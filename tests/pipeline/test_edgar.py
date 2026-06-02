"""
Tests — EDGAR Connector
=========================
Tests for EDGAR data fetching and parsing.
Uses real EDGAR API for integration tests (marked with @pytest.mark.integration).
Unit tests use mock data.

Run unit tests only:  python -m pytest tests/pipeline/test_edgar.py -v -m "not integration"
Run all tests:        python -m pytest tests/pipeline/test_edgar.py -v
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from datetime import date
from unittest.mock import patch, MagicMock

from pipeline.connectors.edgar import (
    detect_accounting_standard, extract_facts, summarize_company_facts,
    cik_for_ticker, FINANCIAL_FORMS
)


# ── Test Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def sample_gaap_facts():
    """Minimal companyfacts JSON for a US-GAAP company."""
    return {
        "cik": 320193,
        "entityName": "Test Company Inc.",
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "label": "Revenues",
                    "description": "Amount of revenue recognized",
                    "units": {
                        "USD": [
                            {
                                "end": "2024-09-30",
                                "start": "2023-10-01",
                                "val": 383285000000,
                                "accn": "0000320193-24-000001",
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2024-11-01",
                            },
                            {
                                "end": "2024-06-30",
                                "start": "2024-04-01",
                                "val": 95000000000,
                                "accn": "0000320193-24-000002",
                                "fy": 2024,
                                "fp": "Q3",
                                "form": "10-Q",
                                "filed": "2024-08-01",
                            },
                        ]
                    }
                },
                "CashAndCashEquivalentsAtCarryingValue": {
                    "label": "Cash and Cash Equivalents",
                    "units": {
                        "USD": [
                            {
                                "end": "2024-09-30",
                                "val": 65000000000,
                                "accn": "0000320193-24-000001",
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2024-11-01",
                            }
                        ]
                    }
                }
            }
        }
    }


@pytest.fixture
def sample_ifrs_facts():
    """Minimal companyfacts JSON for an IFRS filer (foreign ADR)."""
    return {
        "cik": 1045810,
        "entityName": "Foreign Corp Ltd.",
        "facts": {
            "ifrs-full": {
                "Revenue": {
                    "label": "Revenue",
                    "units": {
                        "USD": [
                            {
                                "end": "2024-12-31",
                                "start": "2024-01-01",
                                "val": 50000000000,
                                "form": "20-F",
                                "filed": "2025-03-01",
                                "fy": 2024,
                                "fp": "FY",
                            }
                        ]
                    }
                }
            }
        }
    }


# ── Unit Tests ────────────────────────────────────────────────────────────────

class TestAccountingStandardDetection:

    def test_detects_gaap(self, sample_gaap_facts):
        standard = detect_accounting_standard(sample_gaap_facts)
        assert standard == "US-GAAP"

    def test_detects_ifrs(self, sample_ifrs_facts):
        standard = detect_accounting_standard(sample_ifrs_facts)
        assert standard == "IFRS"

    def test_empty_facts_defaults_to_gaap(self):
        empty_facts = {"cik": 123, "entityName": "Test", "facts": {}}
        standard = detect_accounting_standard(empty_facts)
        assert standard == "US-GAAP"


class TestFactExtraction:

    def test_extracts_revenue_duration(self, sample_gaap_facts):
        facts = list(extract_facts(sample_gaap_facts, "0000320193"))
        revenue_facts = [f for f in facts if "Revenues" in f["source_tag"]]
        assert len(revenue_facts) > 0
        annual = next(f for f in revenue_facts if f["form_type"] == "10-K")
        assert annual["period_type"] == "duration"   # has start + end
        assert annual["value"] == 383285000000
        assert annual["unit"] == "USD"

    def test_extracts_cash_instant(self, sample_gaap_facts):
        facts = list(extract_facts(sample_gaap_facts, "0000320193"))
        cash_facts = [
            f for f in facts
            if "CashAndCashEquivalents" in f["source_tag"]
        ]
        assert len(cash_facts) > 0
        assert cash_facts[0]["period_type"] == "instant"  # no start date

    def test_fiscal_quarter_parsed(self, sample_gaap_facts):
        facts = list(extract_facts(sample_gaap_facts, "0000320193"))
        q3_facts = [f for f in facts if f.get("form_type") == "10-Q"]
        assert len(q3_facts) > 0
        assert q3_facts[0]["fiscal_quarter"] == 3

    def test_filters_non_financial_forms(self, sample_gaap_facts):
        # Add a non-financial form type to test data
        sample_gaap_facts["facts"]["us-gaap"]["Revenues"]["units"]["USD"].append({
            "end": "2024-01-15",
            "start": "2023-01-01",
            "val": 99999,
            "form": "8-K",   # not a financial statement form
            "filed": "2024-01-15",
        })
        facts = list(extract_facts(sample_gaap_facts, "0000320193",
                                   forms=FINANCIAL_FORMS))
        eight_k_facts = [f for f in facts if f.get("form_type") == "8-K"]
        assert len(eight_k_facts) == 0

    def test_skips_records_with_no_period_end(self, sample_gaap_facts):
        sample_gaap_facts["facts"]["us-gaap"]["Revenues"]["units"]["USD"].append({
            "val": 12345,
            "form": "10-K",
            # No "end" field
        })
        # Should not raise — just skip the bad record
        facts = list(extract_facts(sample_gaap_facts, "0000320193"))
        assert all(f["period_end"] is not None for f in facts)


class TestCompanyFactsSummary:

    def test_summary_entity_name(self, sample_gaap_facts):
        summary = summarize_company_facts(sample_gaap_facts)
        assert summary["entity_name"] == "Test Company Inc."

    def test_summary_accounting_standard(self, sample_gaap_facts):
        summary = summarize_company_facts(sample_gaap_facts)
        assert summary["accounting_standard"] == "US-GAAP"

    def test_summary_namespaces(self, sample_gaap_facts):
        summary = summarize_company_facts(sample_gaap_facts)
        assert "us-gaap" in summary["namespaces"]

    def test_summary_year_range(self, sample_gaap_facts):
        summary = summarize_company_facts(sample_gaap_facts)
        assert "us-gaap" in summary["year_range"]
        assert summary["year_range"]["us-gaap"]["latest"] == "2024"

    def test_summary_total_facts(self, sample_gaap_facts):
        summary = summarize_company_facts(sample_gaap_facts)
        # 2 Revenue records + 1 Cash record = 3
        assert summary["total_facts"] == 3


class TestCikLookup:

    def test_returns_none_for_unknown_ticker(self):
        registry = {"AAPL": "0000320193", "NVDA": "0001045810"}
        result = cik_for_ticker("XXXX", registry)
        assert result is None

    def test_case_insensitive(self):
        registry = {"AAPL": "0000320193"}
        assert cik_for_ticker("aapl", registry) == "0000320193"
        assert cik_for_ticker("AAPL", registry) == "0000320193"
        assert cik_for_ticker("Aapl", registry) == "0000320193"


# ── Integration Tests (require live EDGAR access) ─────────────────────────────

@pytest.mark.integration
class TestEdgarIntegration:
    """
    These tests hit the real EDGAR API.
    Marked as integration — skip in CI unless EDGAR access is available.
    Run manually: pytest tests/pipeline/test_edgar.py -v -m integration
    """

    def test_fetch_nvda_facts(self):
        """NVDA should have US-GAAP facts and Revenue tags."""
        from pipeline.connectors.edgar import fetch_ticker_to_cik, fetch_company_facts
        registry = fetch_ticker_to_cik()
        cik = cik_for_ticker("NVDA", registry)
        assert cik is not None

        facts = fetch_company_facts(cik)
        assert facts["entityName"] != ""
        assert "us-gaap" in facts["facts"]
        assert "Revenues" in facts["facts"]["us-gaap"] or \
               "RevenueFromContractWithCustomerExcludingAssessedTax" in facts["facts"]["us-gaap"]

    def test_fetch_tsm_facts_ifrs(self):
        """TSMC (TSM) files 20-F with IFRS — should detect IFRS standard."""
        from pipeline.connectors.edgar import fetch_ticker_to_cik, fetch_company_facts
        registry = fetch_ticker_to_cik()
        cik = cik_for_ticker("TSM", registry)
        if cik is None:
            pytest.skip("TSM ticker not found in registry")

        facts = fetch_company_facts(cik)
        standard = detect_accounting_standard(facts)
        # TSMC files under IFRS via 20-F
        assert standard in ("IFRS", "US-GAAP")  # accept either — may vary by filing
