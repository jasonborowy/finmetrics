"""
FinMetrics — EDGAR Diagnostic Script
=======================================
Run this BEFORE writing any new ETL logic for a company or sector.

Follows the ETL Workflow Standard (HEMM Section 8.4):
  Step 1: Diagnostic review — confirm data structure, eras, coverage
  Step 2: Document findings — only then write ETL code

What this script reports:
  - Entity name and accounting standard
  - All XBRL namespaces present
  - Year range of available data
  - Concept (tag) count per namespace
  - All form types filed
  - Which canonical metrics can be resolved
  - Which canonical metrics are MISSING (unresolvable tags)
  - Recent filing dates

Usage:
  python scripts/diagnose_edgar.py --ticker NVDA
  python scripts/diagnose_edgar.py --ticker NVDA --ticker ASML --ticker TSM
  python scripts/diagnose_edgar.py --ticker NVDA --output diagnose_nvda.json

Always review this output and document any surprises in your ETL script
header before writing ingest code.
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.connectors.edgar import (
    fetch_ticker_to_cik, cik_for_ticker, fetch_company_facts,
    summarize_company_facts, fetch_recent_filings
)
from pipeline.normalizers.tag_resolver import resolver

import logging
logging.basicConfig(
    level=logging.WARNING,  # Suppress debug output during diagnosis
    format="%(levelname)s | %(message)s"
)


def diagnose_ticker(ticker: str, registry: dict) -> dict:
    """Run full diagnostic for a single ticker."""
    print(f"\n{'='*60}")
    print(f"  Diagnosing: {ticker.upper()}")
    print(f"{'='*60}")

    # 1. CIK lookup
    cik = cik_for_ticker(ticker, registry)
    if not cik:
        print(f"  ❌ ERROR: Ticker '{ticker}' not found in EDGAR")
        return {"ticker": ticker, "error": "not_found"}

    print(f"  CIK:        {cik}")

    # 2. Fetch company facts
    try:
        facts_json = fetch_company_facts(cik)
    except Exception as e:
        print(f"  ❌ ERROR fetching facts: {e}")
        return {"ticker": ticker, "cik": cik, "error": str(e)}

    # 3. Summary
    summary = summarize_company_facts(facts_json)
    print(f"  Entity:     {summary['entity_name']}")
    print(f"  Standard:   {summary['accounting_standard']}")
    print(f"  Namespaces: {', '.join(summary['namespaces'])}")
    print(f"  Total facts: {summary['total_facts']:,}")

    for ns, rng in summary["year_range"].items():
        print(f"  {ns}: {rng['earliest']} → {rng['latest']}")

    print(f"  Form types: {', '.join(summary['form_types'])}")

    # 4. Tag resolution coverage
    all_facts   = facts_json.get("facts", {})
    all_tags    = set()
    for namespace, concepts in all_facts.items():
        for tag_name in concepts:
            all_tags.add(f"{namespace}:{tag_name}")

    resolved_canonical = set()
    unresolved_tags    = []
    for tag in all_tags:
        result = resolver.resolve(tag)
        if result.resolved:
            resolved_canonical.add(result.canonical_name)
        else:
            unresolved_tags.append(tag)

    # 5. Canonical coverage check
    from pipeline.normalizers.tag_resolver import CANONICAL_TAG_SEED
    all_canonical  = set(CANONICAL_TAG_SEED.keys())
    missing        = all_canonical - resolved_canonical

    print(f"\n  Canonical tag coverage:")
    print(f"    Resolved:  {len(resolved_canonical)}/{len(all_canonical)} metrics")
    print(f"    Missing:   {len(missing)}")

    if missing:
        print(f"\n  ⚠  Missing canonical metrics (no matching tag found):")
        for m in sorted(missing):
            print(f"    - {m}")

    # 6. Key metric spot-check
    print(f"\n  Key metric tags found:")
    key_checks = ["Revenue", "COGS", "GrossProfit", "NetIncome", "Cash",
                  "Inventory", "TotalAssets", "OperatingIncome", "Employees"]
    for canonical in key_checks:
        found = canonical in resolved_canonical
        status = "✓" if found else "✗ MISSING"
        print(f"    {status:12} {canonical}")

    # 7. Recent filings
    try:
        recent = fetch_recent_filings(cik)[:5]
        print(f"\n  Recent filings:")
        for f in recent:
            print(f"    {f['form']:6} | {f['filing_date']} | period: {f['period_of_report']}")
    except Exception as e:
        print(f"\n  ⚠  Could not fetch recent filings: {e}")

    return {
        "ticker":             ticker.upper(),
        "cik":                cik,
        "entity_name":        summary["entity_name"],
        "accounting_standard": summary["accounting_standard"],
        "namespaces":         summary["namespaces"],
        "total_facts":        summary["total_facts"],
        "year_range":         summary["year_range"],
        "form_types":         summary["form_types"],
        "canonical_resolved": len(resolved_canonical),
        "canonical_total":    len(all_canonical),
        "missing_canonical":  sorted(missing),
        "unresolved_tag_count": len(unresolved_tags),
    }


def main():
    parser = argparse.ArgumentParser(
        description="EDGAR diagnostic — run before writing any new ETL logic"
    )
    parser.add_argument("--ticker", action="append", required=True,
                        help="Ticker symbol(s) to diagnose. Can repeat: --ticker NVDA --ticker AAPL")
    parser.add_argument("--output", type=str, default=None,
                        help="Optional: save results to JSON file")
    args = parser.parse_args()

    print("FinMetrics — EDGAR Diagnostic")
    print("Loading ticker→CIK registry...")
    registry = fetch_ticker_to_cik()
    print(f"Registry loaded: {len(registry):,} companies")

    results = []
    for ticker in args.ticker:
        result = diagnose_ticker(ticker.upper(), registry)
        results.append(result)

    # Summary
    print(f"\n{'='*60}")
    print(f"  DIAGNOSTIC SUMMARY")
    print(f"{'='*60}")
    for r in results:
        if "error" in r:
            print(f"  ❌ {r['ticker']}: {r['error']}")
        else:
            coverage = r["canonical_resolved"] / r["canonical_total"] * 100
            missing_count = len(r["missing_canonical"])
            status = "✓" if missing_count == 0 else f"⚠  {missing_count} missing"
            print(f"  {r['ticker']:10} | {r['accounting_standard']:10} | "
                  f"Coverage: {coverage:.0f}% | {status}")

    print(f"\n  Review output above before writing ETL code.")
    print(f"  Document any missing metrics in your ETL script header.\n")

    # Save if requested
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(json.dumps(results, indent=2, default=str))
        print(f"  Results saved to: {args.output}")


if __name__ == "__main__":
    main()
