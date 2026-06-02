"""
FinMetrics — Accounting Normalizer
=====================================
Detects accounting standard differences and applies normalization flags.
Does NOT silently adjust values — flags the difference and adjusts only
where the adjustment is mathematically clean and well-defined.

The five material differences handled here (from DataFramework Section 3):

  1. LIFO Inventory (US-GAAP only)
     Detection: InventoryLIFOReserve tag present in raw_facts
     Action:    LIFO_FLAG — affects COGS, inventory, all cycle metrics
     Adjustment: Add LIFO reserve to inventory balance for peer comparison

  2. IFRS 16 Lease Treatment
     Detection: IFRS filer (accounting_standard = 'IFRS')
     Action:    IFRS16_LEASE_ADJ — affects EBITDA, operating margin, ROIC
     Adjustment: EBITDA adjusted to operating-lease-equivalent basis

  3. R&D Capitalization (IFRS IAS 38)
     Detection: IntangibleAssetsFromDevelopment or similar capitalized dev tag
     Action:    IFRS_RD_CAP — affects R&D margin, R&D ratio, EBITDA
     No direct adjustment — flagged only; documented in completeness notes

  4. Asset Revaluation (IFRS IAS 16)
     Detection: RevaluationSurplus in equity section
     Action:    ASSET_REVAL_FLAG — affects ROA, RONE, Altman Z
     No direct adjustment — flagged only

  5. J-GAAP Structural Differences
     Detection: accounting_standard = 'J-GAAP'
     Action:    JGAAP_SGA_SPLIT (sum selling + G&A) and/or JGAAP_EXTRAORDINARY
     Adjustment: SG&A summed from separate line items where split
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ── Flag Definitions ──────────────────────────────────────────────────────────

# All 12 defined flag codes — matches DataFramework Section 6
FLAG_CODES = {
    "LIFO_FLAG":             "LIFO inventory method — cycle metrics adjusted",
    "IFRS16_LEASE_ADJ":      "EBITDA adjusted to operating-lease equivalent basis",
    "IFRS_RD_CAP":           "Development costs capitalized (IAS 38) — R&D understated",
    "ASSET_REVAL_FLAG":      "PP&E at fair value (IAS 16) — return ratios not comparable to GAAP",
    "JGAAP_EXTRAORDINARY":   "J-GAAP extraordinary items excluded for comparability",
    "JGAAP_SGA_SPLIT":       "J-GAAP SG&A summed from separate selling + G&A lines",
    "SPARSE_EMPLOYEES":      "Employee headcount not tagged — employee metrics unavailable",
    "SPARSE_INVENTORY_DETAIL": "Inventory sub-components not broken out — using total inventory",
    "ESTIMATE_FLAG":         "Value estimated — not from regulatory filing",
    "INCOMPLETE_PERIOD":     "TTM calculated from fewer than 4 quarters",
    "RESTATEMENT":           "Amended filing — prior period values updated",
    "LOW_COMPLETENESS":      "Completeness score below 40 — limited analysis",
}

# Severity levels by flag code
FLAG_SEVERITY = {
    "LIFO_FLAG":             "warning",
    "IFRS16_LEASE_ADJ":      "info",
    "IFRS_RD_CAP":           "warning",
    "ASSET_REVAL_FLAG":      "info",
    "JGAAP_EXTRAORDINARY":   "info",
    "JGAAP_SGA_SPLIT":       "info",
    "SPARSE_EMPLOYEES":      "warning",
    "SPARSE_INVENTORY_DETAIL": "warning",
    "ESTIMATE_FLAG":         "warning",
    "INCOMPLETE_PERIOD":     "warning",
    "RESTATEMENT":           "info",
    "LOW_COMPLETENESS":      "alert",
}


@dataclass
class AccountingContext:
    """
    Accounting context for a single company-period.
    Populated before metric calculation; used by the normalizer.
    """
    accounting_standard:    str             # US-GAAP | IFRS | J-GAAP | K-IFRS | TW-GAAP
    reporting_currency:     str             # ISO 4217
    fiscal_year_end_month:  int             # 1-12
    active_flags:           list[str]       = field(default_factory=list)

    # Detected values that inform adjustments
    lifo_reserve:           Optional[float] = None   # USD
    capitalized_dev_costs:  Optional[float] = None   # USD
    revaluation_surplus:    Optional[float] = None   # USD
    roa_asset_usd:          Optional[float] = None   # useful for ASSET_REVAL context

    def add_flag(self, flag_code: str):
        if flag_code not in self.active_flags:
            self.active_flags.append(flag_code)
            logger.debug("Flag added: %s", flag_code)

    def has_flag(self, flag_code: str) -> bool:
        return flag_code in self.active_flags


# ── Detection ─────────────────────────────────────────────────────────────────

def detect_lifo(raw_facts_by_tag: dict[str, float]) -> Optional[float]:
    """
    Detect LIFO inventory method and return LIFO reserve if present.

    LIFO reserve is the difference between LIFO and FIFO inventory value.
    Adding it back to LIFO inventory gives FIFO-equivalent inventory for
    peer comparison with IFRS companies.

    Returns:
        LIFO reserve in USD, or None if LIFO not detected.
    """
    lifo_tags = [
        "us-gaap:InventoryLIFOReserve",
        "us-gaap:ExcessOfReplacementOrCurrentCostsOverStatedLIFOValue",
    ]
    for tag in lifo_tags:
        if tag in raw_facts_by_tag:
            reserve = raw_facts_by_tag[tag]
            logger.info("LIFO reserve detected: $%.0f", reserve or 0)
            return reserve
    return None


def detect_rd_capitalization(raw_facts_by_tag: dict[str, float]) -> Optional[float]:
    """
    Detect capitalized development costs under IAS 38.

    Under IFRS, qualifying development costs are capitalized as intangible assets.
    This reduces reported R&D expense and creates an intangible asset on the B/S.
    Not possible under US-GAAP (all R&D expensed immediately).

    Returns:
        Capitalized development cost balance in USD, or None if not detected.
    """
    dev_tags = [
        "ifrs-full:CapitalisedDevelopmentExpenditureMember",
        "ifrs-full:DevelopmentAndRelatedExpenditureMember",
        "ifrs-full:InternallyGeneratedIntangibleAssetsMember",
    ]
    for tag in dev_tags:
        if tag in raw_facts_by_tag:
            value = raw_facts_by_tag[tag]
            logger.info("Capitalized development costs detected: $%.0f", value or 0)
            return value
    return None


def detect_asset_revaluation(raw_facts_by_tag: dict[str, float]) -> Optional[float]:
    """
    Detect PP&E revaluation surplus (IFRS IAS 16).

    Revaluation surplus appears in equity when assets are marked up to fair value.
    US-GAAP does not permit this — assets remain at historical cost.

    Returns:
        Revaluation surplus in USD, or None if not detected.
    """
    reval_tags = [
        "ifrs-full:RevaluationSurplus",
        "ifrs-full:RevaluationSurplusMember",
    ]
    for tag in reval_tags:
        if tag in raw_facts_by_tag:
            value = raw_facts_by_tag[tag]
            logger.info("Asset revaluation surplus detected: $%.0f", value or 0)
            return value
    return None


# ── EBITDA Adjustment: IFRS 16 ────────────────────────────────────────────────

def adjust_ebitda_ifrs16(
    ebitda_raw: float,
    lease_depreciation_usd: Optional[float],
    lease_interest_usd: Optional[float],
) -> tuple[float, bool]:
    """
    Adjust EBITDA for IFRS 16 lease treatment to produce an operating-lease
    equivalent value comparable to US-GAAP EBITDA.

    Under IFRS 16, all leases are treated as finance leases:
      - Lease payments split into: depreciation (above EBITDA) + interest (below EBIT)
      - EBITDA is HIGHER under IFRS 16 because the full lease payment
        appears below EBITDA (as depreciation + interest)

    To make IFRS EBITDA comparable to US-GAAP EBITDA (operating lease basis):
      Adjusted EBITDA = IFRS EBITDA - ROU asset depreciation - Lease interest

    Args:
        ebitda_raw:           EBITDA as calculated from IFRS filing.
        lease_depreciation_usd: ROU asset depreciation from IFRS notes.
        lease_interest_usd:   Interest on lease liabilities.

    Returns:
        Tuple of (adjusted_ebitda, was_adjusted: bool)
    """
    if lease_depreciation_usd is None and lease_interest_usd is None:
        return ebitda_raw, False

    adjustment = (lease_depreciation_usd or 0) + (lease_interest_usd or 0)
    adjusted = ebitda_raw - adjustment

    logger.debug(
        "IFRS 16 EBITDA adjustment: raw=%.0f adj=%.0f delta=%.0f",
        ebitda_raw, adjusted, adjustment
    )
    return adjusted, True


# ── J-GAAP: SG&A Split ────────────────────────────────────────────────────────

def sum_jgaap_sga(
    selling_expense: Optional[float],
    general_admin_expense: Optional[float],
) -> tuple[Optional[float], bool]:
    """
    Sum J-GAAP selling expenses and G&A expenses to produce combined SG&A.

    J-GAAP reports SG&A as two separate line items:
      - Selling Expenses (販売費)
      - General and Administrative Expenses (一般管理費)

    US-GAAP and IFRS typically report as a single SG&A line.
    We sum them and flag the operation.

    Returns:
        Tuple of (combined_sga, was_summed: bool)
        Returns (None, False) if both inputs are None.
    """
    if selling_expense is None and general_admin_expense is None:
        return None, False

    combined = (selling_expense or 0.0) + (general_admin_expense or 0.0)
    was_split = selling_expense is not None and general_admin_expense is not None
    return combined, was_split


# ── Context Builder ───────────────────────────────────────────────────────────

def build_accounting_context(
    accounting_standard: str,
    reporting_currency: str,
    fiscal_year_end_month: int,
    raw_facts_by_tag: dict[str, float],
) -> AccountingContext:
    """
    Build a fully populated AccountingContext for a company-period.

    Runs all detectors and populates flags based on what is found.

    Args:
        accounting_standard:   From companies.accounting_standard.
        reporting_currency:    ISO 4217 code.
        fiscal_year_end_month: Month number 1-12.
        raw_facts_by_tag:      Dict of {source_tag: value_usd} for this period.

    Returns:
        Populated AccountingContext ready for use by the metric engine.
    """
    ctx = AccountingContext(
        accounting_standard=accounting_standard,
        reporting_currency=reporting_currency,
        fiscal_year_end_month=fiscal_year_end_month,
    )

    # LIFO detection (US-GAAP only — but run for all to be safe)
    lifo_reserve = detect_lifo(raw_facts_by_tag)
    if lifo_reserve is not None:
        ctx.lifo_reserve = lifo_reserve
        ctx.add_flag("LIFO_FLAG")

    # IFRS-specific checks
    if accounting_standard == "IFRS":
        dev_costs = detect_rd_capitalization(raw_facts_by_tag)
        if dev_costs is not None:
            ctx.capitalized_dev_costs = dev_costs
            ctx.add_flag("IFRS_RD_CAP")

        reval = detect_asset_revaluation(raw_facts_by_tag)
        if reval is not None:
            ctx.revaluation_surplus = reval
            ctx.add_flag("ASSET_REVAL_FLAG")

        # IFRS 16 applies to all IFRS filers — flag by default
        # Adjustment requires lease_depreciation and lease_interest from notes
        ctx.add_flag("IFRS16_LEASE_ADJ")

    # J-GAAP structural differences
    if accounting_standard == "J-GAAP":
        # Check for extraordinary items tag
        extraordinary_tags = [
            "jpcrp:ExtraordinaryIncome",
            "jpcrp:ExtraordinaryLoss",
            "jpcrp:SpecialProfits",
            "jpcrp:SpecialLoss",
        ]
        if any(t in raw_facts_by_tag for t in extraordinary_tags):
            ctx.add_flag("JGAAP_EXTRAORDINARY")

        # Check for split SG&A
        if ("jpcrp:SellingExpenses" in raw_facts_by_tag or
                "jpcrp:GeneralAndAdministrativeExpense" in raw_facts_by_tag):
            ctx.add_flag("JGAAP_SGA_SPLIT")

    logger.debug(
        "Accounting context built: standard=%s flags=%s",
        accounting_standard, ctx.active_flags
    )
    return ctx
