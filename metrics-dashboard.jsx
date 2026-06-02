import { useState } from "react";

const metrics = {
  Growth: [
    "Common Shares",
    "Employee Growth",
    "Employees",
    "Market Capitalization",
    "R&D Margin",
    "R&D Ratio",
    "R&D To COGS Ratio",
    "Revenue",
    "Revenue Growth",
    "Revenue Growth TTM",
    "Revenue TTM",
    "SG&A Margin",
    "SG&A Ratio",
    "SG&A To COGS Ratio",
  ],
  Profitability: [
    "Cash",
    "Cash Change In Period",
    "Cash On Hand",
    "Cash Ratio TTM",
    "Cash Ratio Quarter",
    "Cash Ratio Year",
    "COGS",
    "EBITDA",
    "Free Cash Flow Ratio",
    "Gross Margin",
    "Gross Profit",
    "Fgross Profit",
    "Net Profit Margin",
    "Operating Cash Flow Ratio",
    "Operating Margin",
    "Opex Ratio",
    "Pretax Margin",
  ],
  Cycle: [
    "Cash-To-Cash",
    "Days Of Finished Goods",
    "Days Of Inventory",
    "Days Of Payables Outstanding",
    "Days Of Raw Materials",
    "Days Of Sales Outstanding",
    "Days Of Work In Progress",
    "DPO/DSO",
    "Finished Goods Inventory",
    "Inventory",
    "Inventory Turns",
    "Receivables Turns",
    "Raw Materials Inventory",
    "Work In Progress Inventory",
  ],
  Complexity: [
    "Altman Z",
    "Capital Turnover",
    "Current Ratio",
    "Quick Ratio",
    "Return On Assets",
    "Return On Equity",
    "Return On Invested Capital",
    "Return On Net Assets",
    "Revenue Per Employee",
    "Working Capital Ratio",
  ],
};

const config = {
  Growth: {
    accent: "#3B82F6",
    dim: "#1E3A5F",
    bg: "rgba(59,130,246,0.07)",
    border: "rgba(59,130,246,0.25)",
    tag: "#93C5FD",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/>
      </svg>
    ),
  },
  Profitability: {
    accent: "#10B981",
    dim: "#064E3B",
    bg: "rgba(16,185,129,0.07)",
    border: "rgba(16,185,129,0.25)",
    tag: "#6EE7B7",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>
      </svg>
    ),
  },
  Cycle: {
    accent: "#F59E0B",
    dim: "#78350F",
    bg: "rgba(245,158,11,0.07)",
    border: "rgba(245,158,11,0.25)",
    tag: "#FCD34D",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-4.5"/>
      </svg>
    ),
  },
  Complexity: {
    accent: "#A855F7",
    dim: "#3B0764",
    bg: "rgba(168,85,247,0.07)",
    border: "rgba(168,85,247,0.25)",
    tag: "#D8B4FE",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="12" cy="12" r="2"/><path d="M12 2a10 10 0 0 1 7.39 16.74M12 2a10 10 0 0 0-7.39 16.74M12 22a10 10 0 0 1-7.39-16.74M12 22a10 10 0 0 0 7.39-16.74"/>
      </svg>
    ),
  },
};

function MetricPill({ name, accent, tag }) {
  const [hovered, setHovered] = useState(false);
  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: "5px 11px",
        borderRadius: "20px",
        fontSize: "12px",
        fontFamily: "'DM Mono', monospace",
        letterSpacing: "0.01em",
        cursor: "default",
        transition: "all 0.18s ease",
        background: hovered ? accent : "rgba(255,255,255,0.04)",
        color: hovered ? "#0A0F1E" : tag,
        border: `1px solid ${hovered ? accent : "rgba(255,255,255,0.08)"}`,
        fontWeight: hovered ? "600" : "400",
        transform: hovered ? "translateY(-1px)" : "none",
        boxShadow: hovered ? `0 4px 16px ${accent}55` : "none",
        userSelect: "none",
      }}
    >
      {name}
    </div>
  );
}

function CategoryCard({ category, items }) {
  const c = config[category];
  return (
    <div
      style={{
        background: "rgba(10,15,30,0.7)",
        border: `1px solid ${c.border}`,
        borderRadius: "16px",
        padding: "24px",
        backdropFilter: "blur(12px)",
        position: "relative",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        gap: "18px",
      }}
    >
      {/* Glow orb */}
      <div style={{
        position: "absolute",
        top: "-40px",
        right: "-40px",
        width: "140px",
        height: "140px",
        borderRadius: "50%",
        background: c.accent,
        opacity: 0.07,
        filter: "blur(40px)",
        pointerEvents: "none",
      }} />

      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <div style={{
            width: "34px", height: "34px", borderRadius: "10px",
            background: c.bg, border: `1px solid ${c.border}`,
            display: "flex", alignItems: "center", justifyContent: "center",
            color: c.accent,
          }}>
            {c.icon}
          </div>
          <div>
            <div style={{
              fontSize: "15px", fontWeight: "700", color: "#F1F5F9",
              fontFamily: "'Syne', sans-serif", letterSpacing: "0.02em",
            }}>
              {category}
            </div>
            <div style={{
              fontSize: "11px", color: "rgba(255,255,255,0.35)",
              fontFamily: "'DM Mono', monospace", marginTop: "1px",
            }}>
              {items.length} metrics
            </div>
          </div>
        </div>
        <div style={{
          width: "6px", height: "6px", borderRadius: "50%",
          background: c.accent, boxShadow: `0 0 8px ${c.accent}`,
        }} />
      </div>

      {/* Divider */}
      <div style={{ height: "1px", background: `linear-gradient(90deg, ${c.accent}44, transparent)` }} />

      {/* Pills */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "7px" }}>
        {items.map((m) => (
          <MetricPill key={m} name={m} accent={c.accent} tag={c.tag} />
        ))}
      </div>
    </div>
  );
}

export default function Dashboard() {
  const total = Object.values(metrics).reduce((a, b) => a + b.length, 0);

  return (
    <div style={{
      minHeight: "100vh",
      background: "#080C1A",
      backgroundImage: `
        radial-gradient(ellipse at 20% 10%, rgba(59,130,246,0.12) 0%, transparent 50%),
        radial-gradient(ellipse at 80% 80%, rgba(168,85,247,0.10) 0%, transparent 50%),
        radial-gradient(ellipse at 60% 30%, rgba(16,185,129,0.06) 0%, transparent 40%)
      `,
      padding: "40px 24px",
      fontFamily: "'DM Mono', monospace",
      boxSizing: "border-box",
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@600;700;800&family=DM+Mono:wght@300;400;500&display=swap');
        * { box-sizing: border-box; }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.15); border-radius: 4px; }
      `}</style>

      {/* Header */}
      <div style={{ maxWidth: "1100px", margin: "0 auto 36px" }}>
        <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", flexWrap: "wrap", gap: "12px" }}>
          <div>
            <div style={{
              fontSize: "11px", color: "rgba(255,255,255,0.3)", letterSpacing: "0.15em",
              textTransform: "uppercase", marginBottom: "8px", fontFamily: "'DM Mono', monospace",
            }}>
              Supply Chain Metrics That Matter
            </div>
            <h1 style={{
              margin: 0, fontSize: "clamp(24px, 4vw, 36px)",
              fontFamily: "'Syne', sans-serif", fontWeight: "800",
              color: "#F8FAFC", letterSpacing: "-0.02em", lineHeight: 1.1,
            }}>
              Financial Metrics
              <span style={{
                display: "block", fontSize: "clamp(22px, 3.5vw, 32px)",
                background: "linear-gradient(90deg, #3B82F6, #10B981, #F59E0B, #A855F7)",
                WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
                backgroundClip: "text",
              }}>
                Dashboard
              </span>
            </h1>
          </div>
          <div style={{
            background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: "12px", padding: "12px 20px", textAlign: "right",
          }}>
            <div style={{ fontSize: "28px", fontWeight: "700", color: "#F8FAFC", fontFamily: "'Syne', sans-serif", lineHeight: 1 }}>
              {total}
            </div>
            <div style={{ fontSize: "11px", color: "rgba(255,255,255,0.35)", marginTop: "3px", letterSpacing: "0.08em" }}>
              TOTAL METRICS
            </div>
          </div>
        </div>

        {/* Category summary bar */}
        <div style={{
          display: "flex", gap: "8px", marginTop: "24px", flexWrap: "wrap",
        }}>
          {Object.entries(metrics).map(([cat, items]) => {
            const c = config[cat];
            return (
              <div key={cat} style={{
                display: "flex", alignItems: "center", gap: "6px",
                padding: "5px 12px", borderRadius: "8px",
                background: c.bg, border: `1px solid ${c.border}`,
                fontSize: "11px", color: c.accent, fontFamily: "'DM Mono', monospace",
              }}>
                <span style={{ color: c.tag, fontWeight: "600" }}>{items.length}</span>
                <span style={{ opacity: 0.7 }}>{cat}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Grid */}
      <div style={{
        maxWidth: "1100px", margin: "0 auto",
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(480px, 1fr))",
        gap: "20px",
      }}>
        {Object.entries(metrics).map(([cat, items]) => (
          <CategoryCard key={cat} category={cat} items={items} />
        ))}
      </div>

      {/* Footer */}
      <div style={{
        maxWidth: "1100px", margin: "32px auto 0",
        textAlign: "center", fontSize: "11px",
        color: "rgba(255,255,255,0.18)", fontFamily: "'DM Mono', monospace",
        letterSpacing: "0.05em",
      }}>
        Hover metrics to highlight · Source: 10-K / 10-Q SEC Filings
      </div>
    </div>
  );
}
