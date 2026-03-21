import { useMemo, useState } from "react";
import { useApplications, useUpdateApplicationStatus } from "../hooks/useJobs";

const STATUS_GROUPS = [
  { key: null, label: "All" },
  { key: "queued", label: "Queued" },
  { key: "applied", label: "Applied" },
  { key: "response_received", label: "Responded" },
  { key: "phone_screen", label: "Phone Screen" },
  { key: "technical", label: "Technical" },
  { key: "final_round", label: "Final Round" },
  { key: "offer", label: "Offer" },
  { key: "rejected", label: "Rejected" },
  { key: "ghosted", label: "Ghosted" },
];

const STATUS_COLOR = {
  queued: { bg: "var(--blue-dim)", color: "var(--blue)" },
  applied: { bg: "var(--green-dim)", color: "var(--green)" },
  response_received: { bg: "var(--accent-glow)", color: "var(--accent)" },
  phone_screen: { bg: "var(--accent-glow)", color: "var(--accent)" },
  technical: { bg: "var(--accent-glow)", color: "var(--accent)" },
  final_round: { bg: "var(--accent-glow)", color: "var(--accent)" },
  offer: { bg: "var(--green-dim)", color: "var(--green)" },
  rejected: { bg: "var(--red-dim)", color: "var(--red)" },
  ghosted: { bg: "var(--red-dim)", color: "var(--text-muted)" },
  manual_required: { bg: "var(--yellow-dim)", color: "var(--yellow)" },
  skipped: { bg: "var(--bg-hover)", color: "var(--text-muted)" },
};

const NEXT_ACTIONS = {
  queued: [{ status: "applied", label: "Mark Applied" }],
  applied: [
    { status: "response_received", label: "Got Response" },
    { status: "rejected", label: "Rejected" },
    { status: "ghosted", label: "Ghosted" },
  ],
  response_received: [
    { status: "phone_screen", label: "Phone Screen" },
    { status: "rejected", label: "Rejected" },
  ],
  phone_screen: [
    { status: "technical", label: "Technical" },
    { status: "rejected", label: "Rejected" },
  ],
  technical: [
    { status: "final_round", label: "Final Round" },
    { status: "rejected", label: "Rejected" },
  ],
  final_round: [
    { status: "offer", label: "Offer!" },
    { status: "rejected", label: "Rejected" },
  ],
};

function StatusBadge({ status }) {
  const s = STATUS_COLOR[status] || STATUS_COLOR.queued;
  return (
    <span style={{
      padding: "3px 10px", borderRadius: 12, fontSize: 11, fontWeight: 700,
      background: s.bg, color: s.color, textTransform: "capitalize",
    }}>
      {status.replace(/_/g, " ")}
    </span>
  );
}

function getAppDate(app) {
  const dt = app.applied_at || app.created_at;
  if (!dt) return null;
  const d = new Date(dt);
  return Number.isNaN(d.getTime()) ? null : d;
}

function fmtDate(d) {
  if (!d) return "—";
  return d.toLocaleDateString();
}

export default function Applied() {
  const [statusFilter, setStatusFilter] = useState("applied");
  const [search, setSearch] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [expandedId, setExpandedId] = useState(null);

  const { data, isLoading } = useApplications(statusFilter);
  const updateStatus = useUpdateApplicationStatus();

  const apps = data?.applications || [];

  const filteredApps = useMemo(() => {
    const q = (search || "").trim().toLowerCase();
    const fromTs = fromDate ? new Date(`${fromDate}T00:00:00`).getTime() : null;
    const toTs = toDate ? new Date(`${toDate}T23:59:59.999`).getTime() : null;

    return (apps || []).filter((app) => {
      const job = app.jobs || {};
      const company = (job.company || "").toLowerCase();
      const title = (job.title || "").toLowerCase();
      const hay = `${company} ${title}`.trim();

      if (q && !hay.includes(q)) return false;

      if (fromTs || toTs) {
        const d = getAppDate(app);
        if (!d) return false;
        const ts = d.getTime();
        if (fromTs && ts < fromTs) return false;
        if (toTs && ts > toTs) return false;
      }

      return true;
    });
  }, [apps, search, fromDate, toDate]);

  const handleUpdate = (appId, newStatus) => {
    updateStatus.mutate({ applicationId: appId, status: newStatus });
  };

  return (
    <div style={{ padding: "32px 40px", maxWidth: 1000, margin: "0 auto" }}>
      <div style={{ marginBottom: 14 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 4 }}>Applied Jobs</h1>
        <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>
          {filteredApps.length} application{filteredApps.length === 1 ? "" : "s"}
        </p>
      </div>

      <div style={{
        display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center",
        marginBottom: 20,
      }}>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search company, title…"
          style={{
            flex: "1 1 260px",
            padding: "10px 16px", borderRadius: 8, fontSize: 13,
            background: "var(--bg-raised)", border: "1px solid var(--border)",
            color: "var(--text-primary)", outline: "none",
          }}
        />

        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <label style={{ fontSize: 12, color: "var(--text-muted)" }}>From</label>
          <input
            type="date"
            value={fromDate}
            onChange={(e) => setFromDate(e.target.value)}
            style={{
              padding: "8px 10px", borderRadius: 8, fontSize: 12,
              background: "var(--bg-raised)", border: "1px solid var(--border)",
              color: "var(--text-primary)", outline: "none",
            }}
          />
        </div>

        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <label style={{ fontSize: 12, color: "var(--text-muted)" }}>To</label>
          <input
            type="date"
            value={toDate}
            onChange={(e) => setToDate(e.target.value)}
            style={{
              padding: "8px 10px", borderRadius: 8, fontSize: 12,
              background: "var(--bg-raised)", border: "1px solid var(--border)",
              color: "var(--text-primary)", outline: "none",
            }}
          />
        </div>

        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <label style={{ fontSize: 12, color: "var(--text-muted)" }}>Status</label>
          <select
            value={statusFilter ?? "all"}
            onChange={(e) => setStatusFilter(e.target.value === "all" ? null : e.target.value)}
            style={{
              padding: "9px 10px", borderRadius: 8, fontSize: 12,
              background: "var(--bg-raised)", border: "1px solid var(--border)",
              color: "var(--text-primary)", outline: "none",
            }}
          >
            {STATUS_GROUPS.map((g) => (
              <option key={g.key ?? "all"} value={g.key ?? "all"}>
                {g.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {updateStatus.isError && (
        <div style={{
          marginBottom: 16, padding: "12px 16px", borderRadius: 8,
          background: "var(--red-dim)", color: "var(--red)", fontSize: 13,
        }}>
          {updateStatus.error?.message || "Failed to update status"}
        </div>
      )}

      {isLoading ? (
        <div style={{ color: "var(--text-muted)", padding: 40, textAlign: "center" }}>Loading…</div>
      ) : filteredApps.length === 0 ? (
        <div style={{
          textAlign: "center", padding: 60, color: "var(--text-muted)", fontSize: 14,
          background: "var(--bg-raised)", borderRadius: 12, border: "1px solid var(--border)",
        }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>📋</div>
          No matching applications. Try a different status or date range.
        </div>
      ) : (
        <div style={{
          background: "var(--bg-raised)", borderRadius: 12, border: "1px solid var(--border)",
          overflow: "hidden",
        }}>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ textAlign: "left", color: "var(--text-muted)", borderBottom: "1px solid var(--border)" }}>
                  <th style={{ padding: "10px 14px", width: 36 }} />
                  <th style={{ padding: "10px 14px" }}>Company</th>
                  <th style={{ padding: "10px 14px" }}>Job Title</th>
                  <th style={{ padding: "10px 14px" }}>Applied</th>
                  <th style={{ padding: "10px 14px" }}>Resume</th>
                  <th style={{ padding: "10px 14px" }}>Link</th>
                </tr>
              </thead>
              <tbody>
                {filteredApps.map((app, idx) => {
                  const job = app.jobs || {};
                  const expanded = expandedId === app.id;
                  const actions = NEXT_ACTIONS[app.status] || [];
                  const appliedDate = fmtDate(getAppDate(app));
                  const resumeUrl = app.resume_id ? `/api/resumes/${app.resume_id}/download?format=pdf` : null;

                  return (
                    <>
                      <tr
                        key={app.id}
                        style={{
                          borderBottom: "1px solid var(--border)",
                          background: idx % 2 === 0 ? "transparent" : "var(--bg-hover)",
                        }}
                      >
                        <td style={{ padding: "12px 14px" }}>
                          <button
                            type="button"
                            onClick={() => setExpandedId(expanded ? null : app.id)}
                            style={{
                              width: 28, height: 28, borderRadius: 8,
                              border: "1px solid var(--border)", cursor: "pointer",
                              background: "var(--bg-surface)",
                              color: "var(--text-secondary)",
                              transform: expanded ? "rotate(90deg)" : "rotate(0deg)",
                              transition: "transform 0.15s",
                            }}
                            aria-label={expanded ? "Collapse" : "Expand"}
                          >
                            ›
                          </button>
                        </td>
                        <td style={{ padding: "12px 14px", color: "var(--text-secondary)" }}>
                          {job.company || "—"}
                        </td>
                        <td style={{ padding: "12px 14px" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                            <span style={{ fontSize: 13, fontWeight: 700, color: "var(--text-primary)" }}>
                              {job.title || "Unknown Role"}
                            </span>
                            <StatusBadge status={app.status} />
                          </div>
                        </td>
                        <td style={{ padding: "12px 14px", color: "var(--text-muted)", whiteSpace: "nowrap" }}>
                          {appliedDate}
                        </td>
                        <td style={{ padding: "12px 14px" }}>
                          {resumeUrl ? (
                            <a
                              href={resumeUrl}
                              style={{
                                padding: "8px 12px",
                                borderRadius: 8,
                                fontSize: 12,
                                fontWeight: 700,
                                background: "var(--green)",
                                color: "#fff",
                                textDecoration: "none",
                                display: "inline-block",
                              }}
                            >
                              Download
                            </a>
                          ) : (
                            <span style={{ color: "var(--text-muted)" }}>—</span>
                          )}
                        </td>
                        <td style={{ padding: "12px 14px" }}>
                          {job.job_url ? (
                            <a
                              href={job.job_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              style={{
                                padding: "8px 12px",
                                borderRadius: 8,
                                fontSize: 12,
                                fontWeight: 700,
                                background: "var(--bg-hover)",
                                color: "var(--blue)",
                                border: "1px solid var(--border)",
                                textDecoration: "none",
                                display: "inline-block",
                              }}
                            >
                              View
                            </a>
                          ) : (
                            <span style={{ color: "var(--text-muted)" }}>—</span>
                          )}
                        </td>
                      </tr>

                      {expanded && (
                        <tr>
                          <td colSpan={6} style={{ padding: 16, background: "var(--bg-base)" }}>
                            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                              <div>
                                <div style={{ fontSize: 12, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: 1.2, marginBottom: 8 }}>
                                  Actions
                                </div>
                                <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                                  {actions.length ? (
                                    actions.map((a) => (
                                      <button
                                        key={a.status}
                                        type="button"
                                        onClick={() => handleUpdate(app.id, a.status)}
                                        style={{
                                          padding: "8px 12px",
                                          borderRadius: 8,
                                          fontSize: 12,
                                          fontWeight: 700,
                                          border: "1px solid var(--border)",
                                          cursor: "pointer",
                                          background: (STATUS_COLOR[a.status] || STATUS_COLOR.queued).bg,
                                          color: (STATUS_COLOR[a.status] || STATUS_COLOR.queued).color,
                                        }}
                                      >
                                        {a.label}
                                      </button>
                                    ))
                                  ) : (
                                    <span style={{ color: "var(--text-muted)", fontSize: 12 }}>No next actions for this status.</span>
                                  )}
                                </div>
                              </div>

                              <div style={{ minWidth: 260 }}>
                                <div style={{ fontSize: 12, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: 1.2, marginBottom: 8 }}>
                                  Details
                                </div>
                                <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6 }}>
                                  <div>
                                    Created {app.created_at ? new Date(app.created_at).toLocaleDateString() : "—"}
                                  </div>
                                  {job.source_board && <div>Source: {job.source_board}</div>}
                                  {job.is_remote && <div style={{ color: "var(--purple)" }}>Remote</div>}
                                  {app.notes && <div style={{ marginTop: 10, color: "var(--text-muted)" }}>{app.notes}</div>}
                                </div>
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
