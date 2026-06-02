# ADR-001: PostgreSQL as Primary Database

**Date:** 2026-06  
**Status:** Accepted  
**Author:** FinMetrics

---

## Context

FinMetrics needs a database that can:
- Handle ~14M rows of raw_facts (comparable to HEMM Chapter 9 volume)
- Support both the Python pipeline (writes) and Power BI (reads via DirectQuery)
- Scale from local development to Railway cloud hosting without schema changes
- Be queried from multiple tools: Python, Power BI, DBeaver, pgAdmin

## Decision

Use **PostgreSQL 16** as the primary database.

- Local development: PostgreSQL on localhost
- Production: Railway PostgreSQL add-on (~$10–20/month)
- Power BI: native PostgreSQL connector (DirectQuery mode)

SQLite is used during early development only (Phase 1 prototyping) due to zero-config setup. The schema is designed for PostgreSQL from the start — SQLite is a development convenience, not an architecture choice.

## Rationale

| Option | Pros | Cons | Decision |
|---|---|---|---|
| PostgreSQL | Enterprise-grade, Power BI native connector, full SQL, JSONB for flags | Requires hosting | ✅ Chosen |
| SQLite | Zero config, file-based | No Power BI DirectQuery, no concurrent writes | Dev only |
| Supabase | Managed PostgreSQL, free tier | Vendor lock-in, free tier limits | Use as hosting option |
| MongoDB | Flexible schema | Power BI connector limited, no native SQL | ❌ Rejected |

## Consequences

- Power BI connects directly to PostgreSQL via native connector — no API layer needed for analyst reports
- The `accounting_flags` JSONB column stores flexible flag arrays without schema changes
- Denormalized `flag_*` boolean columns added alongside JSONB for Power BI filter performance
- TimescaleDB extension available if time-series query performance becomes a concern (Phase 4)
