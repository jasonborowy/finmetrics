"""
FinMetrics — FX Converter
==========================
Converts monetary values to USD using period-accurate exchange rates.

Conversion rules (standard financial reporting practice):
  - Income statement items (P&L): period-AVERAGE rate
    Applied to: Revenue, COGS, Gross Profit, R&D, SG&A, Operating Income,
                Net Income, EBITDA, Operating Cash Flow, CapEx
  - Balance sheet items (B/S):   period-END rate
    Applied to: Cash, Inventory, Receivables, Payables, Total Assets,
                Equity, Debt, PP&E

Data sources (all free, no API keys):
  - ECB Statistical Data Warehouse: EUR and cross-rates
    https://data-api.ecb.europa.eu/service/data/EXR
  - Federal Reserve H.10 release: official USD rates
    https://www.federalreserve.gov/releases/h10/

Supported currencies: USD (no conversion), EUR, JPY, KRW, TWD

If a rate is unavailable for a specific date, the converter falls back to
the nearest available rate within a 7-day window and logs a warning.
"""

import logging
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


# ── Rate type determination ───────────────────────────────────────────────────

# Income statement tags — use period-average rate
INCOME_STATEMENT_TAGS = {
    "Revenue", "COGS", "GrossProfit", "RDExpense", "SGAExpense",
    "OperatingIncome", "NetIncome", "EBIT", "DA", "OperatingCashFlow",
    "CapEx", "PreTaxIncome", "OperatingExpenses",
}

# Balance sheet tags — use period-end rate
BALANCE_SHEET_TAGS = {
    "Cash", "Inventory", "FinishedGoodsInventory", "RawMaterialsInventory",
    "WIPInventory", "AccountsReceivable", "AccountsPayable", "TotalAssets",
    "CurrentAssets", "CurrentLiabilities", "TotalEquity", "LongTermDebt",
    "ShortTermDebt", "RetainedEarnings", "PPENet", "ShortTermInvestments",
    "CommonSharesOutstanding",
}


def rate_type_for_canonical(canonical_tag: str) -> str:
    """
    Return 'period_average' or 'period_end' for a canonical metric name.
    Defaults to 'period_average' for unrecognized tags (conservative choice).
    """
    if canonical_tag in BALANCE_SHEET_TAGS:
        return "period_end"
    return "period_average"


# ── FX Rate Store ─────────────────────────────────────────────────────────────

class FxRateStore:
    """
    In-memory store of exchange rates.
    Populated from the fx_rates database table at pipeline startup.

    Rates are stored as: {(from_currency, rate_date): rate}
    All rates are to USD (to_currency always USD).
    """

    def __init__(self):
        # {(from_currency: str, rate_date: date): rate: float}
        self._rates: dict[tuple[str, date], float] = {}
        self._loaded_currencies: set[str] = set()

    def add_rate(self, from_currency: str, rate_date: date, rate: float):
        """Add a single rate to the store."""
        self._rates[(from_currency.upper(), rate_date)] = rate
        self._loaded_currencies.add(from_currency.upper())

    def add_rates_bulk(self, rates: list[dict]):
        """
        Bulk load rates from database query results.

        Args:
            rates: List of dicts with keys: from_currency, rate_date, rate
        """
        for r in rates:
            self.add_rate(r["from_currency"], r["rate_date"], r["rate"])
        logger.info(
            "FxRateStore loaded %d rates for currencies: %s",
            len(rates), sorted(self._loaded_currencies)
        )

    def get_rate(
        self,
        from_currency: str,
        target_date: date,
        fallback_window_days: int = 7,
    ) -> Optional[float]:
        """
        Get exchange rate for a currency on a specific date.
        If exact date not found, searches within fallback_window_days.

        Args:
            from_currency:       Source currency code (e.g. 'JPY').
            target_date:         Date of the rate needed.
            fallback_window_days: Look within this window if exact date missing.

        Returns:
            Exchange rate (units of from_currency per 1 USD), or None if not found.
        """
        currency = from_currency.upper()

        if currency == "USD":
            return 1.0

        # Try exact date first
        exact = self._rates.get((currency, target_date))
        if exact is not None:
            return exact

        # Fallback: search within window
        for delta in range(1, fallback_window_days + 1):
            for d in [target_date - timedelta(days=delta),
                      target_date + timedelta(days=delta)]:
                rate = self._rates.get((currency, d))
                if rate is not None:
                    logger.debug(
                        "FX rate for %s on %s not found; using %s (±%d days)",
                        currency, target_date, d, delta
                    )
                    return rate

        logger.warning(
            "No FX rate found for %s within %d days of %s",
            currency, fallback_window_days, target_date
        )
        return None

    def period_average_rate(
        self,
        from_currency: str,
        period_start: date,
        period_end: date,
    ) -> Optional[float]:
        """
        Calculate the average rate over a period.
        Used for income statement items.

        Collects all available daily rates between period_start and period_end
        and returns their simple average. If fewer than 5 rates are found,
        logs a warning (sparse data may indicate a coverage gap).

        Args:
            from_currency: Source currency.
            period_start:  First day of the period.
            period_end:    Last day of the period.

        Returns:
            Average rate, or None if no rates found.
        """
        currency = from_currency.upper()

        if currency == "USD":
            return 1.0

        rates = []
        current = period_start
        while current <= period_end:
            rate = self._rates.get((currency, current))
            if rate is not None:
                rates.append(rate)
            current += timedelta(days=1)

        if not rates:
            # Fall back to period-end rate if no daily rates in range
            logger.warning(
                "No daily rates for %s between %s and %s; falling back to period-end rate",
                currency, period_start, period_end
            )
            return self.get_rate(currency, period_end)

        if len(rates) < 5:
            logger.warning(
                "Only %d rate(s) found for %s in period %s–%s; average may be unreliable",
                len(rates), currency, period_start, period_end
            )

        return sum(rates) / len(rates)


# ── Conversion ────────────────────────────────────────────────────────────────

class FxConverter:
    """
    Converts raw fact values to USD using period-appropriate FX rates.

    Usage:
        converter = FxConverter(rate_store)
        usd_value, rate_used, rate_type = converter.convert(
            value=100_000_000,
            from_currency="JPY",
            canonical_tag="Revenue",
            period_start=date(2024, 1, 1),
            period_end=date(2024, 3, 31),
        )
    """

    def __init__(self, rate_store: FxRateStore):
        self.store = rate_store

    def convert(
        self,
        value: float,
        from_currency: str,
        canonical_tag: str,
        period_end: date,
        period_start: Optional[date] = None,
    ) -> tuple[Optional[float], Optional[float], str]:
        """
        Convert a value to USD.

        Args:
            value:          Numeric value in source currency.
            from_currency:  Source currency ISO code.
            canonical_tag:  Canonical metric name (determines rate type).
            period_end:     End of reporting period.
            period_start:   Start of reporting period (for P&L averaging).

        Returns:
            Tuple of (usd_value, rate_used, rate_type_used)
            usd_value is None if no rate available.
        """
        if from_currency.upper() == "USD":
            return value, 1.0, "no_conversion"

        rate_type = rate_type_for_canonical(canonical_tag)

        if rate_type == "period_average" and period_start:
            rate = self.store.period_average_rate(from_currency, period_start, period_end)
        else:
            rate = self.store.get_rate(from_currency, period_end)
            rate_type = "period_end"

        if rate is None:
            return None, None, rate_type

        # Rate is stored as units of foreign currency per 1 USD
        # So: usd_value = foreign_value / rate
        usd_value = value / rate
        return usd_value, rate, rate_type


# ── Module-level instances ─────────────────────────────────────────────────────
rate_store = FxRateStore()
converter  = FxConverter(rate_store)
