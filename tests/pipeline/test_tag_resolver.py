"""
Tests — Tag Resolver
======================
Verifies that canonical tag mappings work correctly across all
five taxonomies. Every canonical metric should resolve at least
one tag per taxonomy where that taxonomy is expected to have coverage.

Run:  python -m pytest tests/pipeline/test_tag_resolver.py -v
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from pipeline.normalizers.tag_resolver import TagResolver, CANONICAL_TAG_SEED


@pytest.fixture
def resolver():
    return TagResolver()


class TestTagResolution:

    def test_revenue_resolves_gaap(self, resolver):
        result = resolver.resolve("us-gaap:Revenues")
        assert result.resolved is True
        assert result.canonical_name == "Revenue"
        assert result.priority == 1

    def test_revenue_resolves_gaap_asc606(self, resolver):
        """Post-ASC 606 tag should resolve as fallback."""
        result = resolver.resolve(
            "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"
        )
        assert result.resolved is True
        assert result.canonical_name == "Revenue"
        assert result.priority == 2  # second priority

    def test_revenue_resolves_ifrs(self, resolver):
        result = resolver.resolve("ifrs-full:Revenue")
        assert result.resolved is True
        assert result.canonical_name == "Revenue"

    def test_revenue_resolves_jgaap(self, resolver):
        result = resolver.resolve("jpcrp:NetSales")
        assert result.resolved is True
        assert result.canonical_name == "Revenue"

    def test_cogs_resolves_gaap(self, resolver):
        result = resolver.resolve("us-gaap:CostOfGoodsAndServicesSold")
        assert result.resolved is True
        assert result.canonical_name == "COGS"

    def test_cogs_resolves_ifrs(self, resolver):
        result = resolver.resolve("ifrs-full:CostOfSales")
        assert result.resolved is True
        assert result.canonical_name == "COGS"

    def test_unknown_tag_returns_unresolved(self, resolver):
        result = resolver.resolve("us-gaap:SomeCompletelyMadeUpTag12345")
        assert result.resolved is False
        assert result.canonical_name is None

    def test_unknown_tag_logged_once(self, resolver):
        """Unresolved tags should appear in unresolved_tags() after first encounter."""
        tag = "us-gaap:TagThatDoesNotExistAtAll"
        resolver.resolve(tag)
        assert tag in resolver.unresolved_tags()

    def test_tag_without_namespace_prefix(self, resolver):
        """Tags without namespace prefix should default to us-gaap resolution."""
        result = resolver.resolve("Revenues")  # no namespace prefix
        assert result.resolved is True
        assert result.canonical_name == "Revenue"

    def test_inventory_all_taxonomies(self, resolver):
        """Inventory should resolve across all taxonomies."""
        test_cases = [
            ("us-gaap:InventoryNet",  "Inventory"),
            ("ifrs-full:Inventories", "Inventory"),
            ("jpcrp:Inventories",     "Inventory"),
        ]
        for tag, expected in test_cases:
            result = resolver.resolve(tag)
            assert result.resolved, f"Tag {tag} should resolve"
            assert result.canonical_name == expected, \
                f"Tag {tag} should resolve to {expected}, got {result.canonical_name}"

    def test_cash_resolves(self, resolver):
        result = resolver.resolve("us-gaap:CashAndCashEquivalentsAtCarryingValue")
        assert result.resolved is True
        assert result.canonical_name == "Cash"

    def test_batch_resolution(self, resolver):
        tags = [
            "us-gaap:Revenues",
            "us-gaap:CostOfGoodsAndServicesSold",
            "us-gaap:UnknownTag",
        ]
        results = resolver.resolve_batch(tags)
        assert len(results) == 3
        assert results["us-gaap:Revenues"].resolved is True
        assert results["us-gaap:CostOfGoodsAndServicesSold"].resolved is True
        assert results["us-gaap:UnknownTag"].resolved is False

    def test_coverage_report(self, resolver):
        report = resolver.coverage_report()
        assert "total_mappings" in report
        assert "canonical_metrics" in report
        assert report["total_mappings"] > 0
        assert report["canonical_metrics"] == len(CANONICAL_TAG_SEED)


class TestSeedCompleteness:
    """Verify seed data has expected coverage."""

    def test_all_growth_metrics_have_gaap_tags(self):
        growth_metrics = [
            "Revenue", "Employees", "CommonSharesOutstanding",
            "RDExpense", "SGAExpense"
        ]
        for metric in growth_metrics:
            assert metric in CANONICAL_TAG_SEED, \
                f"Growth metric '{metric}' missing from seed"
            assert "us-gaap" in CANONICAL_TAG_SEED[metric], \
                f"Growth metric '{metric}' has no US-GAAP tags"

    def test_all_cycle_metrics_have_gaap_tags(self):
        cycle_metrics = [
            "Inventory", "AccountsReceivable", "AccountsPayable",
            "FinishedGoodsInventory", "RawMaterialsInventory", "WIPInventory"
        ]
        for metric in cycle_metrics:
            assert metric in CANONICAL_TAG_SEED
            assert "us-gaap" in CANONICAL_TAG_SEED[metric]

    def test_revenue_has_five_taxonomy_coverage(self):
        """Revenue is the most important metric — should cover all taxonomies."""
        taxonomies = ["us-gaap", "ifrs-full", "jpcrp", "k-ifrs", "tw-ifrs"]
        for taxonomy in taxonomies:
            assert taxonomy in CANONICAL_TAG_SEED["Revenue"], \
                f"Revenue missing {taxonomy} coverage"
