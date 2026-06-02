# ADR-002: Canonical Tag Mapping Architecture

**Date:** 2026-06  
**Status:** Accepted  

---

## Context

Five filing systems use five different XBRL taxonomies. The same concept (e.g. "Revenue") has different tag names across US-GAAP, IFRS, J-GAAP, K-IFRS, and TW-GAAP. Without normalization, cross-company comparison is impossible.

Additionally, within a single taxonomy, the same concept can have multiple valid tag names. EDGAR US-GAAP has `Revenues`, `RevenueFromContractWithCustomerExcludingAssessedTax`, `SalesRevenueNet` — all meaning the same thing.

## Decision

Implement a **canonical tag mapping table** (`tag_mappings`) with priority-ordered synonyms per taxonomy per canonical metric name.

Resolution algorithm:
1. For each fact's source_tag, look up `(taxonomy, source_tag)` in tag_mappings
2. If found: assign canonical_name and record priority
3. If not found: store raw fact with `canonical_tag = NULL`; log for review
4. Never discard unresolved facts — they remain in raw_facts for future mapping

The `tag_resolver.py` module loads mappings at startup and resolves in-memory (~825 entries, fits easily in RAM).

## Rationale

- **Seeded in code, extended in database:** The seed (~200 most common tags) ships with the codebase. New tags discovered during pipeline runs are logged and added to the database without code changes.
- **Priority ordering:** When multiple tags for the same metric exist in the same filing (rare but possible), the lowest priority number wins.
- **Audit trail:** `raw_facts.source_tag` always preserves the original tag. Normalization is non-destructive.

## Consequences

- New filing systems (EDINET, DART) require new taxonomy sections in tag_mappings
- `scripts/diagnose_edgar.py` surfaces unresolved tags after each new company is added
- Coverage % tracked in `completeness_scores` table
- `resolver.unresolved_tags()` returns session-accumulated unknowns for database insertion
