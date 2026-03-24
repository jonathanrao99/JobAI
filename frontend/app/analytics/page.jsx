"use client";

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
import { useAnalytics } from "@/hooks/useJobs";
import "./Analytics.css";

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
    <div className="analytics-page">
      <header className="analytics-header">
        <div>
          <h1 className="analytics-title">Analytics</h1>
          <p className="analytics-subtitle">
            Daily jobs scraped by verdict (from <code>scraped_at</code>)
          </p>
        </div>
        <div className="analytics-range" role="group" aria-label="Date range">
          {DAY_OPTIONS.map((o) => (
            <button
              key={o.value}
              type="button"
              className={`analytics-range-btn${days === o.value ? " is-active" : ""}`}
              onClick={() => setDays(o.value)}
            >
              {o.label}
            </button>
          ))}
        </div>
      </header>

      {isError && (
        <div className="analytics-error" role="alert">
          {error?.message || "Failed to load analytics"}
        </div>
      )}

      <div className="analytics-chart-shell">
        {isLoading ? (
          <div className="analytics-chart-loading">Loading series…</div>
        ) : series.length === 0 ? (
          <div className="analytics-chart-empty">
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
                  border: "1px solid rgba(255, 255, 255, 0.1)",
                  borderRadius: 10,
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

      <div className="analytics-footnote">
        {rowsUsed != null && (
          <span>
            Based on <strong>{rowsUsed}</strong> job rows
            {truncated && " (cap reached — chart may be incomplete)"}
          </span>
        )}
      </div>

      <div className="analytics-legend">
        {[
          { k: "APPLY", label: "Apply", c: "var(--green)" },
          { k: "MAYBE", label: "Maybe", c: "var(--yellow)" },
          { k: "SKIP", label: "Skip", c: "var(--red)" },
        ].map(({ k, label, c }) => (
          <div key={k} className="analytics-legend-item">
            <span className="analytics-legend-swatch" style={{ background: c }} />
            <span>{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
