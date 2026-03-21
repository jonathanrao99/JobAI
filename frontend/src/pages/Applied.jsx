import { useState } from "react";
import { useApplications, useUpdateApplicationStatus, useCreateApplication } from "../hooks/useJobs";

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

function ApplicationRow({ app, onUpdate }) {
  const [expanded, setExpanded] = useState(false);
  const job = app.jobs || {};
  const actions = NEXT_ACTIONS[app.status] || [];

  return (
    <div style={{
      background: "var(--bg-raised)", borderRadius: 10,
      border: "1px solid var(--border)", overflow: "hidden",
    }}>
      <div
        onClick={() => setExpanded(!expanded)}
        style={{
          display: "flex", alignItems: "center", gap: 16,
          padding: "16px 20px", cursor: "pointer",
        }}
      >
        <div style={{
          width: 40, height: 40, borderRadius: 10, display: "flex",
          alignItems: "center", justifyContent: "center", fontSize: 15,
          fontWeight: 700, flexShrink: 0,
          background: "var(--green-dim)", color: "var(--green)",
        }}>
          {job.ai_score || "—"}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <span style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)" }}>
              {job.title || "Unknown Role"}
            </span>
            <StatusBadge status={app.status} />
          </div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 3 }}>
            {job.company || "—"}
            {job.location ? ` · ${job.location}` : ""}
            {app.applied_at && (
              <span style={{ marginLeft: 12, color: "var(--text-muted)" }}>
                Applied {new Date(app.applied_at).toLocaleDateString()}
              </span>
            )}
          </div>
        </div>
        <span style={{
          color: "var(--text-muted)", fontSize: 18, flexShrink: 0,
          transition: "transform 0.15s", transform: expanded ? "rotate(180deg)" : "none",
        }}>
          ▾
        </span>
      </div>

      {expanded && (
        <div style={{ padding: "0 20px 20px", borderTop: "1px solid var(--border)" }}>
          <div style={{ display: "flex", gap: 12, paddingTop: 16, flexWrap: "wrap", alignItems: "center" }}>
            {job.job_url && (
              <a href={job.job_url} target="_blank" rel="noopener noreferrer" style={{
                padding: "7px 16px", borderRadius: 6, fontSize: 12, fontWeight: 600,
                background: "var(--accent)", color: "#fff", textDecoration: "none",
              }}>
                View Posting
              </a>
            )}
            {actions.map((a) => (
              <button
                key={a.status}
                onClick={(e) => { e.stopPropagation(); onUpdate(app.id, a.status); }}
                style={{
                  padding: "7px 14px", borderRadius: 6, fontSize: 11, fontWeight: 600,
                  border: "1px solid var(--border)", cursor: "pointer",
                  background: (STATUS_COLOR[a.status] || STATUS_COLOR.queued).bg,
                  color: (STATUS_COLOR[a.status] || STATUS_COLOR.queued).color,
                }}
              >
                {a.label}
              </button>
            ))}
          </div>
          {app.notes && (
            <div style={{ marginTop: 12, fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6 }}>
              {app.notes}
            </div>
          )}
          <div style={{ marginTop: 12, display: "flex", gap: 16, fontSize: 11, color: "var(--text-muted)" }}>
            <span>Created {new Date(app.created_at).toLocaleDateString()}</span>
            {job.source_board && <span>Source: {job.source_board}</span>}
            {job.is_remote && <span style={{ color: "var(--purple)" }}>Remote</span>}
          </div>
        </div>
      )}
    </div>
  );
}

export default function Applied() {
  const [statusFilter, setStatusFilter] = useState(null);
  const { data, isLoading } = useApplications(statusFilter);
  const updateStatus = useUpdateApplicationStatus();

  const apps = data?.applications || [];

  const handleUpdate = (appId, newStatus) => {
    updateStatus.mutate({ applicationId: appId, status: newStatus });
  };

  return (
    <div style={{ padding: "32px 40px", maxWidth: 1000, margin: "0 auto" }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 4 }}>Applications</h1>
      <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 24 }}>
        Track your application pipeline from queued to offer
      </p>

      {/* Status filter tabs */}
      <div style={{
        display: "flex", gap: 6, marginBottom: 24, flexWrap: "wrap",
        padding: "4px", background: "var(--bg-surface)", borderRadius: 10,
        border: "1px solid var(--border)",
      }}>
        {STATUS_GROUPS.map((g) => (
          <button
            key={g.key || "all"}
            onClick={() => setStatusFilter(g.key)}
            style={{
              padding: "8px 14px", borderRadius: 8, fontSize: 12, fontWeight: 600,
              border: "none", cursor: "pointer", transition: "all 0.15s",
              background: statusFilter === g.key ? "var(--accent)" : "transparent",
              color: statusFilter === g.key ? "#fff" : "var(--text-secondary)",
            }}
          >
            {g.label}
          </button>
        ))}
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
      ) : apps.length === 0 ? (
        <div style={{
          textAlign: "center", padding: 60, color: "var(--text-muted)", fontSize: 14,
          background: "var(--bg-raised)", borderRadius: 12, border: "1px solid var(--border)",
        }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>📋</div>
          No applications yet. Add jobs from the Job Board or Pipeline and start tracking.
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {apps.map((app) => (
            <ApplicationRow key={app.id} app={app} onUpdate={handleUpdate} />
          ))}
        </div>
      )}
    </div>
  );
}
