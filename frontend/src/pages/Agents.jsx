import { useState, useEffect, useRef } from "react";
import { useTriggerScrape, useStats, useAgentRuns } from "../hooks/useJobs";

function LogLine({ text, type }) {
  const color = type === "error" ? "var(--red)" : type === "success" ? "var(--green)" : "var(--text-secondary)";
  return <div style={{ fontSize: 12, fontFamily: "monospace", color, lineHeight: 1.8 }}>{text}</div>;
}

export default function Agents() {
  const scrape = useTriggerScrape();
  const { data: stats, refetch: refetchStats } = useStats();
  const { data: runsPayload, refetch: refetchRuns } = useAgentRuns(30);
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
      addLog("Polling stopped (5-minute window elapsed). Refresh stats to check results.", "info");
    }, 300000);

    return () => { clearInterval(interval); clearTimeout(timeout); };
  }, [polling, refetchStats]);

  useEffect(() => {
    logEnd.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  const s = stats || { total: 0, by_verdict: {} };

  return (
    <div style={{ padding: "32px 40px", maxWidth: 900, margin: "0 auto" }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 4 }}>Agent Control</h1>
      <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 32 }}>
        Trigger scrapes, monitor runs, and manage the pipeline
      </p>

      {/* Action Cards */}
      <div style={{ display: "flex", gap: 16, marginBottom: 32, flexWrap: "wrap" }}>
        {/* Scrape card */}
        <div style={{
          flex: "1 1 300px", background: "var(--bg-raised)", borderRadius: 12,
          padding: 24, border: "1px solid var(--border)",
        }}>
          <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 16 }}>Scraper Agent</div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 20, lineHeight: 1.6 }}>
            Scrapes job boards (jobspy + optional Adzuna/Jooble APIs), ATS company YAMLs, Dice/Glassdoor (Apify when configured).
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
              {scrape.isPending ? "Starting..." : "⚡ Run Scrape"}
            </button>

            <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "var(--text-secondary)", cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={dryRun}
                onChange={(e) => setDryRun(e.target.checked)}
                style={{ accentColor: "var(--accent)" }}
              />
              Dry run (skip DB writes)
            </label>
          </div>

          <div style={{ display: "flex", gap: 20, fontSize: 12, color: "var(--text-muted)", flexWrap: "wrap" }}>
            <span>config.yaml: scraper_agent + job_boards</span>
            <span>10 concurrent ATS</span>
            <span>Celery when Redis up</span>
          </div>
        </div>

        {/* Quick stats card */}
        <div style={{
          flex: "0 0 220px", background: "var(--bg-raised)", borderRadius: 12,
          padding: 24, border: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: 16,
        }}>
          <div style={{ fontSize: 15, fontWeight: 600 }}>Current Stats</div>
          <div>
            <div style={{ fontSize: 32, fontWeight: 700 }}>{s.total}</div>
            <div style={{ fontSize: 11, color: "var(--text-muted)" }}>Total Jobs</div>
          </div>
          <div style={{ display: "flex", gap: 16 }}>
            <div>
              <div style={{ fontSize: 20, fontWeight: 700, color: "var(--green)" }}>{s.by_verdict?.APPLY || 0}</div>
              <div style={{ fontSize: 10, color: "var(--text-muted)" }}>Apply</div>
            </div>
            <div>
              <div style={{ fontSize: 20, fontWeight: 700, color: "var(--yellow)" }}>{s.by_verdict?.MAYBE || 0}</div>
              <div style={{ fontSize: 10, color: "var(--text-muted)" }}>Maybe</div>
            </div>
            <div>
              <div style={{ fontSize: 20, fontWeight: 700, color: "var(--red)" }}>{s.by_verdict?.SKIP || 0}</div>
              <div style={{ fontSize: 10, color: "var(--text-muted)" }}>Skip</div>
            </div>
          </div>
          <button
            onClick={() => refetchStats()}
            style={{
              padding: "6px 14px", borderRadius: 6, fontSize: 11, fontWeight: 600,
              background: "var(--bg-hover)", color: "var(--text-secondary)",
              border: "1px solid var(--border)", cursor: "pointer", marginTop: "auto",
            }}
          >
            ↻ Refresh
          </button>
        </div>
      </div>

      {/* Agent runs from DB */}
      <div style={{
        marginBottom: 24, background: "var(--bg-raised)", borderRadius: 12,
        border: "1px solid var(--border)", overflow: "hidden",
      }}>
        <div style={{
          display: "flex", justifyContent: "space-between", alignItems: "center",
          padding: "12px 20px", borderBottom: "1px solid var(--border)",
        }}>
          <div style={{ fontSize: 13, fontWeight: 600 }}>Recent scraper runs</div>
          <button
            type="button"
            onClick={() => refetchRuns()}
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
                    No runs yet. Trigger a scrape or run the Celery worker for scheduled jobs.
                  </td>
                </tr>
              ) : (
                (runsPayload.runs || []).map((run) => (
                  <tr key={run.id} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td style={{ padding: "10px 16px", color: "var(--text-secondary)", whiteSpace: "nowrap" }}>
                      {run.started_at ? new Date(run.started_at).toLocaleString() : "—"}
                    </td>
                    <td style={{ padding: "10px 16px", fontWeight: 600 }}>
                      {run.status}
                    </td>
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

      {/* Live log */}
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
            {polling && (
              <span style={{ marginLeft: 10, fontSize: 11, color: "var(--green)" }}>● Polling</span>
            )}
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
          height: 280, overflow: "auto", padding: "12px 20px",
          background: "var(--bg-base)",
        }}>
          {logs.length === 0 ? (
            <div style={{ color: "var(--text-muted)", fontSize: 12, fontFamily: "monospace" }}>
              No activity yet. Trigger a scrape to see logs here.
            </div>
          ) : (
            logs.map((log, i) => <LogLine key={i} text={log.text} type={log.type} />)
          )}
          <div ref={logEnd} />
        </div>
      </div>
    </div>
  );
}
