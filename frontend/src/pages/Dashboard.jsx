import { useStats, useJobs, useTriggerScrape } from "../hooks/useJobs";

const verdictColor = {
  APPLY: { bg: "var(--green-dim)", color: "var(--green)", border: "var(--green)" },
  MAYBE: { bg: "var(--yellow-dim)", color: "var(--yellow)", border: "var(--yellow)" },
  SKIP:  { bg: "var(--red-dim)",    color: "var(--red)",    border: "var(--red)" },
};

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
  const { data: stats, isLoading: statsLoading } = useStats();
  const { data: topApply } = useJobs({ verdict: "APPLY", limit: 10 });
  const scrape = useTriggerScrape();

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
        <button
          onClick={() => scrape.mutate(false)}
          disabled={scrape.isPending}
          style={{
            padding: "10px 24px", borderRadius: 8, border: "none", cursor: "pointer",
            background: scrape.isPending ? "var(--border)" : "var(--accent)",
            color: "#fff", fontWeight: 600, fontSize: 13,
            opacity: scrape.isPending ? 0.6 : 1, transition: "all 0.15s",
          }}
        >
          {scrape.isPending ? "Starting..." : scrape.isSuccess ? "✓ Scrape Running" : "⚡ Run Scrape"}
        </button>
      </div>

      {scrape.isSuccess && (
        <div style={{
          background: "var(--green-dim)", border: "1px solid var(--green)", borderRadius: 8,
          padding: "12px 20px", marginBottom: 24, fontSize: 13, color: "var(--green)",
        }}>
          Scrape started in background. Jobs will appear in a few minutes. The page auto-refreshes.
        </div>
      )}

      {/* Stat cards */}
      <div style={{ display: "flex", gap: 16, marginBottom: 32, flexWrap: "wrap" }}>
        <StatCard label="Total Jobs" value={statsLoading ? "—" : s.total} />
        <StatCard label="Apply" value={s.by_verdict?.APPLY || 0} color="var(--green)" />
        <StatCard label="Maybe" value={s.by_verdict?.MAYBE || 0} color="var(--yellow)" />
        <StatCard label="Skip" value={s.by_verdict?.SKIP || 0} color="var(--red)" />
        <StatCard label="Avg Score" value={s.avg_score || "—"} sub="out of 10" color="var(--blue)" />
        <StatCard label="Remote" value={s.remote_count || 0} color="var(--purple)" />
      </div>

      {/* Source breakdown */}
      {s.by_source && Object.keys(s.by_source).length > 0 && (
        <div style={{
          background: "var(--bg-raised)", borderRadius: 12, padding: "20px 24px",
          border: "1px solid var(--border)", marginBottom: 32,
        }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 16 }}>Jobs by Source</div>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            {Object.entries(s.by_source).sort((a, b) => b[1] - a[1]).map(([src, count]) => (
              <div key={src} style={{
                padding: "6px 14px", borderRadius: 20,
                background: "var(--bg-hover)", fontSize: 12, color: "var(--text-secondary)",
              }}>
                {src} <span style={{ fontWeight: 700, color: "var(--text-primary)", marginLeft: 4 }}>{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Top APPLY jobs */}
      <div style={{
        background: "var(--bg-surface)", borderRadius: 12, padding: 24,
        border: "1px solid var(--border)",
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
    </div>
  );
}
