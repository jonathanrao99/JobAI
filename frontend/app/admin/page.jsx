"use client";

import { useMemo } from "react";
import { useAdminOpsSummary } from "@/hooks/useJobs";
import "./Admin.css";

function StatCard({ label, value, hint }) {
  return (
    <div className="admin-card">
      <div className="admin-card__label">{label}</div>
      <div className="admin-card__value">{value}</div>
      {hint ? <div className="admin-card__hint">{hint}</div> : null}
    </div>
  );
}

function SourceTable({ rows }) {
  if (!rows.length) return <p className="admin-empty">No source metrics yet.</p>;
  return (
    <div className="admin-table-wrap">
      <table className="admin-table">
        <thead>
          <tr>
            <th>Source</th>
            <th>Fetched</th>
            <th>Post dedup</th>
            <th>Apply</th>
            <th>Maybe</th>
            <th>Skip</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.source}>
              <td>{r.source}</td>
              <td>{r.raw}</td>
              <td>{r.post_dedup}</td>
              <td>{r.apply}</td>
              <td>{r.maybe}</td>
              <td>{r.skip}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function AdminPage() {
  const { data, isLoading, isError, error } = useAdminOpsSummary();
  const summary = data?.summary || {};
  const rows = useMemo(() => summary.by_source || [], [summary.by_source]);
  const latestScrapeAt = summary.latest_scrape_at ? new Date(summary.latest_scrape_at).toLocaleString() : "—";

  return (
    <div className="admin-page">
      <header className="admin-header">
        <h1 className="admin-title">Admin</h1>
        <p className="admin-subtitle">Scraper, dedup, recency, and enrichment operations overview.</p>
      </header>

      {isLoading ? <div className="admin-loading">Loading ops summary…</div> : null}
      {isError ? <div className="admin-error">{error?.message || "Failed to load admin summary."}</div> : null}

      {!isLoading && !isError ? (
        <>
          <section className="admin-grid">
            <StatCard label="Latest Scrape" value={latestScrapeAt} />
            <StatCard label="Raw Jobs" value={summary.scraped_raw ?? 0} hint="Most recent scraper run" />
            <StatCard label="Unique Jobs" value={summary.unique_new ?? 0} hint="After dedup + recency" />
            <StatCard label="Duplicates Removed" value={summary.dedup_removed ?? 0} />
            <StatCard label="Stale Dropped" value={summary.stale_dropped ?? 0} hint={`Window: ${summary.recency_hours ?? 0}h`} />
            <StatCard label="Inserted to DB" value={summary.inserted_to_db ?? 0} />
          </section>

          <section className="admin-panel">
            <h2 className="admin-panel__title">Source Coverage</h2>
            <SourceTable rows={rows} />
          </section>

          <section className="admin-grid admin-grid--enrichment">
            <StatCard label="Prepare Runs (24h)" value={summary.prepare_runs_24h ?? 0} />
            <StatCard label="DB Reused (24h)" value={summary.db_reused_24h ?? 0} />
            <StatCard label="Apify Called (24h)" value={summary.apify_called_24h ?? 0} />
            <StatCard label="Emails Enriched (24h)" value={summary.emails_enriched_24h ?? 0} />
          </section>
        </>
      ) : null}
    </div>
  );
}
