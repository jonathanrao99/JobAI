import { Link } from "react-router-dom";
import { useJobs } from "../hooks/useJobs";

export default function Outreach() {
  const { data, isLoading } = useJobs({ verdict: "APPLY", limit: 15 });

  const jobs = data?.jobs || [];

  return (
    <div style={{ padding: "32px 40px", maxWidth: 900, margin: "0 auto" }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0 }}>Outreach</h1>
      <p style={{ fontSize: 13, color: "var(--text-secondary)", marginTop: 4, marginBottom: 28 }}>
        Track who you&apos;ve contacted and keep a simple cold-email pattern. Full CRM features aren&apos;t wired yet—use this as a checklist against your top APPLY matches.
      </p>

      <div style={{
        background: "var(--bg-raised)", borderRadius: 12, padding: "20px 24px",
        border: "1px solid var(--border)", marginBottom: 24,
      }}>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>Email template (edit before sending)</div>
        <pre style={{
          margin: 0, fontSize: 12, lineHeight: 1.55, color: "var(--text-secondary)",
          whiteSpace: "pre-wrap", fontFamily: "ui-monospace, monospace",
        }}>
{`Hi [Name or Hiring team],

I applied for the [Role] role at [Company] and wanted to share why I'm a strong fit: [1–2 sentences tied to the JD].

I've attached my resume. Happy to chat this week if useful.

Best,
[Your name]`}
        </pre>
      </div>

      <div style={{
        background: "var(--bg-surface)", borderRadius: 12, padding: 24,
        border: "1px solid var(--border)",
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <div style={{ fontSize: 15, fontWeight: 600 }}>APPLY queue</div>
          <Link to="/pipeline" style={{ fontSize: 12, color: "var(--accent)" }}>Open pipeline →</Link>
        </div>
        {isLoading ? (
          <div style={{ color: "var(--text-muted)", fontSize: 13 }}>Loading…</div>
        ) : jobs.length === 0 ? (
          <div style={{ color: "var(--text-muted)", fontSize: 13 }}>
            No APPLY jobs yet. Promote roles from the pipeline or run a scrape.
          </div>
        ) : (
          <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
            {jobs.map((job) => (
              <li
                key={job.id}
                style={{
                  display: "flex", alignItems: "flex-start", gap: 12,
                  padding: "12px 0", borderBottom: "1px solid var(--border)",
                }}
              >
                <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", flexShrink: 0 }}>
                  <input type="checkbox" style={{ accentColor: "var(--accent)" }} />
                </label>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)" }}>
                    {job.title}
                  </div>
                  <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 2 }}>
                    {job.company}
                    {job.location ? ` · ${job.location}` : ""}
                  </div>
                </div>
                {job.job_url && (
                  <a
                    href={job.job_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ fontSize: 12, color: "var(--blue)", flexShrink: 0 }}
                  >
                    Posting
                  </a>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
