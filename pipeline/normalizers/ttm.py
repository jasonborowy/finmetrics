"""
FinMetrics — TTM Calculator
=============================
Calculates trailing twelve months (TTM) values for flow metrics
(income statement items, cash flow items).

TTM = sum of the most recent 4 fiscal quarters.

Key complexity: fiscal year calendar alignment.
Not all companies end their fiscal year in December. Examples:
  - Apple:        September 30
  - Samsung:      December 31
  - Murata (JP):  March 31
  - TSMC:         December 31
  - SK Hynix:     December 31

The TTM calculator is fiscal-calendar-aware:
  1. Identifies the 4 most recent non-overlapping quarters
  2. Verifies they form a complete 12-month period
  3. Flags INCOMPLETE_PERIOD if fewer than 4 quarters available
  4. Returns None for TTM if the period is incomplete and flag_incomplete=False

Only flow metrics can be TTM-averaged. Stock metrics (balance sheet) use
the most recent point-in-time value — never TTM.

Stock metrics (period-end, no TTM):
  Cash, Inventory, Receivables, Payables, Total Assets, Equity, Debt, PP&E

Flow metrics (can be TTM):
  Revenue, COGS, Gross Profit, R&D, SG&A, Operating Income, Net Income,
  EBITDA, Operating Cash Flow, CapEx, D&A
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


# ── Flow vs Stock classification ──────────────────────────────────────────────

FLOW_METRICS = {
    "Revenue", "COGS", "GrossProfit", "RDExpense", "SGAExpense",
    "OperatingIncome", "NetIncome", "EBIT", "DA", "OperatingCashFlow",
    "CapEx", "PreTaxIncome", "OperatingExpenses",
}

STOCK_METRICS = {
    "Cash", "Inventory", "FinishedGoodsInventory", "RawMaterialsInventory",
    "WIPInventory", "AccountsReceivable", "AccountsPayable", "TotalAssets",
    "CurrentAssets", "CurrentLiabilities", "TotalEquity", "LongTermDebt",
    "ShortTermDebt", "RetainedEarnings", "PPENet", "ShortTermInvestments",
    "CommonSharesOutstanding", "Employees",
}


def is_flow_metric(canonical_tag: str) -> bool:
    """Return True if this metric is a flow (P&L) item suitable for TTM."""
    return canonical_tag in FLOW_METRICS


@dataclass
class QuarterRecord:
    """A single quarterly fact value."""
    period_end:   date
    period_start: Optional[date]
    value_usd:    float
    fiscal_year:  Optional[int]
    fiscal_quarter: Optional[int]
    form_type:    str

    @property
    def days_in_period(self) -> int:
        if self.period_start:
            return (self.period_end - self.period_start).days + 1
        return 91  # assume ~91 days if no start date

    @property
    def is_quarterly(self) -> bool:
        """True if this looks like a quarterly (not annual) record."""
        return self.days_in_period < 200


# ── TTM Calculation ───────────────────────────────────────────────────────────

class TTMCalculator:
    """
    Calculates trailing twelve months values from a series of quarterly records.

    Usage:
        calc = TTMCalculator()
        ttm_value, is_complete, quarters_used = calc.calculate(
            quarterly_records=records,
            as_of_date=date(2024, 12, 31),
        )
    """

    def calculate(
        self,
        quarterly_records: list[QuarterRecord],
        as_of_date: Optional[date] = None,
        require_complete: bool = True,
    ) -> tuple[Optional[float], bool, int]:
        """
        Calculate TTM value from a list of quarterly records.

        Args:
            quarterly_records:  All available quarterly records for the metric.
            as_of_date:         Calculate TTM as of this date. Default: most recent period.
            require_complete:   If True, return None when fewer than 4 quarters available.

        Returns:
            Tuple of (ttm_value, is_complete, quarters_used)
            ttm_value is None if incomplete and require_complete=True.
        """
        # Filter to quarterly records only (not annual)
        quarters = [r for r in quarterly_records if r.is_quarterly]

        if not quarters:
            logger.debug("No quarterly records available for TTM")
            return None, False, 0

        # Sort by period end, most recent first
        quarters = sorted(quarters, key=lambda r: r.period_end, reverse=True)

        # If as_of_date specified, filter to records on or before that date
        if as_of_date:
            quarters = [q for q in quarters if q.period_end <= as_of_date]

        if not quarters:
            return None, False, 0

        # Select 4 most recent non-overlapping quarters
        selected = self._select_non_overlapping(quarters, n=4)

        is_complete = len(selected) == 4
        quarters_used = len(selected)

        if not selected:
            return None, False, 0

        if not is_complete and require_complete:
            logger.debug(
                "Incomplete TTM: only %d quarters available (need 4)", quarters_used
            )
            return None, False, quarters_used

        # Verify selected quarters span approximately 12 months
        if is_complete:
            span_days = (selected[0].period_end - selected[-1].period_end).days
            if span_days < 270 or span_days > 400:
                logger.warning(
                    "TTM quarters span %d days — may not represent 12 months", span_days
                )

        ttm_value = sum(q.value_usd for q in selected)
        logger.debug(
            "TTM calculated from %d quarters: %.0f", quarters_used, ttm_value
        )
        return ttm_value, is_complete, quarters_used

    def _select_non_overlapping(
        self, sorted_quarters: list[QuarterRecord], n: int
    ) -> list[QuarterRecord]:
        """
        Select up to n non-overlapping quarters from a sorted (desc) list.

        Two quarters overlap if their date ranges intersect. We skip a quarter
        if it would double-count any days already covered.
        """
        selected = []
        covered_end = None

        for quarter in sorted_quarters:
            if len(selected) >= n:
                break

            # First quarter — always include
            if covered_end is None:
                selected.append(quarter)
                covered_end = quarter.period_start or (quarter.period_end - timedelta(days=90))
                continue

            # Check for overlap: this quarter must end before our coverage starts
            quarter_end = quarter.period_end
            if quarter_end < covered_end:
                selected.append(quarter)
                covered_end = quarter.period_start or (quarter_end - timedelta(days=90))

        return selected

    def ttm_growth_rate(
        self,
        current_records: list[QuarterRecord],
        prior_records: list[QuarterRecord],
        as_of_date: Optional[date] = None,
    ) -> Optional[float]:
        """
        Calculate year-over-year TTM growth rate.

        Args:
            current_records: Records for the current TTM period.
            prior_records:   Records for the prior TTM period (same metric, prior year).
            as_of_date:      Calculate as of this date.

        Returns:
            Growth rate as decimal (e.g. 0.12 = 12% growth), or None.
        """
        current_ttm, complete_c, _ = self.calculate(current_records, as_of_date)
        if not complete_c or current_ttm is None:
            return None

        # Prior year as of 12 months ago
        prior_date = (as_of_date - timedelta(days=365)) if as_of_date else None
        prior_ttm, complete_p, _ = self.calculate(prior_records, prior_date)
        if not complete_p or prior_ttm is None or prior_ttm == 0:
            return None

        return (current_ttm - prior_ttm) / abs(prior_ttm)


# ── Module-level singleton ────────────────────────────────────────────────────
ttm_calculator = TTMCalculator()
