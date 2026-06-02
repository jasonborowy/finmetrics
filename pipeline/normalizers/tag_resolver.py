"""
FinMetrics — Tag Resolver
==========================
Maps XBRL source tags from any taxonomy to canonical metric names.

The tag_mappings table (~825 entries) is the authoritative source.
This module provides the in-memory resolver that the pipeline uses
at runtime — loading mappings once and resolving thousands of facts.

Canonical metric names are defined in FinMetrics_DataFramework.docx Section 5.
Each canonical name maps to 3–5 synonym tags per taxonomy, ordered by priority.

Taxonomy namespaces handled:
  us-gaap   — SEC EDGAR domestic filers
  ifrs-full — SEC EDGAR foreign ADR filers (20-F)
  jpcrp     — EDINET Japan (J-GAAP and IFRS)
  k-ifrs    — DART South Korea (K-IFRS)
  tw-ifrs   — TWSE Taiwan (IFRS-convergent)

Example resolution:
  "us-gaap:Revenues"                         → "Revenue"  (priority 1)
  "us-gaap:RevenueFromContractWithCustomer"   → "Revenue"  (priority 2)
  "ifrs-full:Revenue"                         → "Revenue"  (priority 1)
  "jpcrp:NetSales"                            → "Revenue"  (priority 1)
  "us-gaap:UnknownTag"                        → None       (unresolved)
"""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# ── Canonical Metric Definitions ──────────────────────────────────────────────
# Seeded here for Phase 1 (EDGAR only).
# Full 825-entry mapping loaded from database (tag_mappings table) in production.
# Format: {canonical_name: {taxonomy: [tag_priority_1, tag_priority_2, ...]}}

CANONICAL_TAG_SEED: dict[str, dict[str, list[str]]] = {

    # ── GROWTH ────────────────────────────────────────────────────────────────
    "Revenue": {
        "us-gaap":   ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                      "SalesRevenueNet", "RevenueFromContractWithCustomerIncludingAssessedTax",
                      "RevenueFromContractWithCustomer"],
        "ifrs-full": ["Revenue", "RevenueFromContractsWithCustomers", "TurnoverRevenue"],
        "jpcrp":     ["NetSales", "OperatingRevenue"],
        "k-ifrs":    ["Revenue"],
        "tw-ifrs":   ["Revenue"],
    },
    "Employees": {
        "us-gaap":   ["EntityNumberOfEmployees"],
        "ifrs-full": ["EmployeesAtEndOfPeriod", "NumberOfEmployees"],
        "jpcrp":     ["NumberOfEmployees"],
        "k-ifrs":    ["NumberOfEmployees"],
        "tw-ifrs":   ["NumberOfEmployees"],
    },
    "CommonSharesOutstanding": {
        "us-gaap":   ["CommonStockSharesOutstanding"],
        "ifrs-full": ["NumberOfSharesOutstanding", "OrdinarySharesOutstanding"],
        "jpcrp":     ["NumberOfSharesIssued"],
    },
    "RDExpense": {
        "us-gaap":   ["ResearchAndDevelopmentExpense",
                      "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost"],
        "ifrs-full": ["ResearchAndDevelopmentExpense"],
        "jpcrp":     ["ResearchAndDevelopmentExpenses"],
    },
    "SGAExpense": {
        "us-gaap":   ["SellingGeneralAndAdministrativeExpense"],
        "ifrs-full": ["SellingGeneralAndAdministrativeExpense"],
        "jpcrp":     ["SellingExpenses", "GeneralAndAdministrativeExpense"],  # sum these
    },

    # ── PROFITABILITY ─────────────────────────────────────────────────────────
    "COGS": {
        "us-gaap":   ["CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold",
                      "CostOfGoodsAndServiceExcludingDepreciation"],
        "ifrs-full": ["CostOfSales"],
        "jpcrp":     ["CostOfSales", "CostOfRevenue"],
        "k-ifrs":    ["CostOfSales"],
        "tw-ifrs":   ["CostOfSales"],
    },
    "GrossProfit": {
        "us-gaap":   ["GrossProfit"],
        "ifrs-full": ["GrossProfit"],
        "jpcrp":     ["GrossProfit"],
        "k-ifrs":    ["GrossProfit"],
        "tw-ifrs":   ["GrossProfit"],
    },
    "OperatingIncome": {
        "us-gaap":   ["OperatingIncomeLoss"],
        "ifrs-full": ["ProfitLossFromOperatingActivities", "OperatingProfit"],
        "jpcrp":     ["OperatingIncome"],
        "k-ifrs":    ["OperatingIncomeLoss"],
    },
    "NetIncome": {
        "us-gaap":   ["NetIncomeLoss", "ProfitLoss"],
        "ifrs-full": ["ProfitLoss"],
        "jpcrp":     ["NetIncome", "ProfitLoss"],
        "k-ifrs":    ["ProfitLoss"],
    },
    "EBIT": {
        "us-gaap":   ["OperatingIncomeLoss"],
        "ifrs-full": ["ProfitLossFromOperatingActivities"],
        "jpcrp":     ["OperatingIncome"],
    },
    "DA": {  # Depreciation & Amortization
        "us-gaap":   ["DepreciationDepletionAndAmortization",
                      "DepreciationAmortizationAndAccretionNet",
                      "Depreciation"],
        "ifrs-full": ["DepreciationAndAmortisationExpense",
                      "DepreciationAmortisationAndImpairmentLoss"],
        "jpcrp":     ["Depreciation", "DepreciationAndAmortization"],
    },
    "Cash": {
        "us-gaap":   ["CashAndCashEquivalentsAtCarryingValue",
                      "CashCashEquivalentsAndShortTermInvestments",
                      "Cash"],
        "ifrs-full": ["CashAndCashEquivalents"],
        "jpcrp":     ["CashAndDeposits", "CashAndCashEquivalents"],
    },
    "OperatingCashFlow": {
        "us-gaap":   ["NetCashProvidedByUsedInOperatingActivities"],
        "ifrs-full": ["CashFlowsFromUsedInOperatingActivities"],
        "jpcrp":     ["NetCashProvidedByUsedInOperatingActivities"],
    },
    "CapEx": {
        "us-gaap":   ["PaymentsToAcquirePropertyPlantAndEquipment",
                      "CapitalExpendituresIncurredButNotYetPaid"],
        "ifrs-full": ["PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"],
        "jpcrp":     ["PurchaseOfPropertyPlantAndEquipment"],
    },
    "PreTaxIncome": {
        "us-gaap":   ["IncomeLossFromContinuingOperationsBeforeIncomeTaxes",
                      "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"],
        "ifrs-full": ["ProfitLossBeforeTax"],
        "jpcrp":     ["OrdinaryIncome"],
    },
    "OperatingExpenses": {
        "us-gaap":   ["OperatingExpenses", "CostsAndExpenses"],
        "ifrs-full": ["OperatingExpense"],
        "jpcrp":     ["OperatingExpenses"],
    },

    # ── CYCLE ─────────────────────────────────────────────────────────────────
    "Inventory": {
        "us-gaap":   ["InventoryNet", "InventoryGross"],
        "ifrs-full": ["Inventories"],
        "jpcrp":     ["Inventories"],
        "k-ifrs":    ["Inventories"],
    },
    "FinishedGoodsInventory": {
        "us-gaap":   ["InventoryFinishedGoods", "InventoryFinishedGoodsNetOfReserves"],
        "ifrs-full": ["FinishedGoods"],
        "jpcrp":     ["MerchandiseAndFinishedGoods"],
    },
    "RawMaterialsInventory": {
        "us-gaap":   ["InventoryRawMaterials", "InventoryRawMaterialsNetOfReserves"],
        "ifrs-full": ["RawMaterialsAndConsumables"],
        "jpcrp":     ["RawMaterials"],
    },
    "WIPInventory": {
        "us-gaap":   ["InventoryWorkInProcess", "InventoryWorkInProcessNetOfReserves"],
        "ifrs-full": ["WorkInProgress", "CurrentWorkInProgress"],
        "jpcrp":     ["WorkInProcess"],
    },
    "AccountsReceivable": {
        "us-gaap":   ["AccountsReceivableNetCurrent", "ReceivablesNetCurrent"],
        "ifrs-full": ["TradeAndOtherCurrentReceivables", "TradeReceivablesCurrent"],
        "jpcrp":     ["NotesAndAccountsReceivableTrade"],
    },
    "AccountsPayable": {
        "us-gaap":   ["AccountsPayableCurrent"],
        "ifrs-full": ["TradeAndOtherCurrentPayables", "TradeAndOtherPayablesCurrent"],
        "jpcrp":     ["NotesAndAccountsPayableTrade"],
    },

    # ── COMPLEXITY ────────────────────────────────────────────────────────────
    "TotalAssets": {
        "us-gaap":   ["Assets"],
        "ifrs-full": ["Assets"],
        "jpcrp":     ["Assets"],
    },
    "CurrentAssets": {
        "us-gaap":   ["AssetsCurrent"],
        "ifrs-full": ["CurrentAssets"],
        "jpcrp":     ["CurrentAssets"],
    },
    "CurrentLiabilities": {
        "us-gaap":   ["LiabilitiesCurrent"],
        "ifrs-full": ["CurrentLiabilities"],
        "jpcrp":     ["CurrentLiabilities"],
    },
    "TotalEquity": {
        "us-gaap":   ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
        "ifrs-full": ["Equity"],
        "jpcrp":     ["NetAssets"],
    },
    "LongTermDebt": {
        "us-gaap":   ["LongTermDebt", "LongTermDebtNoncurrent"],
        "ifrs-full": ["NoncurrentPortionOfLongTermBorrowings", "LongTermBorrowings"],
        "jpcrp":     ["LongTermLoansPayable", "BondsPayable"],
    },
    "ShortTermDebt": {
        "us-gaap":   ["ShortTermBorrowings", "DebtCurrent"],
        "ifrs-full": ["CurrentBorrowings", "ShorttermBorrowings"],
        "jpcrp":     ["ShortTermLoansPayable"],
    },
    "RetainedEarnings": {
        "us-gaap":   ["RetainedEarningsAccumulatedDeficit"],
        "ifrs-full": ["RetainedEarnings"],
        "jpcrp":     ["RetainedEarnings"],
    },
    "PPENet": {
        "us-gaap":   ["PropertyPlantAndEquipmentNet"],
        "ifrs-full": ["PropertyPlantAndEquipment"],
        "jpcrp":     ["PropertyPlantAndEquipment"],
    },
    "ShortTermInvestments": {
        "us-gaap":   ["ShortTermInvestments", "MarketableSecuritiesCurrent"],
        "ifrs-full": ["CurrentFinancialAssetsAtFairValueThroughProfitOrLoss"],
        "jpcrp":     ["InvestmentSecurities"],
    },
}


# ── Resolver ──────────────────────────────────────────────────────────────────

@dataclass
class ResolutionResult:
    """Result of a single tag resolution attempt."""
    canonical_name: Optional[str]
    source_tag:     str
    taxonomy:       str
    priority:       int       # 1 = first choice, higher = fallback
    resolved:       bool


class TagResolver:
    """
    Resolves XBRL source tags to canonical metric names.

    Usage:
        resolver = TagResolver()
        result = resolver.resolve("us-gaap:Revenues")
        # result.canonical_name == "Revenue"
        # result.resolved == True

    The resolver loads the seed mappings at init time. In production,
    call load_from_database() to use the full tag_mappings table.
    """

    def __init__(self):
        # Build lookup: {(taxonomy, source_tag) → (canonical_name, priority)}
        self._lookup: dict[tuple[str, str], tuple[str, int]] = {}
        self._unresolved_log: set[str] = set()  # track new tags for db insertion
        self._load_seed()

    def _load_seed(self):
        """Load the seed mappings into the lookup dict."""
        count = 0
        for canonical_name, taxonomy_map in CANONICAL_TAG_SEED.items():
            for taxonomy, tags in taxonomy_map.items():
                for priority, tag in enumerate(tags, start=1):
                    key = (taxonomy, tag)
                    # Only store the best (lowest) priority for a given tag
                    if key not in self._lookup or self._lookup[key][1] > priority:
                        self._lookup[key] = (canonical_name, priority)
                        count += 1
        logger.info("TagResolver loaded %d mappings from seed", count)

    def load_from_database(self, db_mappings: list[dict]):
        """
        Load additional mappings from the tag_mappings database table.
        Extends (does not replace) the seed mappings.

        Args:
            db_mappings: List of dicts with keys:
                         canonical_name, taxonomy, source_tag, priority
        """
        added = 0
        for row in db_mappings:
            key = (row["taxonomy"], row["source_tag"])
            priority = row["priority"]
            canonical = row["canonical_name"]
            if key not in self._lookup or self._lookup[key][1] > priority:
                self._lookup[key] = (canonical, priority)
                added += 1
        logger.info("TagResolver loaded %d additional mappings from database", added)

    def resolve(self, source_tag: str) -> ResolutionResult:
        """
        Resolve a single source_tag to a canonical metric name.

        Args:
            source_tag: Full tag string including namespace prefix.
                        e.g. "us-gaap:Revenues" or "ifrs-full:Revenue"

        Returns:
            ResolutionResult with canonical_name=None if unresolved.
        """
        # Parse namespace from tag
        if ":" in source_tag:
            taxonomy, tag_name = source_tag.split(":", 1)
        else:
            taxonomy = "us-gaap"  # default assumption
            tag_name = source_tag

        key = (taxonomy, tag_name)
        if key in self._lookup:
            canonical_name, priority = self._lookup[key]
            return ResolutionResult(
                canonical_name=canonical_name,
                source_tag=source_tag,
                taxonomy=taxonomy,
                priority=priority,
                resolved=True,
            )

        # Unresolved — log for potential addition to mappings
        if source_tag not in self._unresolved_log:
            self._unresolved_log.add(source_tag)
            logger.debug("Unresolved tag: %s", source_tag)

        return ResolutionResult(
            canonical_name=None,
            source_tag=source_tag,
            taxonomy=taxonomy,
            priority=0,
            resolved=False,
        )

    def resolve_batch(self, source_tags: list[str]) -> dict[str, ResolutionResult]:
        """Resolve a list of tags. Returns dict keyed by source_tag."""
        return {tag: self.resolve(tag) for tag in source_tags}

    def unresolved_tags(self) -> set[str]:
        """
        Return all tags encountered during this session that had no mapping.
        Use to identify candidates for addition to tag_mappings table.
        """
        return self._unresolved_log.copy()

    def coverage_report(self) -> dict:
        """
        Return a summary of mapping coverage.
        Useful for monitoring — track coverage % as new companies are added.
        """
        return {
            "total_mappings":    len(self._lookup),
            "canonical_metrics": len(CANONICAL_TAG_SEED),
            "taxonomies":        sorted({k[0] for k in self._lookup.keys()}),
            "unresolved_this_session": len(self._unresolved_log),
        }


# ── Module-level singleton ─────────────────────────────────────────────────────
# Import and reuse: from pipeline.normalizers.tag_resolver import resolver
resolver = TagResolver()
