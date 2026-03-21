import { useState, useRef, useEffect } from "react";
import { useStats, useJobs, useTriggerScrape, useAgentRuns } from "../hooks/useJobs";

function StatCard({ label, value, sub, color }) {
  return (
    <div style={{
      background: "var(--bg-raised)", borderRadius: 12, padding: "24px 28px",
      border: "1px solid var(--border)", flex: "1 1 0", minWidth: 150,
    }}>
      <div style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: 1.5, marginBottom: 8 }}>
        {label}
      </div>
      <div style={{ fontSize: 36, fontWeight: 700, color: color || "var(--text-primary)", lineHeight: 1 }}>
        {value}
      </div>
      {sub && <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 6 }}>{sub}</div>}
    </div>
  );
}

function TopJobs({ jobs }) {
  if (!jobs?.length) {
    return (
      <div style={{ color: "var(--text-muted)", fontSize: 13, textAlign: "center", padding: 40 }}>
        No jobs yet. Trigger a scrape to get started.
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
      {jobs.map((job, i) => (
        <div key={job.id || i} style={{
          display: "flex", alignItems: "center", gap: 16, padding: "14px 20px",
          background: i % 2 === 0 ? "var(--bg-raised)" : "transparent",
          borderRadius: 8,
        }}>
          <div style={{
            width: 40, height: 40, borderRadius: 8, display: "flex", alignItems: "center",
            justifyContent: "center", fontSize: 16, fontWeight: 700, flexShrink: 0,
            background: "var(--green-dim)", color: "var(--green)",
          }}>
            {job.ai_score}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {job.title}
            </div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 2 }}>
              {job.company}{job.location ? ` · ${job.location}` : ""}
            </div>
          </div>
          <div style={{ fontSize: 11, color: "var(--text-muted)", flexShrink: 0 }}>
            {job.source_board}
          </div>
          {job.job_url && (
            <a href={job.job_url} target="_blank" rel="noopener noreferrer"
              style={{ fontSize: 12, color: "var(--blue)", flexShrink: 0 }}>
              View →
            </a>
          )}
        </div>
      ))}
    </div>
  );
}

export default function Dashboard() {
  const { data: stats, isLoading: statsLoading, refetch: refetchStats } = useStats();
  const { data: topApply } = useJobs({ verdict: "APPLY", minScore: 7, limit: 10 });
  const scrape = useTriggerScrape();
  const { data: runsPayload, refetch: refetchRuns } = useAgentRuns(15);

  const [dryRun, setDryRun] = useState(false);
  const [logs, setLogs] = useState([]);
  const [polling, setPolling] = useState(false);
  const prevTotal = useRef(stats?.total || 0);
  const logEnd = useRef(null);

  const addLog = (text, type = "info") => {
    const ts = new Date().toLocaleTimeString();
    setLogs((prev) => [...prev, { text: `[${ts}] ${text}`, type }]);
  };

  const handleScrape = () => {
    addLog(dryRun ? "Starting dry-run scrape..." : "Starting full scrape...");
    scrape.mutate(dryRun, {
      onSuccess: (res) => {
        const extra = res?.task_id ? ` Celery task ${res.task_id}` : "";
        addLog(`Scrape ${res?.status || "ok"} — ${res?.message || "started"}${extra}`, "success");
        prevTotal.current = stats?.total || 0;
        setPolling(true);
        refetchRuns();
      },
      onError: (e) => addLog(`Failed to trigger: ${e.message}`, "error"),
    });
  };

  useEffect(() => {
    if (!polling) return;
    const interval = setInterval(async () => {
      const result = await refetchStats();
      const newTotal = result.data?.total || 0;
      if (newTotal > prevTotal.current) {
        addLog(`New jobs detected: ${newTotal - prevTotal.current} added (total: ${newTotal})`, "success");
        prevTotal.current = newTotal;
      } else {
        addLog(`Polling... (${newTotal} total jobs)`);
      }
    }, 15000);
    const timeout = setTimeout(() => {
      clearInterval(interval);
      setPolling(false);
      addLog("Polling stopped (5-min window elapsed).");
    }, 300000);
    return () => { clearInterval(interval); clearTimeout(timeout); };
  }, [polling, refetchStats]);

  useEffect(() => {
    logEnd.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  const s = stats || { total: 0, by_verdict: {}, avg_score: 0, remote_count: 0, by_source: {} };

  return (
    <div style={{ padding: "32px 40px", maxWidth: 1200, margin: "0 auto" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 32 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0 }}>Dashboard</h1>
          <p style={{ fontSize: 13, color: "var(--text-secondary)", marginTop: 4 }}>
            Job search overview and quick actions
          </p>
        </div>
      </div>

      {/* Stat cards */}
      <div style={{ display: "flex", gap: 16, marginBottom: 32, flexWrap: "wrap" }}>
        <StatCard label="Total Jobs" value={statsLoading ? "—" : s.total} />
        <StatCard label="Apply" value={s.by_verdict?.APPLY || 0} color="var(--green)" />
        <StatCard label="Maybe" value={s.by_verdict?.MAYBE || 0} color="var(--yellow)" />
        <StatCard label="Skip" value={s.by_verdict?.SKIP || 0} color="var(--red)" />
        <StatCard label="Avg Score" value={s.avg_score || "—"} sub="out of 10" color="var(--blue)" />
        <StatCard label="Remote" value={s.remote_count || 0} color="var(--purple)" />
      </div>

      {/* Top APPLY jobs */}
      <div style={{
        background: "var(--bg-surface)", borderRadius: 12, padding: 24,
        border: "1px solid var(--border)", marginBottom: 32,
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <div style={{ fontSize: 15, fontWeight: 600 }}>Top Matches</div>
          <div style={{
            fontSize: 11, color: "var(--green)", background: "var(--green-dim)",
            padding: "4px 10px", borderRadius: 12,
          }}>
            APPLY
          </div>
        </div>
        <TopJobs jobs={topApply?.jobs} />
      </div>

      {/* ── Scraper Control ─────────────────────────────── */}
      <div style={{
        display: "flex", gap: 16, marginBottom: 24, flexWrap: "wrap",
      }}>
        <div style={{
          flex: "1 1 340px", background: "var(--bg-raised)", borderRadius: 12,
          padding: 24, border: "1px solid var(--border)",
        }}>
          <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 8 }}>Scraper Agent</div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 20, lineHeight: 1.6 }}>
            Scrapes job boards, ATS career pages, and Dice via Apify.
            Jobs are deduplicated, scored by AI, and saved to the database.
          </div>
          <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 16 }}>
            <button
              onClick={handleScrape}
              disabled={scrape.isPending}
              style={{
                padding: "10px 28px", borderRadius: 8, border: "none", cursor: "pointer",
                background: scrape.isPending ? "var(--border)" : "var(--accent)",
                color: "#fff", fontWeight: 600, fontSize: 13,
              }}
            >
              {scrape.isPending ? "Starting…" : "⚡ Run Scrape"}
            </button>
            <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "var(--text-secondary)", cursor: "pointer" }}>
              <input
                type="checkbox" checked={dryRun}
                onChange={(e) => setDryRun(e.target.checked)}
                style={{ accentColor: "var(--accent)" }}
              />
              Dry run
            </label>
          </div>
        </div>
      </div>

      {/* Run history table */}
      <div style={{
        marginBottom: 24, background: "var(--bg-raised)", borderRadius: 12,
        border: "1px solid var(--border)", overflow: "hidden",
      }}>
        <div style={{
          display: "flex", justifyContent: "space-between", alignItems: "center",
          padding: "12px 20px", borderBottom: "1px solid var(--border)",
        }}>
          <div style={{ fontSize: 13, fontWeight: 600 }}>Recent Scraper Runs</div>
          <button
            type="button" onClick={() => refetchRuns()}
            style={{
              padding: "4px 12px", borderRadius: 6, fontSize: 11,
              background: "var(--bg-hover)", color: "var(--text-muted)",
              border: "none", cursor: "pointer",
            }}
          >
            ↻ Refresh
          </button>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr style={{ textAlign: "left", color: "var(--text-muted)", borderBottom: "1px solid var(--border)" }}>
                <th style={{ padding: "10px 16px" }}>Started</th>
                <th style={{ padding: "10px 16px" }}>Status</th>
                <th style={{ padding: "10px 16px" }}>Processed</th>
                <th style={{ padding: "10px 16px" }}>Saved</th>
                <th style={{ padding: "10px 16px" }}>Error</th>
              </tr>
            </thead>
            <tbody>
              {(runsPayload?.runs || []).length === 0 ? (
                <tr>
                  <td colSpan={5} style={{ padding: 20, color: "var(--text-muted)" }}>
                    No runs yet. Trigger a scrape above or start the Celery worker.
                  </td>
                </tr>
              ) : (
                (runsPayload.runs || []).map((run) => (
                  <tr key={run.id} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td style={{ padding: "10px 16px", color: "var(--text-secondary)", whiteSpace: "nowrap" }}>
                      {run.started_at ? new Date(run.started_at).toLocaleString() : "—"}
                    </td>
                    <td style={{ padding: "10px 16px", fontWeight: 600 }}>{run.status}</td>
                    <td style={{ padding: "10px 16px" }}>{run.items_processed ?? "—"}</td>
                    <td style={{ padding: "10px 16px" }}>{run.items_succeeded ?? "—"}</td>
                    <td style={{ padding: "10px 16px", color: "var(--red)", maxWidth: 280 }} title={run.error_message || ""}>
                      {(run.error_message || "").slice(0, 80)}{(run.error_message || "").length > 80 ? "…" : ""}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Activity log */}
      {logs.length > 0 && (
        <div style={{
          background: "var(--bg-surface)", borderRadius: 12, border: "1px solid var(--border)",
          overflow: "hidden",
        }}>
          <div style={{
            display: "flex", justifyContent: "space-between", alignItems: "center",
            padding: "12px 20px", borderBottom: "1px solid var(--border)",
          }}>
            <div style={{ fontSize: 13, fontWeight: 600 }}>
              Activity Log
              {polling && <span style={{ marginLeft: 10, fontSize: 11, color: "var(--green)" }}>● Polling</span>}
            </div>
            <button
              onClick={() => setLogs([])}
              style={{
                padding: "4px 12px", borderRadius: 6, fontSize: 11,
                background: "var(--bg-hover)", color: "var(--text-muted)",
                border: "none", cursor: "pointer",
              }}
            >
              Clear
            </button>
          </div>
          <div style={{
            maxHeight: 220, overflow: "auto", padding: "12px 20px",
            background: "var(--bg-base)",
          }}>
            {logs.map((log, i) => (
              <div key={i} style={{
                fontSize: 12, fontFamily: "monospace", lineHeight: 1.8,
                color: log.type === "error" ? "var(--red)" : log.type === "success" ? "var(--green)" : "var(--text-secondary)",
              }}>
                {log.text}
              </div>
            ))}
            <div ref={logEnd} />
          </div>
        </div>
      )}
    </div>
  );
}
