# ADR-003: FX Conversion Strategy

**Date:** 2026-06  
**Status:** Accepted  

---

## Context

Companies report in local currencies (JPY, EUR, KRW, TWD). All FinMetrics output is in USD. FX conversion must be period-accurate — using a single spot rate introduces systematic error.

Standard financial reporting practice:
- Income statement items: translated at **period-average** rate
- Balance sheet items: translated at **period-end** rate

This matches FASB ASC 830 and IAS 21 translation guidance.

## Decision

- **Period-average for P&L:** Revenue, COGS, Gross Profit, R&D, SG&A, Operating Income, Net Income, EBITDA, Operating Cash Flow, CapEx
- **Period-end for B/S:** Cash, Inventory, Receivables, Payables, Total Assets, Equity, Debt, PP&E

FX data sources (all free):
- ECB Statistical Data Warehouse: `data-api.ecb.europa.eu` — EUR and cross rates
- Federal Reserve H.10: official USD rates for TWD
- Rates stored in `fx_rates` table with source attribution

Fallback: if exact date not available, search within ±7 days and log warning.

## Consequences

- `fx_rates` table must be populated before pipeline runs for non-USD companies
- FX rate and rate_type stored alongside every `raw_facts.value_usd` for audit
- IFRS 16 lease adjustment (EBITDA normalization) also requires FX-converted lease data
- Rate source logged per fact — enables cross-validation and error detection
