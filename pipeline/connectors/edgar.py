"""
FinMetrics — EDGAR Connector
==============================
Fetches XBRL financial data from SEC EDGAR for US-listed companies.
Handles both domestic filers (10-K/10-Q, US-GAAP) and foreign private
issuers (20-F/6-K, IFRS).

Data sources:
  - Company tickers:   https://data.sec.gov/submissions/company_tickers.json
  - Company facts:     https://data.sec.gov/api/xbrl/companyfacts/CIK{n}.json
  - Filings RSS feed:  https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent

Rate limits:
  - 10 requests/second across all EDGAR domains (data.sec.gov, efts.sec.gov, etc.)
  - Target 8 req/sec in practice for safety margin
  - No daily cap
  - User-Agent header required — 403 without it

Known issues documented:
  - Some companies report Revenue as multiple tags (Revenues, RevenueFromContractWithCustomer, etc.)
    The tag_resolver handles priority-ordered fallback.
  - Foreign 20-F filers use IFRS taxonomy tags, not us-gaap namespace.
    Detected by checking namespace prefix in source_tag.
  - CIK numbers must be zero-padded to 10 digits in API URLs.
  - companyfacts JSON can be 5-20MB for large companies — stream don't load all at once.

ETL Workflow Standard (from HEMM Section 8.4):
  1. Run scripts/diagnose_edgar.py before writing any new ETL logic
  2. Confirm column schema, era breaks, gap years, unit conventions
  3. Document findings in script header — only then write ingest code
"""

import json
import time
import logging
from datetime import datetime, date
from typing import Optional, Iterator

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config.settings import config

logger = logging.getLogger(__name__)


# ── Constants ─────────────────────────────────────────────────────────────────

# Forms that contain structured financial data
FINANCIAL_FORMS = {"10-K", "10-Q", "20-F", "6-K"}

# Minimum gap between requests in seconds (enforces rate limit)
REQUEST_GAP_SECONDS = 1.0 / config.edgar.requests_per_second  # ~0.125s at 8/sec

# IFRS namespace indicator in tag names
IFRS_NAMESPACE_PREFIX = "ifrs"
GAAP_NAMESPACE_PREFIX = "us-gaap"


# ── Rate-Limited HTTP Session ─────────────────────────────────────────────────

class EdgarSession:
    """
    HTTP session with automatic rate limiting and retry logic.

    All EDGAR API requests go through this class to ensure:
      - User-Agent header present on every request
      - Rate limit respected (< 10 req/sec)
      - Retries with exponential backoff on transient failures
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": config.edgar.user_agent,
            "Accept": "application/json",
        })
        self._last_request_time = 0.0

    def _throttle(self):
        """Enforce minimum gap between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < REQUEST_GAP_SECONDS:
            time.sleep(REQUEST_GAP_SECONDS - elapsed)
        self._last_request_time = time.time()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
        reraise=True,
    )
    def get(self, url: str, **kwargs) -> requests.Response:
        """
        GET request with rate limiting and retry.

        Raises:
            requests.HTTPError: on 4xx/5xx responses (not retried — likely permanent)
            requests.ConnectionError: on network failure (retried up to 3 times)
            requests.Timeout: on timeout (retried up to 3 times)
        """
        self._throttle()
        logger.debug("GET %s", url)
        response = self.session.get(url, timeout=30, **kwargs)

        if response.status_code == 403:
            logger.error(
                "EDGAR returned 403 Forbidden. Check User-Agent header. "
                "Current value: %s", config.edgar.user_agent
            )
        if response.status_code == 429:
            logger.warning("EDGAR rate limit hit (429). Backing off 60 seconds.")
            time.sleep(60)
            return self.get(url, **kwargs)  # retry after backoff

        response.raise_for_status()
        return response


# Shared session — one instance per process
_session = EdgarSession()


# ── Company Registry ──────────────────────────────────────────────────────────

def fetch_ticker_to_cik() -> dict[str, str]:
    """
    Download the full ticker → CIK mapping from EDGAR.

    Returns:
        dict mapping ticker symbols (uppercase) to zero-padded CIK strings.
        e.g. {'AAPL': '0000320193', 'NVDA': '0001045810'}

    Notes:
        This endpoint returns all ~10,000 tickers in one JSON file (~500KB).
        Cache aggressively — updates infrequently (daily at most).
        CIK is returned as integer in the JSON — we zero-pad to 10 digits here.
    """
    logger.info("Fetching ticker → CIK mapping from EDGAR")
    response = _session.get(config.edgar.tickers_url)
    raw = response.json()

    mapping = {}
    for entry in raw.values():
        ticker = entry.get("ticker", "").upper()
        cik    = str(entry.get("cik_str", "")).zfill(10)
        if ticker:
            mapping[ticker] = cik

    logger.info("Loaded %d ticker→CIK mappings", len(mapping))
    return mapping


def cik_for_ticker(ticker: str, registry: Optional[dict] = None) -> Optional[str]:
    """
    Look up the 10-digit zero-padded CIK for a ticker symbol.

    Args:
        ticker:   Ticker symbol (case-insensitive).
        registry: Optional pre-loaded mapping dict. If None, fetches from EDGAR.

    Returns:
        Zero-padded CIK string, or None if ticker not found.
    """
    if registry is None:
        registry = fetch_ticker_to_cik()
    return registry.get(ticker.upper())


# ── Company Facts ─────────────────────────────────────────────────────────────

def fetch_company_facts(cik: str) -> dict:
    """
    Fetch all XBRL-tagged facts for a company from EDGAR.

    The companyfacts endpoint returns every financial fact a company has
    ever filed — revenues, assets, income, etc. — across all periods and forms.

    Args:
        cik: 10-digit zero-padded CIK string.

    Returns:
        Full companyfacts JSON dict. Structure:
        {
          "cik": 320193,
          "entityName": "Apple Inc.",
          "facts": {
            "us-gaap": {
              "Revenues": {
                "label": "Revenues",
                "description": "...",
                "units": {
                  "USD": [
                    {"end": "2023-09-30", "val": 383285000000, "form": "10-K", ...},
                    ...
                  ]
                }
              },
              ...
            },
            "ifrs-full": { ... }  # for foreign filers
          }
        }

    Notes:
        Response can be 5-20MB for large companies.
        The "facts" key contains both "us-gaap" and "ifrs-full" namespaces.
        Foreign 20-F filers populate "ifrs-full"; domestic 10-K filers populate "us-gaap".

    Raises:
        requests.HTTPError: if EDGAR returns a non-200 status.
    """
    url = f"{config.edgar.facts_url}/CIK{cik}.json"
    logger.info("Fetching company facts for CIK %s", cik)

    response = _session.get(url)
    data = response.json()

    entity_name = data.get("entityName", "Unknown")
    fact_count  = sum(
        len(tags)
        for ns in data.get("facts", {}).values()
        for tags in [ns]
    )
    logger.info("Loaded %d XBRL concept(s) for %s", fact_count, entity_name)
    return data


def detect_accounting_standard(facts: dict) -> str:
    """
    Infer accounting standard from the namespaces present in facts.

    Returns one of: 'US-GAAP', 'IFRS', 'J-GAAP', 'K-IFRS', 'TW-GAAP'

    Notes:
        EDGAR companyfacts only distinguishes us-gaap vs ifrs-full.
        J-GAAP / K-IFRS / TW-GAAP are only relevant for EDINET/DART/TWSE connectors.
        For EDGAR: presence of "ifrs-full" namespace = foreign IFRS filer.
    """
    fact_namespaces = set(facts.get("facts", {}).keys())

    if "us-gaap" in fact_namespaces:
        return "US-GAAP"
    elif "ifrs-full" in fact_namespaces:
        return "IFRS"
    else:
        # Unexpected — log for investigation
        logger.warning(
            "Unknown namespaces in facts: %s. Defaulting to US-GAAP.",
            fact_namespaces
        )
        return "US-GAAP"


# ── Fact Extraction ───────────────────────────────────────────────────────────

def extract_facts(
    facts_json: dict,
    cik: str,
    forms: Optional[set[str]] = None,
) -> Iterator[dict]:
    """
    Extract individual XBRL fact records from a companyfacts JSON response.

    Yields one dict per fact record — ready for insertion into raw_facts table.

    Args:
        facts_json: Full companyfacts JSON from fetch_company_facts().
        cik:        Zero-padded CIK string (for logging).
        forms:      Optional set of form types to include. Default: FINANCIAL_FORMS.
                    Pass None to include all forms.

    Yields:
        dict with keys matching raw_facts table columns:
            source_tag, taxonomy, value, unit, period_start, period_end,
            period_type, fiscal_year, fiscal_quarter, form_type, accession, filing_date

    Notes:
        Period type detection:
          - "end" present + "start" present → duration (income statement)
          - "end" present + "start" absent  → instant (balance sheet)

        Fiscal year / quarter derivation:
          Uses the "fy" and "fp" fields from EDGAR if present.
          "fp" values: "Q1", "Q2", "Q3", "Q4", "FY" (annual)

        Shares and pure units:
          Some facts are reported in "shares" or "pure" units — not USD.
          These are included and stored with their original unit.
    """
    if forms is None:
        forms = FINANCIAL_FORMS

    entity_name = facts_json.get("entityName", cik)
    all_facts   = facts_json.get("facts", {})
    yielded     = 0
    skipped     = 0

    for namespace, concepts in all_facts.items():
        for tag_name, concept_data in concepts.items():
            source_tag = f"{namespace}:{tag_name}"
            units_data = concept_data.get("units", {})

            for unit, records in units_data.items():
                for record in records:
                    form_type = record.get("form", "")

                    # Filter to financial statement forms only
                    if forms and form_type not in forms:
                        skipped += 1
                        continue

                    # Parse dates
                    period_end_str   = record.get("end")
                    period_start_str = record.get("start")

                    if not period_end_str:
                        skipped += 1
                        continue

                    try:
                        period_end   = date.fromisoformat(period_end_str)
                        period_start = date.fromisoformat(period_start_str) if period_start_str else None
                    except ValueError:
                        logger.debug("Invalid date in fact %s: %s", source_tag, period_end_str)
                        skipped += 1
                        continue

                    # Determine period type
                    fact_period_type = "duration" if period_start else "instant"

                    # Fiscal year / quarter from EDGAR metadata
                    fiscal_year    = record.get("fy")
                    fp             = record.get("fp", "")
                    fiscal_quarter = None
                    if fp and fp.startswith("Q") and len(fp) == 2:
                        try:
                            fiscal_quarter = int(fp[1])
                        except ValueError:
                            pass

                    yield {
                        "source_tag":    source_tag,
                        "taxonomy":      namespace,
                        "value":         record.get("val"),
                        "unit":          unit,
                        "period_start":  period_start,
                        "period_end":    period_end,
                        "period_type":   fact_period_type,
                        "fiscal_year":   fiscal_year,
                        "fiscal_quarter": fiscal_quarter,
                        "form_type":     form_type,
                        "accession":     record.get("accn"),
                        "filing_date":   record.get("filed"),
                        "is_restated":   False,  # EDGAR doesn't flag restated facts directly
                    }
                    yielded += 1

    logger.info(
        "Extracted %d facts for %s (skipped %d non-financial forms)",
        yielded, entity_name, skipped
    )


# ── Submission History ────────────────────────────────────────────────────────

def fetch_recent_filings(cik: str, form_types: Optional[set[str]] = None) -> list[dict]:
    """
    Fetch recent filing history for a company from the submissions endpoint.

    Useful for:
      - Checking when the most recent 10-K/10-Q was filed
      - Triggering incremental refreshes after new filings
      - Detecting amendments (10-K/A, 10-Q/A)

    Args:
        cik:        Zero-padded CIK.
        form_types: Optional filter. Default: FINANCIAL_FORMS.

    Returns:
        List of filing dicts with keys: form, filingDate, accessionNumber, periodOfReport
    """
    if form_types is None:
        form_types = FINANCIAL_FORMS

    url = f"{config.edgar.submissions_url}/CIK{cik}.json"
    response = _session.get(url)
    data = response.json()

    filings = []
    recent = data.get("filings", {}).get("recent", {})

    forms   = recent.get("form", [])
    dates   = recent.get("filingDate", [])
    accns   = recent.get("accessionNumber", [])
    periods = recent.get("periodOfReport", [])

    for i, form in enumerate(forms):
        if form in form_types:
            filings.append({
                "form":            form,
                "filing_date":     dates[i]   if i < len(dates)   else None,
                "accession":       accns[i]   if i < len(accns)   else None,
                "period_of_report": periods[i] if i < len(periods) else None,
            })

    logger.debug("Found %d financial filings for CIK %s", len(filings), cik)
    return filings


def get_last_filing_date(cik: str) -> Optional[date]:
    """
    Return the date of the most recent financial filing for a company.
    Used to decide whether a refresh is needed.
    """
    filings = fetch_recent_filings(cik)
    if not filings:
        return None

    dates = [
        date.fromisoformat(f["filing_date"])
        for f in filings
        if f.get("filing_date")
    ]
    return max(dates) if dates else None


# ── Diagnostic Helper ─────────────────────────────────────────────────────────

def summarize_company_facts(facts_json: dict) -> dict:
    """
    Produce a diagnostic summary of a companyfacts response.

    Returns a dict suitable for logging or display:
      - entity name
      - namespaces present (us-gaap, ifrs-full, etc.)
      - concept count per namespace
      - year range covered
      - form types present
      - inferred accounting standard

    Use this during development to understand a new company's data
    before writing ETL logic. Follows the HEMM diagnostic-first pattern.
    """
    entity_name = facts_json.get("entityName", "Unknown")
    all_facts   = facts_json.get("facts", {})

    summary = {
        "entity_name":         entity_name,
        "accounting_standard": detect_accounting_standard(facts_json),
        "namespaces":          list(all_facts.keys()),
        "concepts_per_ns":     {},
        "year_range":          {},
        "form_types":          set(),
        "total_facts":         0,
    }

    for namespace, concepts in all_facts.items():
        summary["concepts_per_ns"][namespace] = len(concepts)
        years = []
        for tag_name, concept_data in concepts.items():
            for unit, records in concept_data.get("units", {}).items():
                for r in records:
                    summary["form_types"].add(r.get("form", ""))
                    if r.get("end"):
                        years.append(r["end"][:4])
                    summary["total_facts"] += 1

        if years:
            summary["year_range"][namespace] = {
                "earliest": min(years),
                "latest":   max(years),
            }

    summary["form_types"] = sorted(summary["form_types"])
    return summary
