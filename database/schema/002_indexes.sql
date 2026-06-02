-- FinMetrics Performance Indexes
-- ================================
-- Run after 001_core.sql.
-- Optimized for:
--   1. Pipeline writes (insert speed)
--   2. API reads (ticker lookup, period range queries)
--   3. Power BI DirectQuery (cross-company, cross-period aggregations)

-- ── companies ─────────────────────────────────────────────────────────────────
CREATE INDEX idx_companies_ticker         ON companies(ticker);
CREATE INDEX idx_companies_cik            ON companies(cik) WHERE cik IS NOT NULL;
CREATE INDEX idx_companies_filing_system  ON companies(filing_system);
CREATE INDEX idx_companies_gics_sector    ON companies(gics_sector);
CREATE INDEX idx_companies_semi_subsector ON companies(semi_sub_sector);
CREATE INDEX idx_companies_is_benchmark   ON companies(is_benchmark) WHERE is_benchmark = TRUE;
CREATE INDEX idx_companies_name_trgm      ON companies USING gin(name gin_trgm_ops);  -- fuzzy search

-- ── raw_facts ─────────────────────────────────────────────────────────────────
CREATE INDEX idx_raw_facts_company_period ON raw_facts(company_id, period_end DESC);
CREATE INDEX idx_raw_facts_canonical_tag  ON raw_facts(canonical_tag) WHERE canonical_tag IS NOT NULL;
CREATE INDEX idx_raw_facts_period_end     ON raw_facts(period_end DESC);
CREATE INDEX idx_raw_facts_form_type      ON raw_facts(form_type);
CREATE INDEX idx_raw_facts_fiscal         ON raw_facts(fiscal_year, fiscal_quarter);

-- ── tag_mappings ──────────────────────────────────────────────────────────────
CREATE INDEX idx_tag_mappings_canonical   ON tag_mappings(canonical_name, taxonomy, priority);
CREATE INDEX idx_tag_mappings_source      ON tag_mappings(source_tag, taxonomy);

-- ── metrics ───────────────────────────────────────────────────────────────────
-- Primary access patterns: by company+period, by period across companies
CREATE INDEX idx_metrics_company_period   ON metrics(company_id, period_end DESC, period_type);
CREATE INDEX idx_metrics_period_type      ON metrics(period_end DESC, period_type);

-- Power BI cross-company aggregation support
CREATE INDEX idx_metrics_period_ttm       ON metrics(period_end DESC) WHERE period_type = 'ttm';
CREATE INDEX idx_metrics_completeness     ON metrics(completeness_score) WHERE completeness_score >= 40;

-- Flag columns for Power BI filter performance
CREATE INDEX idx_metrics_flag_lifo        ON metrics(flag_lifo) WHERE flag_lifo = TRUE;
CREATE INDEX idx_metrics_flag_ifrs16      ON metrics(flag_ifrs16_lease_adj) WHERE flag_ifrs16_lease_adj = TRUE;

-- ── fx_rates ──────────────────────────────────────────────────────────────────
CREATE INDEX idx_fx_rates_lookup          ON fx_rates(from_currency, to_currency, rate_date DESC);

-- ── flags ─────────────────────────────────────────────────────────────────────
CREATE INDEX idx_flags_company_active     ON flags(company_id, resolved_at) WHERE resolved_at IS NULL;
CREATE INDEX idx_flags_severity           ON flags(severity) WHERE resolved_at IS NULL;
CREATE INDEX idx_flags_metric_name        ON flags(metric_name);

-- ── filing_log ────────────────────────────────────────────────────────────────
CREATE INDEX idx_filing_log_company       ON filing_log(company_id, run_at DESC);
CREATE INDEX idx_filing_log_status        ON filing_log(status, run_at DESC);

-- ── completeness_scores ───────────────────────────────────────────────────────
CREATE INDEX idx_completeness_company     ON completeness_scores(company_id, period_end DESC);
CREATE INDEX idx_completeness_score       ON completeness_scores(score DESC);
