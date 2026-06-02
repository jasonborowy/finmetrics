# FinMetrics

**Global financial intelligence built entirely on free public regulatory filings.**

FinMetrics calculates 55 standardized financial metrics for ~285 public companies across the global semiconductor sector and cross-sector benchmarks. All data sourced from primary regulatory filings — SEC EDGAR, ESMA ESEF, EDINET, DART, and TWSE. No paid data vendors. No API keys except where free registration is required.

## Live Links
- **Dashboard**: [finmetrics.vercel.app](https://finmetrics.vercel.app) *(coming Phase 1)*
- **Power BI Reports**: [Power BI Service](https://app.powerbi.com) *(coming Phase 2)*
- **API Docs**: [finmetrics-api.railway.app/docs](https://finmetrics-api.railway.app/docs) *(coming Phase 1)*

---

## Architecture

```
SEC EDGAR ──────────────────────────────────────┐
ESMA ESEF ────────────────────────────────────┐  │
EDINET (Japan) ─────────────────────────────┐  │  │   ┌─────────────────┐
DART (Korea) ─────────────────────────────┐  │  │  │   │   PostgreSQL    │
TWSE (Taiwan) ──────────────────────────┐  │  │  │  │   │                 │
                                         │  │  │  │  │   │  raw_facts      │
                          ┌──────────────▼──▼──▼──▼──▼─▶│  tag_mappings   │
                          │   Source Connectors          │  metrics        │
                          │   Tag Resolver               │  fx_rates       │
                          │   Normalization Layer        │  flags          │◀─── Power BI
                          │   FX Converter               │  companies      │     DirectQuery
                          │   Metric Engine  ────────────▶  completeness   │
                          └──────────────────────────────└────────┬────────┘
                                                                   │
                                                              FastAPI
                                                                   │
                                                           React Dashboard
```

---

## Repository Structure

```
finmetrics/
├── pipeline/
│   ├── connectors/          # One file per filing system
│   │   ├── edgar.py         # SEC EDGAR — US domestic + foreign ADRs
│   │   ├── esma.py          # ESMA ESEF — Europe (Phase 3)
│   │   ├── edinet.py        # EDINET — Japan (Phase 3)
│   │   ├── dart.py          # DART — South Korea (Phase 4)
│   │   └── twse.py          # TWSE — Taiwan (Phase 4)
│   ├── normalizers/
│   │   ├── tag_resolver.py  # Maps source tags → canonical names
│   │   ├── fx_converter.py  # USD normalization, period-accurate rates
│   │   ├── accounting.py    # IFRS/GAAP/J-GAAP adjustments + flags
│   │   └── ttm.py           # Trailing twelve months, fiscal-calendar aware
│   └── etl/
│       ├── orchestrator.py  # Coordinates full pipeline run per company
│       ├── scheduler.py     # SEC RSS watcher + earnings refresh trigger
│       └── loader.py        # Writes normalized data to PostgreSQL
├── database/
│   ├── schema/
│   │   ├── 001_core.sql     # All 8 tables — full DDL
│   │   └── 002_indexes.sql  # Performance indexes
│   └── migrations/          # Version-controlled schema changes
├── api/
│   └── main.py              # FastAPI application
├── tests/
│   ├── pipeline/
│   │   ├── test_edgar.py
│   │   ├── test_tag_resolver.py
│   │   └── test_metric_engine.py
│   └── database/
│       └── test_schema.py
├── docs/
│   ├── decisions/           # Architecture Decision Records (ADRs)
│   └── runbooks/            # Operational procedures
├── config/
│   ├── settings.py          # Environment config
│   ├── companies.json       # Company universe registry
│   └── tag_mappings.json    # Canonical tag mapping seed data
├── scripts/
│   ├── diagnose_edgar.py    # Pre-ETL diagnostic (HEMM pattern)
│   ├── verify_schema.py     # Schema verification tool
│   └── seed_companies.py    # Load company universe from registry
└── data/
    └── reference/
        └── cpi_bls.csv      # BLS CPI-U for real value calculations
```

---

## Metric Categories

| Category | Count | Examples |
|---|---|---|
| Growth | 14 | Revenue, R&D Margin, Employee Growth, Market Cap |
| Profitability | 17 | Gross Margin, EBITDA, Operating Margin, Free Cash Flow Ratio |
| Cycle | 14 | Cash-to-Cash, Days of Inventory, DSO, Inventory Turns |
| Complexity | 10 | Altman Z, ROIC, Current Ratio, Return on Equity |

Full definitions, formulas, and business decision context: see `Financial_Metrics_Reference.xlsx`

---

## Company Universe

- **~275 semiconductor companies** across 6 sub-sectors (Fabless, Foundry, IDM, Equipment, Materials, Packaging)
- **11 cross-sector benchmarks** — one market-cap leader per GICS sector
- **5 filing systems** — EDGAR (Phase 1–2), ESMA + EDINET (Phase 3), DART + TWSE (Phase 4)
- **4 accounting standards** — US-GAAP, IFRS, J-GAAP, K-IFRS

Full universe definition: see `FinMetrics_DataFramework.docx`

---

## Data Quality

Every metric carries a completeness score (0–100) and up to 12 data quality flags:

| Flag | Meaning |
|---|---|
| `LIFO_FLAG` | LIFO inventory method — cycle metrics adjusted |
| `IFRS16_LEASE_ADJ` | EBITDA adjusted to operating-lease equivalent |
| `IFRS_RD_CAP` | Development costs capitalized — R&D understated |
| `ASSET_REVAL_FLAG` | PP&E at fair value — return ratios differ from GAAP peers |
| `SPARSE_EMPLOYEES` | Employee headcount not tagged in filing |
| `SPARSE_INVENTORY_DETAIL` | Inventory sub-components unavailable |

Full flag registry: `FinMetrics_DataFramework.docx` Section 6

---

## Getting Started

### Prerequisites
- Python 3.11+
- PostgreSQL 16
- Node.js 20+ (for React dashboard)

### Local Setup

```bash
git clone https://github.com/yourusername/finmetrics.git
cd finmetrics
pip install -r requirements.txt
cp config/.env.example config/.env
# Edit config/.env — add your DB connection string
psql -d finmetrics_db -f database/schema/001_core.sql
psql -d finmetrics_db -f database/schema/002_indexes.sql
python scripts/seed_companies.py
python pipeline/etl/orchestrator.py --ticker NVDA --dry-run
```

---

## Development Standards

**Before writing any ETL code:**
1. Run the diagnostic script for the data source (`scripts/diagnose_edgar.py`)
2. Confirm column schema, era breaks, gap years, and unit conventions
3. Document findings in script header before writing ingest logic

This is the ETL workflow standard established in the HEMM model (Section 8.4). It prevents unit conversion errors, wrong column mappings, and silent data quality failures.

---

## Documentation

| Document | Location | Purpose |
|---|---|---|
| Product & Career Roadmap | `docs/FinMetrics_Roadmap_v2.docx` | Full build strategy |
| Global Scope & Data Framework | `docs/FinMetrics_DataFramework.docx` | Engineering specification |
| Metrics Reference | `docs/Financial_Metrics_Reference.xlsx` | All 55 metrics defined |
| Architecture Decisions | `docs/decisions/` | ADR log |
| Runbooks | `docs/runbooks/` | Operational procedures |

---

## Phase Status

| Phase | Description | Status |
|---|---|---|
| Phase 1 | EDGAR pipeline + React dashboard live (10 tickers) | 🔨 In Progress |
| Phase 2 | Insight layer + Power BI report suite | ⏳ Planned |
| Phase 3 | Scale to 230+ companies + EDINET + ESMA | ⏳ Planned |
| Phase 4 | DART + TWSE + Freemium SaaS | ⏳ Planned |

---

*Built by [Your Name] | All data from free public regulatory filings | SEC EDGAR · ESMA · EDINET · DART · TWSE*
