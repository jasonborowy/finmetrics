# FinMetrics Pipeline Runbook

**Purpose:** Step-by-step procedures for operating the FinMetrics data pipeline.  
**Audience:** Anyone running the pipeline — including future-you after a 3-month gap.

---

## Before Running Any ETL — The Diagnostic Step

**This step is mandatory. Do not skip it.**

Based on the HEMM ETL Workflow Standard (Section 8.4): always run the diagnostic before writing new ETL logic or adding a new company.

```bash
# Single company
python scripts/diagnose_edgar.py --ticker NVDA

# Multiple companies
python scripts/diagnose_edgar.py --ticker NVDA --ticker AAPL --ticker TSM

# Save results for documentation
python scripts/diagnose_edgar.py --ticker NVDA --output docs/diagnose_nvda.json
```

**What to look for:**
- Accounting standard (US-GAAP vs IFRS)
- Missing canonical metrics (will appear as gaps in the dashboard)
- Year range available
- Any unresolved tags to add to tag_mappings

Document any surprises in the ETL script header before writing ingest code.

---

## Initial Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp config/.env.example config/.env
# Edit config/.env:
#   DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
#   EDGAR_USER_AGENT = "FinMetrics your@email.com"
```

### 3. Create database
```bash
psql -U postgres -c "CREATE DATABASE finmetrics_db;"
psql -U postgres -c "CREATE USER finmetrics WITH PASSWORD 'your_password';"
psql -U postgres -c "GRANT ALL ON DATABASE finmetrics_db TO finmetrics;"
```

### 4. Run schema migrations
```bash
psql -d finmetrics_db -f database/schema/001_core.sql
psql -d finmetrics_db -f database/schema/002_indexes.sql
```

### 5. Seed company registry
```bash
python scripts/seed_companies.py
```

### 6. Verify schema
```bash
python scripts/verify_schema.py
```

---

## Adding a New Company

```bash
# Step 1: Diagnose first
python scripts/diagnose_edgar.py --ticker NVDA

# Step 2: Review output — note any missing metrics

# Step 3: Add to companies registry (config/companies.json)
# See config/companies.json for format

# Step 4: Run dry-run to validate
python pipeline/etl/orchestrator.py --ticker NVDA --dry-run

# Step 5: Full ingest
python pipeline/etl/orchestrator.py --ticker NVDA
```

---

## Running the Full Pipeline

```bash
# Single company
python pipeline/etl/orchestrator.py --ticker NVDA

# Multiple companies
python pipeline/etl/orchestrator.py --ticker NVDA --ticker AAPL --ticker MSFT

# All companies in registry
python pipeline/etl/orchestrator.py --all

# Dry run (no database writes)
python pipeline/etl/orchestrator.py --all --dry-run
```

---

## Checking Data Quality

After a pipeline run, verify completeness:

```sql
-- Companies with completeness below 70%
SELECT c.ticker, c.name, cs.score, cs.missing_metrics
FROM completeness_scores cs
JOIN companies c ON c.company_id = cs.company_id
WHERE cs.score < 70
ORDER BY cs.score;

-- Active flags by type
SELECT metric_name, severity, COUNT(*) as count
FROM flags
WHERE resolved_at IS NULL
GROUP BY metric_name, severity
ORDER BY count DESC;

-- Recent pipeline errors
SELECT ticker, form_type, error_message, run_at
FROM filing_log
WHERE status = 'failed'
ORDER BY run_at DESC
LIMIT 20;
```

---

## Known Issues and Workarounds

| Issue | Cause | Workaround |
|---|---|---|
| EDGAR returns 403 | Missing or invalid User-Agent | Set `EDGAR_USER_AGENT` in .env |
| EDGAR returns 429 | Rate limit exceeded | Pipeline auto-backs off 60s; reduce `REQUESTS_PER_SECOND` in settings |
| Revenue resolves to NULL | Company uses non-standard tag | Run diagnose, add tag to tag_mappings |
| TTM flagged INCOMPLETE | Fewer than 4 quarters available | Expected for new companies — resolves over time |
| FX rate missing | ECB/Fed rate not yet loaded | Run `python scripts/fetch_fx_rates.py` |

---

## Power BI Refresh

After pipeline runs, Power BI Import mode requires a manual refresh or scheduled refresh via Power BI Service. DirectQuery mode is always live.

To trigger a refresh via Power BI Service:
1. Open the dataset in Power BI Service
2. Datasets → [FinMetrics dataset] → Refresh now
3. Or: configure scheduled refresh (daily, post-earnings windows recommended)

---

## Rollback

If a pipeline run produces bad data:

```sql
-- Delete metrics for a specific company and period
DELETE FROM metrics
WHERE company_id = (SELECT company_id FROM companies WHERE ticker = 'NVDA')
  AND period_end = '2024-09-30';

-- Delete raw_facts for a specific accession
DELETE FROM raw_facts WHERE accession = '0001045810-24-000001';

-- Check filing_log for what was loaded
SELECT * FROM filing_log
WHERE ticker = 'NVDA'
ORDER BY run_at DESC
LIMIT 10;
```

Re-run the pipeline after fixing the issue:
```bash
python pipeline/etl/orchestrator.py --ticker NVDA
```
