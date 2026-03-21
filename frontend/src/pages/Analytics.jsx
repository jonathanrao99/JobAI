import { useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useAnalytics } from "../hooks/useJobs";

const DAY_OPTIONS = [
  { value: 7, label: "7d" },
  { value: 30, label: "30d" },
  { value: 90, label: "90d" },
];

export default function Analytics() {
  const [days, setDays] = useState(30);
  const { data, isLoading, isError, error } = useAnalytics(days);

  const series = data?.series || [];
  const truncated = data?.truncated;
  const rowsUsed = data?.rows_used;

  return (
    <div style={{ padding: "32px 40px", maxWidth: 1200, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 28, flexWrap: "wrap", gap: 16 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0 }}>Analytics</h1>
          <p style={{ fontSize: 13, color: "var(--text-secondary)", marginTop: 4 }}>
            Daily jobs scraped by verdict (from <code style={{ fontSize: 12 }}>scraped_at</code>)
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {DAY_OPTIONS.map((o) => (
            <button
              key={o.value}
              type="button"
              onClick={() => setDays(o.value)}
              style={{
                padding: "8px 16px",
                borderRadius: 8,
                border: days === o.value ? "1px solid var(--accent)" : "1px solid var(--border)",
                background: days === o.value ? "var(--accent-glow)" : "var(--bg-raised)",
                color: days === o.value ? "var(--accent)" : "var(--text-secondary)",
                fontWeight: 600,
                fontSize: 12,
                cursor: "pointer",
              }}
            >
              {o.label}
            </button>
          ))}
        </div>
      </div>

      {isError && (
        <div style={{
          background: "var(--red-dim)", border: "1px solid var(--red)", borderRadius: 8,
          padding: "12px 16px", marginBottom: 20, fontSize: 13, color: "var(--red)",
        }}>
          {error?.message || "Failed to load analytics"}
        </div>
      )}

      <div style={{
        background: "var(--bg-surface)", borderRadius: 12, padding: 24,
        border: "1px solid var(--border)", minHeight: 380,
      }}>
        {isLoading ? (
          <div style={{ color: "var(--text-muted)", padding: 60, textAlign: "center" }}>Loading series…</div>
        ) : series.length === 0 ? (
          <div style={{ color: "var(--text-muted)", padding: 60, textAlign: "center" }}>
            No data in this window. Run a scrape and check back after jobs land.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={340}>
            <AreaChart data={series} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="gApply" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--green)" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="var(--green)" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gMaybe" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--yellow)" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="var(--yellow)" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gSkip" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--red)" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="var(--red)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 11, fill: "var(--text-muted)" }}
                tickLine={false}
                axisLine={{ stroke: "var(--border)" }}
              />
              <YAxis
                allowDecimals={false}
                tick={{ fontSize: 11, fill: "var(--text-muted)" }}
                tickLine={false}
                axisLine={{ stroke: "var(--border)" }}
              />
              <Tooltip
                contentStyle={{
                  background: "var(--bg-raised)",
                  border: "1px solid var(--border)",
                  borderRadius: 8,
                  fontSize: 12,
                }}
                labelStyle={{ color: "var(--text-primary)" }}
              />
              <Area type="monotone" dataKey="SKIP" stackId="1" stroke="var(--red)" fill="url(#gSkip)" name="Skip" />
              <Area type="monotone" dataKey="MAYBE" stackId="1" stroke="var(--yellow)" fill="url(#gMaybe)" name="Maybe" />
              <Area type="monotone" dataKey="APPLY" stackId="1" stroke="var(--green)" fill="url(#gApply)" name="Apply" />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>

      <div style={{ marginTop: 16, fontSize: 12, color: "var(--text-muted)" }}>
        {rowsUsed != null && (
          <span>
            Based on <strong style={{ color: "var(--text-secondary)" }}>{rowsUsed}</strong> job rows
            {truncated && " (cap reached — chart may be incomplete)"}
          </span>
        )}
      </div>

      <div style={{ marginTop: 32, display: "flex", gap: 24, flexWrap: "wrap" }}>
        {[
          { k: "APPLY", label: "Apply", c: "var(--green)" },
          { k: "MAYBE", label: "Maybe", c: "var(--yellow)" },
          { k: "SKIP", label: "Skip", c: "var(--red)" },
        ].map(({ k, label, c }) => (
          <div key={k} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
            <span style={{ width: 10, height: 10, borderRadius: 2, background: c }} />
            <span style={{ color: "var(--text-secondary)" }}>{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
