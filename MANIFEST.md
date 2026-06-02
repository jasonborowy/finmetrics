# FinMetrics — Complete Document Package
**Version:** 1.0  |  **Date:** 2026-06  |  **Author:** Borowy Consulting

---

## Documents in This Package

### PRIMARY — Single Source of Truth
| File | Purpose | Replaces |
|---|---|---|
| `FinMetrics_Master_Specification.docx` | Complete specification: vision, universe, filing systems, accounting standards, data model, 75 metrics, **Systems Analysis Framework**, pipeline, tech stack, Power BI, roadmap, career pathway, content strategy | FinMetrics_Roadmap_v2, FinMetrics_DataFramework, FinMetrics_ExpandedMetrics_Pipeline |

### APPENDIX — Borowy Consulting Private Practice
| File | Purpose |
|---|---|
| `FinMetrics_AppendixA_PrivateFramework.docx` | Borowy Consulting branded. Origin story, 20 synthetic models, onboarding process, private data problems, normalization methodology, client deliverable spec. Parked Phase 3. |

### LIVING DOCUMENTS — Operational References
| File | Purpose | Update Frequency |
|---|---|---|
| `Financial_Metrics_Reference_v2.xlsx` | 75 public + 12 parked private metrics. Definition, formula, notes, business decisions, causal chains. | Per metric addition |
| `metrics-dashboard.jsx` | React frontend scaffold. 4-category display, hover interactions. Wire to API in Phase 1. | Per UI iteration |
| `finmetrics_pipeline.zip` | Complete Python pipeline: edgar.py, tag_resolver.py, fx_converter.py, accounting.py, ttm.py, schema SQL, tests, diagnose script | Per code commit |

### RETIRED — Content Absorbed Into Master
The following documents are superseded by `FinMetrics_Master_Specification.docx`:
- FinMetrics_Roadmap.docx (v1 — superseded by v2 before consolidation)
- FinMetrics_Roadmap_v2.docx → Sections 1, 11-16
- FinMetrics_DataFramework.docx → Sections 2-6, 8-9
- FinMetrics_ExpandedMetrics_Pipeline.docx → Sections 6 (expanded), 8 (new flags), 10
- Financial_Metrics_Reference.xlsx (v1) → superseded by v2

---

## What's New in v1.0

**Section 7 — Systems Analysis Framework** is the primary new addition:
- Three levels of analytical thinking
- Reinforcing and balancing loop framework
- Seven-stakeholder impact model with incentive layer
- Time delay analysis
- Full causal chain structure (10 dimensions per metric)
- Prototype causal chains: Inventory, DSO, ROIC, EV/EBITDA
- System integration map: how metrics connect
- Dashboard/Power BI systems view (Page 7)

**75 metrics** (up from 55):
- Valuation: EV/EBITDA, EV/Revenue, EV/Gross Profit, P/E, P/FCF
- Growth Quality: Gross Profit Growth, Rule of 40, Book-to-Bill
- Capital Efficiency: Asset Turnover, CapEx Intensity, CapEx/Dep, Net Debt/EBITDA, FCF Conversion
- Semiconductor: Customer Concentration, Geographic Revenue, R&D vs Sector
- Cash Flow Quality: FCF/EBITDA, Cash Earnings, Days Cash On Hand

**12 parked private metrics** formally documented in Appendix B.
