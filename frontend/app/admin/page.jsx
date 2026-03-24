"use client";

import { useMemo } from "react";
import toast from "react-hot-toast";
import { useAdminOpsSummary, useTriggerScrape } from "@/hooks/useJobs";
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

function fmtCount(v) {
  if (v == null) return "—";
  return String(v);
}

export default function AdminPage() {
  const { data, isLoading, isError, error, refetch } = useAdminOpsSummary();
  const triggerScrape = useTriggerScrape();
  const summary = data?.summary || {};
  const rows = useMemo(() => summary.by_source || [], [summary.by_source]);
  const recency = summary.recency_buckets || {};
  const latestScrapeAt = summary.latest_scrape_at ? new Date(summary.latest_scrape_at).toLocaleString() : "—";

  return (
    <div className="admin-page">
      <header className="admin-header">
        <div className="admin-header__row">
          <div>
            <h1 className="admin-title">Admin</h1>
            <p className="admin-subtitle">Scraper, dedup, recency, and enrichment operations overview.</p>
          </div>
          <div className="admin-header__actions">
            <button
              type="button"
              className="admin-btn admin-btn--secondary"
              disabled={isLoading}
              onClick={() => refetch()}
            >
              Refresh
            </button>
            <button
              type="button"
              className="admin-btn"
              disabled={triggerScrape.isPending}
              onClick={() => {
                const tid = toast.loading("Starting scrape…");
                triggerScrape.mutate(false, {
                  onSettled: () => toast.dismiss(tid),
                  onSuccess: () => {
                    toast.success("Scrape finished");
                    refetch();
                  },
                  onError: (e) => toast.error(e?.message || "Scrape failed"),
                });
              }}
            >
              {triggerScrape.isPending ? "Scraping…" : "Run scrape"}
            </button>
          </div>
        </div>
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

          <section className="admin-panel admin-panel--compact">
            <h2 className="admin-panel__title">Jobs in DB by posted date</h2>
            <p className="admin-panel__note">
              Based on <code className="admin-code">jobs.posted_at</code>. Cumulative = all jobs posted on or after the cutoff.
            </p>
            <div className="admin-grid admin-grid--recency">
              <StatCard label="≤ 24h" value={fmtCount(recency.posted_within_24h)} hint="Cumulative" />
              <StatCard label="≤ 72h" value={fmtCount(recency.posted_within_72h)} hint="Cumulative" />
              <StatCard label="≤ 7d" value={fmtCount(recency.posted_within_7d)} hint="Cumulative" />
            </div>
            <p className="admin-panel__note admin-panel__note--tight">Non-overlapping bands (sum with ≤24h ≈ ≤7d when posted_at is set).</p>
            <div className="admin-grid admin-grid--recency admin-grid--recency-two">
              <StatCard label="72h–7d ago" value={fmtCount(recency.posted_between_72h_and_7d_ago)} />
              <StatCard label="24–72h ago" value={fmtCount(recency.posted_between_24h_and_72h_ago)} />
            </div>
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
