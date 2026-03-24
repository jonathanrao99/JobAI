"use client";

import { useState, useRef, useEffect } from "react";
import { useStats, useJobs, useTriggerScrape, useAgentRuns } from "@/hooks/useJobs";
import "./Dashboard.css";

function StatCard({ label, value, sub, color }) {
  return (
    <div className="dash-stat-card">
      <div className="dash-stat-label">{label}</div>
      <div className="dash-stat-value" style={color ? { color } : undefined}>
        {value}
      </div>
      {sub && <div className="dash-stat-sub">{sub}</div>}
    </div>
  );
}

function statusPillClass(status) {
  const s = String(status || "").toLowerCase();
  if (s === "completed") return "dash-status-pill dash-status-completed";
  if (s === "failed") return "dash-status-pill dash-status-failed";
  if (s === "running") return "dash-status-pill dash-status-running";
  if (s === "cancelled") return "dash-status-pill dash-status-cancelled";
  return "dash-status-pill dash-status-unknown";
}

function TopJobs({ jobs }) {
  if (!jobs?.length) {
    return (
      <div className="dash-top-empty">
        No jobs yet. Trigger a scrape to get started.
      </div>
    );
  }

  return (
    <div className="dash-top-list">
      {jobs.map((job, i) => (
        <div key={job.id || i} className="dash-top-row">
          <div className="dash-score-pill">{job.ai_score}</div>
          <div className="dash-top-main">
            <div className="dash-top-title">{job.title}</div>
            <div className="dash-top-meta">
              {job.company}
              {job.location ? ` · ${job.location}` : ""}
            </div>
          </div>
          <div className="dash-top-source">{job.source_board}</div>
          {job.job_url && (
            <a
              href={job.job_url}
              target="_blank"
              rel="noopener noreferrer"
              className="dash-top-link"
            >
              Open ↗
            </a>
          )}
        </div>
      ))}
    </div>
  );
}

export default function HomePageClient() {
  const [logs, setLogs] = useState([]);
  const [polling, setPolling] = useState(false);
  const prevTotal = useRef(0);
  const pollingStarted = useRef(false);
  const logEnd = useRef(null);

  const { data: stats, isLoading: statsLoading } = useStats({
    staleTime: 45_000,
    refetchInterval: polling ? 15_000 : false,
  });
  const { data: topApply } = useJobs({ verdict: "APPLY", minScore: 7, limit: 10 });
  const scrape = useTriggerScrape();
  const { data: runsPayload, refetch: refetchRuns } = useAgentRuns(15);

  const addLog = (text, type = "info") => {
    const ts = new Date().toLocaleTimeString();
    setLogs((prev) => [...prev, { text: `[${ts}] ${text}`, type }]);
  };

  const handleScrape = () => {
    addLog("Starting scrape…");
    scrape.mutate(false, {
      onSuccess: (res) => {
        const extra = res?.task_id ? ` Celery task ${res.task_id}` : "";
        addLog(`Scrape ${res?.status || "ok"} — ${res?.message || "started"}${extra}`, "success");
        prevTotal.current = stats?.total || 0;
        pollingStarted.current = false;
        setPolling(true);
        refetchRuns();
      },
      onError: (e) => addLog(`Failed to trigger: ${e.message}`, "error"),
    });
  };

  useEffect(() => {
    if (!polling || stats == null) return;
    if (!pollingStarted.current) {
      pollingStarted.current = true;
      prevTotal.current = stats.total || 0;
      return;
    }
    const newTotal = stats.total || 0;
    if (newTotal > prevTotal.current) {
      addLog(`New jobs detected: ${newTotal - prevTotal.current} added (total: ${newTotal})`, "success");
      prevTotal.current = newTotal;
    } else {
      addLog(`Polling… (${newTotal} total jobs)`);
    }
  }, [polling, stats]);

  useEffect(() => {
    if (!polling) return undefined;
    const timeout = setTimeout(() => {
      setPolling(false);
      addLog("Polling stopped (5-min window elapsed).");
    }, 300_000);
    return () => clearTimeout(timeout);
  }, [polling]);

  useEffect(() => {
    logEnd.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  const s = stats || { total: 0, by_verdict: {}, avg_score: 0, remote_count: 0, by_source: {} };

  return (
    <div className="dash-page">
      <header className="dash-header">
        <h1 className="dash-title">Dashboard</h1>
        <p className="dash-subtitle">Job search overview and quick actions</p>
      </header>

      <div className="dash-stat-grid">
        <StatCard label="Total Jobs" value={statsLoading ? "—" : s.total} />
        <StatCard label="Apply" value={s.by_verdict?.APPLY || 0} color="var(--green)" />
        <StatCard label="Maybe" value={s.by_verdict?.MAYBE || 0} color="var(--yellow)" />
        <StatCard label="Skip" value={s.by_verdict?.SKIP || 0} color="var(--red)" />
        <StatCard label="Avg Score" value={s.avg_score || "—"} sub="out of 10" color="var(--blue)" />
        <StatCard label="Remote" value={s.remote_count || 0} color="var(--purple)" />
      </div>

      <section className="dash-panel">
        <div className="dash-panel__head">
          <div className="dash-panel__intro">
            <div className="dash-section-title">Scraper Agent</div>
            <p className="dash-blurb">
              Pulls from JobSpy, company ATS feeds, and config-driven Apify actors (e.g. Dice). Set{" "}
              <code style={{ fontSize: 11 }}>APIFY_API_TOKEN</code> and optional{" "}
              <code style={{ fontSize: 11 }}>scraper_agent.apify_actors</code> in{" "}
              <code style={{ fontSize: 11 }}>config.yaml</code>. Jobs are deduplicated, scored, and saved.
            </p>
          </div>
          <div className="dash-panel__actions">
            <button
              type="button"
              className="dash-btn-run"
              onClick={handleScrape}
              disabled={scrape.isPending}
            >
              {scrape.isPending ? "Starting…" : "Run Scrape"}
            </button>
            <button type="button" className="dash-btn-secondary" onClick={() => refetchRuns()}>
              Refresh runs
            </button>
          </div>
        </div>

        <div className="dash-divider">
          <div className="dash-runs-label">Recent scraper runs</div>
          <div className="dash-table-wrap">
            <table className="dash-table">
              <thead>
                <tr>
                  <th>Started</th>
                  <th>Status</th>
                  <th>Processed</th>
                  <th>Saved</th>
                  <th>Error</th>
                </tr>
              </thead>
              <tbody>
                {(runsPayload?.runs || []).length === 0 ? (
                  <tr>
                    <td colSpan={5} className="dash-table-empty">
                      No runs yet. Run a scrape above or start the Celery worker.
                    </td>
                  </tr>
                ) : (
                  (runsPayload.runs || []).map((run) => (
                    <tr key={run.id}>
                      <td className="dash-cell-time">
                        {run.started_at ? new Date(run.started_at).toLocaleString() : "—"}
                      </td>
                      <td>
                        <span className={statusPillClass(run.status)}>
                          {String(run.status || "unknown").toLowerCase()}
                        </span>
                      </td>
                      <td>{run.items_processed ?? "—"}</td>
                      <td>{run.items_succeeded ?? "—"}</td>
                      <td className="dash-cell-err" title={run.error_message || ""}>
                        {(run.error_message || "").slice(0, 80)}
                        {(run.error_message || "").length > 80 ? "…" : ""}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {logs.length > 0 && (
          <div className="dash-activity">
            <div className="dash-activity__bar">
              <div>
                <span className="dash-activity__title">Activity log</span>
                {polling && <span className="dash-activity__poll">● Polling</span>}
              </div>
              <button
                type="button"
                onClick={() => setLogs([])}
                className="dash-btn-ghost dash-btn-clear"
              >
                Clear
              </button>
            </div>
            <div className="dash-log">
              {logs.map((log, i) => (
                <div
                  key={i}
                  className={`dash-log-line dash-log-line--${log.type === "error" ? "error" : log.type === "success" ? "success" : "info"}`}
                >
                  {log.text}
                </div>
              ))}
              <div ref={logEnd} />
            </div>
          </div>
        )}
      </section>

      <section className="dash-panel">
        <div className="dash-top-head">
          <div className="dash-section-title">Top matches</div>
          <span className="dash-badge-apply">APPLY</span>
        </div>
        <TopJobs jobs={topApply?.jobs} />
      </section>
    </div>
  );
}
