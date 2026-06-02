-- FinMetrics Core Database Schema
-- =================================
-- Run against finmetrics_db in order:
--   psql -d finmetrics_db -f database/schema/001_core.sql
--   psql -d finmetrics_db -f database/schema/002_indexes.sql
--
-- Version:  1.0
-- Date:     2026-06
-- Notes:    All monetary values stored in USD.
--           Source currency and FX rate recorded for audit trail.
--           JSONB used for accounting_flags — expandable without schema change.

-- ── Extensions ────────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";   -- fuzzy text search on company names

-- ── Enumerations ──────────────────────────────────────────────────────────────
CREATE TYPE filing_system_type AS ENUM (
    'EDGAR', 'ESMA', 'EDINET', 'DART', 'TWSE'
);

CREATE TYPE accounting_standard_type AS ENUM (
    'US-GAAP', 'IFRS', 'J-GAAP', 'K-IFRS', 'TW-GAAP'
);

CREATE TYPE period_type AS ENUM (
    'quarterly', 'annual', 'ttm'
);

CREATE TYPE fact_period_type AS ENUM (
    'instant',    -- balance sheet items: value at a point in time
    'duration'    -- income statement items: value over a period
);

CREATE TYPE flag_type AS ENUM (
    'threshold', 'trend', 'anomaly', 'data_quality'
);

CREATE TYPE flag_severity AS ENUM (
    'info', 'warning', 'alert', 'critical'
);

CREATE TYPE inventory_method_type AS ENUM (
    'FIFO', 'LIFO', 'WeightedAvg', 'Unknown'
);

-- ── DIMENSION: companies ──────────────────────────────────────────────────────
CREATE TABLE companies (
    company_id          UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Filing system identifiers
    ticker              VARCHAR(20) NOT NULL,
    cik                 VARCHAR(12),          -- EDGAR only; zero-padded 10 digits
    edinet_code         VARCHAR(10),          -- Japan EDINET E-code
    dart_code           VARCHAR(10),          -- Korea DART corp_code
    twse_code           VARCHAR(10),          -- Taiwan TWSE stock code
    esma_lei            VARCHAR(20),          -- Europe LEI identifier

    -- Core company data
    name                VARCHAR(300) NOT NULL,
    country             CHAR(2)      NOT NULL, -- ISO 3166-1 alpha-2
    reporting_currency  CHAR(3)      NOT NULL, -- ISO 4217
    accounting_standard accounting_standard_type NOT NULL,
    fiscal_year_end     CHAR(5)      NOT NULL, -- MM-DD format e.g. '12-31', '03-31'
    filing_system       filing_system_type NOT NULL,

    -- Classification
    gics_sector         VARCHAR(100),
    gics_industry       VARCHAR(100),
    semi_sub_sector     VARCHAR(50),  -- Fabless | Foundry | IDM | Equipment | Materials | Packaging
    sic_code            VARCHAR(10),

    -- FinMetrics flags
    is_benchmark        BOOLEAN     NOT NULL DEFAULT FALSE, -- cross-sector benchmark company
    is_active           BOOLEAN     NOT NULL DEFAULT TRUE,
    phase_available     SMALLINT    NOT NULL DEFAULT 1,     -- pipeline phase when data becomes available

    -- Audit
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT companies_ticker_unique UNIQUE (ticker),
    CONSTRAINT companies_cik_unique    UNIQUE (cik),
    CONSTRAINT companies_fy_end_format CHECK (fiscal_year_end ~ '^\d{2}-\d{2}$')
);

COMMENT ON TABLE  companies                   IS 'Master company registry. One row per company. Links to all filing system identifiers.';
COMMENT ON COLUMN companies.cik               IS 'SEC Central Index Key, zero-padded to 10 digits. EDGAR companies only.';
COMMENT ON COLUMN companies.fiscal_year_end   IS 'Fiscal year end as MM-DD. Used for TTM calculation calendar alignment.';
COMMENT ON COLUMN companies.is_benchmark      IS 'TRUE for 11 cross-sector benchmark companies (one per GICS sector).';
COMMENT ON COLUMN companies.phase_available   IS 'Pipeline phase in which this company becomes available: 1=EDGAR, 2=ADRs, 3=EDINET/ESMA, 4=DART/TWSE.';


-- ── FACT: raw_facts ───────────────────────────────────────────────────────────
CREATE TABLE raw_facts (
    fact_id             UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id          UUID        NOT NULL REFERENCES companies(company_id),

    -- XBRL tag information
    source_tag          VARCHAR(200) NOT NULL,  -- original tag e.g. 'us-gaap:Revenues'
    taxonomy            VARCHAR(20)  NOT NULL,  -- us-gaap | ifrs-full | jpcrp | k-ifrs | tw-ifrs
    canonical_tag       VARCHAR(100),           -- resolved canonical name e.g. 'Revenue'

    -- Value
    value               NUMERIC(20, 4) NOT NULL,   -- raw value in reporting currency
    value_usd           NUMERIC(20, 4),             -- USD-normalized value
    unit                VARCHAR(20)  NOT NULL,       -- USD | JPY | EUR | KRW | TWD | shares | pure

    -- FX tracking
    fx_rate             NUMERIC(12, 6),             -- rate used for USD conversion
    fx_rate_type        VARCHAR(20),                -- period_average | period_end
    fx_rate_date        DATE,                       -- date of FX rate used

    -- Temporal
    period_start        DATE,                        -- duration facts only (income statement)
    period_end          DATE        NOT NULL,        -- all facts — primary temporal key
    period_type         fact_period_type NOT NULL,
    fiscal_year         SMALLINT,
    fiscal_quarter      SMALLINT    CHECK (fiscal_quarter BETWEEN 1 AND 4),

    -- Filing provenance — full audit trail to source document
    form_type           VARCHAR(20) NOT NULL,        -- 10-K | 10-Q | 20-F | Yuho | etc.
    accession           VARCHAR(50),                 -- EDGAR accession number or equivalent
    filing_date         DATE,
    is_restated         BOOLEAN     NOT NULL DEFAULT FALSE,

    -- Quality
    data_quality_score  SMALLINT    CHECK (data_quality_score BETWEEN 0 AND 100),

    -- Audit
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT raw_facts_no_future_period CHECK (period_end <= CURRENT_DATE + INTERVAL '90 days')
);

COMMENT ON TABLE  raw_facts                  IS 'Every XBRL-tagged value as filed. Never modified after insert. Source of truth.';
COMMENT ON COLUMN raw_facts.source_tag       IS 'Original XBRL tag including namespace prefix.';
COMMENT ON COLUMN raw_facts.canonical_tag    IS 'Resolved canonical metric name from tag_mappings. NULL if unresolved.';
COMMENT ON COLUMN raw_facts.value            IS 'Raw value in original reporting currency. Never converted here.';
COMMENT ON COLUMN raw_facts.value_usd        IS 'USD-normalized value using period-appropriate FX rate.';
COMMENT ON COLUMN raw_facts.is_restated      IS 'TRUE if this value supersedes a previously filed value for the same period.';


-- ── REFERENCE: tag_mappings ───────────────────────────────────────────────────
CREATE TABLE tag_mappings (
    mapping_id          SERIAL      PRIMARY KEY,
    canonical_name      VARCHAR(100) NOT NULL,  -- e.g. 'Revenue'
    taxonomy            VARCHAR(20)  NOT NULL,  -- us-gaap | ifrs-full | jpcrp | k-ifrs | tw-ifrs
    source_tag          VARCHAR(200) NOT NULL,  -- e.g. 'Revenues'
    priority            SMALLINT     NOT NULL DEFAULT 1,  -- 1=try first, higher=fallback
    notes               TEXT,

    CONSTRAINT tag_mappings_unique UNIQUE (canonical_name, taxonomy, source_tag)
);

COMMENT ON TABLE  tag_mappings              IS 'Canonical normalization table. Maps every source XBRL tag to a canonical metric name. ~825 entries across 55 metrics × 5 taxonomies × ~3 synonyms. This is the core IP of the normalization layer.';
COMMENT ON COLUMN tag_mappings.priority     IS 'Tag resolution priority within a taxonomy. 1 = try first; higher numbers are fallbacks.';


-- ── FACT: metrics ─────────────────────────────────────────────────────────────
CREATE TABLE metrics (
    metric_id           UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id          UUID        NOT NULL REFERENCES companies(company_id),
    period_end          DATE        NOT NULL,
    period_type         period_type NOT NULL,

    -- ── GROWTH (14 metrics) ───────────────────────────────────────────────────
    revenue_usd                 NUMERIC(20, 4),
    revenue_growth_yoy          NUMERIC(10, 6),   -- decimal e.g. 0.12 = 12%
    revenue_ttm_usd             NUMERIC(20, 4),
    revenue_ttm_growth_yoy      NUMERIC(10, 6),
    employees                   INTEGER,
    employee_growth_yoy         NUMERIC(10, 6),
    shares_outstanding          BIGINT,
    rd_expense_usd              NUMERIC(20, 4),
    rd_margin                   NUMERIC(10, 6),
    rd_ratio                    NUMERIC(10, 6),
    rd_to_cogs_ratio            NUMERIC(10, 6),
    sga_expense_usd             NUMERIC(20, 4),
    sga_margin                  NUMERIC(10, 6),
    sga_ratio                   NUMERIC(10, 6),
    sga_to_cogs_ratio           NUMERIC(10, 6),

    -- ── PROFITABILITY (17 metrics) ────────────────────────────────────────────
    cash_usd                    NUMERIC(20, 4),
    cash_change_usd             NUMERIC(20, 4),
    cash_ratio_ttm              NUMERIC(10, 6),
    cash_ratio_quarter          NUMERIC(10, 6),
    cash_ratio_year             NUMERIC(10, 6),
    cogs_usd                    NUMERIC(20, 4),
    gross_profit_usd            NUMERIC(20, 4),
    gross_margin                NUMERIC(10, 6),
    ebitda_usd                  NUMERIC(20, 4),
    ebitda_margin               NUMERIC(10, 6),
    free_cash_flow_usd          NUMERIC(20, 4),
    free_cash_flow_ratio        NUMERIC(10, 6),
    net_income_usd              NUMERIC(20, 4),
    net_profit_margin           NUMERIC(10, 6),
    operating_income_usd        NUMERIC(20, 4),
    operating_margin            NUMERIC(10, 6),
    opex_ratio                  NUMERIC(10, 6),
    pretax_margin               NUMERIC(10, 6),
    operating_cash_flow_usd     NUMERIC(20, 4),
    operating_cash_flow_ratio   NUMERIC(10, 6),

    -- ── CYCLE (14 metrics) ────────────────────────────────────────────────────
    inventory_usd               NUMERIC(20, 4),
    finished_goods_usd          NUMERIC(20, 4),
    raw_materials_usd           NUMERIC(20, 4),
    wip_usd                     NUMERIC(20, 4),
    inventory_turns             NUMERIC(10, 4),
    receivables_turns           NUMERIC(10, 4),
    days_inventory              NUMERIC(10, 2),
    days_sales_outstanding      NUMERIC(10, 2),
    days_payables_outstanding   NUMERIC(10, 2),
    days_finished_goods         NUMERIC(10, 2),
    days_raw_materials          NUMERIC(10, 2),
    days_wip                    NUMERIC(10, 2),
    cash_to_cash                NUMERIC(10, 2),   -- DIO + DSO - DPO
    dpo_dso_ratio               NUMERIC(10, 4),

    -- ── COMPLEXITY (10 metrics) ───────────────────────────────────────────────
    current_ratio               NUMERIC(10, 4),
    quick_ratio                 NUMERIC(10, 4),
    working_capital_ratio       NUMERIC(10, 4),
    return_on_assets            NUMERIC(10, 6),
    return_on_equity            NUMERIC(10, 6),
    return_on_invested_capital  NUMERIC(10, 6),
    return_on_net_assets        NUMERIC(10, 6),
    capital_turnover            NUMERIC(10, 4),
    altman_z                    NUMERIC(10, 4),
    revenue_per_employee        NUMERIC(20, 4),

    -- ── DATA QUALITY & FLAGS ──────────────────────────────────────────────────
    completeness_score          SMALLINT    CHECK (completeness_score BETWEEN 0 AND 100),
    accounting_flags            JSONB       NOT NULL DEFAULT '[]'::JSONB,

    -- Specific flag columns for Power BI filtering (denormalized from JSONB)
    flag_lifo                   BOOLEAN     NOT NULL DEFAULT FALSE,
    flag_ifrs16_lease_adj       BOOLEAN     NOT NULL DEFAULT FALSE,
    flag_ifrs_rd_cap            BOOLEAN     NOT NULL DEFAULT FALSE,
    flag_asset_reval            BOOLEAN     NOT NULL DEFAULT FALSE,
    flag_jgaap_extraordinary    BOOLEAN     NOT NULL DEFAULT FALSE,
    flag_jgaap_sga_split        BOOLEAN     NOT NULL DEFAULT FALSE,
    flag_sparse_employees       BOOLEAN     NOT NULL DEFAULT FALSE,
    flag_sparse_inventory       BOOLEAN     NOT NULL DEFAULT FALSE,
    flag_incomplete_period      BOOLEAN     NOT NULL DEFAULT FALSE,
    flag_restatement            BOOLEAN     NOT NULL DEFAULT FALSE,

    inventory_method            inventory_method_type NOT NULL DEFAULT 'Unknown',
    ebitda_lease_adjusted       BOOLEAN     NOT NULL DEFAULT FALSE,
    rd_capitalized              BOOLEAN     NOT NULL DEFAULT FALSE,

    -- Audit
    calculated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    pipeline_version            VARCHAR(20),   -- git commit hash or version tag

    CONSTRAINT metrics_unique_period UNIQUE (company_id, period_end, period_type)
);

COMMENT ON TABLE  metrics                        IS 'All 55 calculated metrics, one row per company per period. Rebuilt on every pipeline refresh. Never manually edited.';
COMMENT ON COLUMN metrics.accounting_flags       IS 'JSONB array of active flag codes e.g. ["LIFO_FLAG", "IFRS16_LEASE_ADJ"]. Use denormalized flag_ columns for Power BI filtering.';
COMMENT ON COLUMN metrics.completeness_score     IS '0-100: percentage of 55 metrics successfully calculated. Below 40 = insufficient for full analysis.';
COMMENT ON COLUMN metrics.pipeline_version       IS 'Git commit hash of pipeline version that produced this row. Enables reproducibility and rollback.';


-- ── REFERENCE: fx_rates ───────────────────────────────────────────────────────
CREATE TABLE fx_rates (
    rate_id             SERIAL      PRIMARY KEY,
    from_currency       CHAR(3)     NOT NULL,   -- JPY | EUR | KRW | TWD
    to_currency         CHAR(3)     NOT NULL DEFAULT 'USD',
    rate_date           DATE        NOT NULL,
    rate                NUMERIC(12, 6) NOT NULL,
    rate_type           VARCHAR(20) NOT NULL,   -- daily | weekly | monthly
    source              VARCHAR(50) NOT NULL,   -- ECB | FederalReserve | OpenExchangeRates

    CONSTRAINT fx_rates_unique UNIQUE (from_currency, to_currency, rate_date, source)
);

COMMENT ON TABLE  fx_rates             IS 'Period-accurate exchange rates for USD normalization. P&L items use period-average; B/S items use period-end. Multiple sources cross-validate.';


-- ── FACT: flags ───────────────────────────────────────────────────────────────
CREATE TABLE flags (
    flag_id             UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id          UUID        NOT NULL REFERENCES companies(company_id),
    metric_name         VARCHAR(100) NOT NULL,
    flag_type           flag_type   NOT NULL,
    severity            flag_severity NOT NULL,
    triggered_value     NUMERIC(20, 6),
    threshold_value     NUMERIC(20, 6),
    period_end          DATE        NOT NULL,
    flag_message        TEXT        NOT NULL,
    consecutive_periods SMALLINT    DEFAULT 1,
    resolved_at         TIMESTAMPTZ,            -- NULL = still active
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  flags                    IS 'Threshold alerts and trend anomalies. Written by flag engine after every pipeline refresh.';
COMMENT ON COLUMN flags.consecutive_periods IS 'Number of consecutive periods this flag has been triggered. Used for trend alerts e.g. DSO rising 3 quarters.';
COMMENT ON COLUMN flags.resolved_at         IS 'Timestamp when flag was cleared. NULL means currently active.';


-- ── OPERATIONAL: filing_log ───────────────────────────────────────────────────
CREATE TABLE filing_log (
    log_id              SERIAL      PRIMARY KEY,
    company_id          UUID        REFERENCES companies(company_id),
    ticker              VARCHAR(20),
    filing_system       filing_system_type,
    form_type           VARCHAR(20),
    period_end          DATE,
    accession           VARCHAR(50),
    status              VARCHAR(20) NOT NULL,   -- fetched | parsed | loaded | failed | skipped
    rows_loaded         INTEGER     DEFAULT 0,
    error_message       TEXT,
    duration_ms         INTEGER,                -- pipeline step duration in milliseconds
    run_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE filing_log IS 'Audit trail for every pipeline run. Records status, row counts, errors, and timing for every filing processed.';


-- ── OPERATIONAL: completeness_scores ─────────────────────────────────────────
CREATE TABLE completeness_scores (
    score_id            SERIAL      PRIMARY KEY,
    company_id          UUID        NOT NULL REFERENCES companies(company_id),
    period_end          DATE        NOT NULL,
    total_metrics       SMALLINT    NOT NULL DEFAULT 55,
    populated_metrics   SMALLINT    NOT NULL DEFAULT 0,
    score               SMALLINT    GENERATED ALWAYS AS
                            (ROUND(populated_metrics::NUMERIC / total_metrics * 100)::SMALLINT)
                            STORED,
    missing_metrics     JSONB       NOT NULL DEFAULT '[]'::JSONB,
    calculated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT completeness_unique UNIQUE (company_id, period_end)
);

COMMENT ON TABLE  completeness_scores             IS 'Per-company data quality summary. Generated score = populated / total × 100. missing_metrics lists which of the 55 metrics could not be calculated.';


-- ── TRIGGERS: updated_at maintenance ─────────────────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER companies_updated_at
    BEFORE UPDATE ON companies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
