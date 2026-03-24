"use client";

import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import toast from "react-hot-toast";
import {
  fetchAuthenticatedBlob,
  resolveApiUrl,
  useApplications,
  usePrepareApplication,
  useUpdateApplicationStatus,
} from "@/hooks/useJobs";
import "./Pipeline.css";

function FormattedCopyBlock({ label, text }) {
  if (!text || !String(text).trim()) return null;
  const body = String(text).trim();
  const paragraphs = body.split(/\n\n+/).map((p) => p.trim()).filter(Boolean);
  const blocks =
    paragraphs.length > 0
      ? paragraphs
      : [body];

  return (
    <div className="pipeline-copy-block">
      <div className="pipeline-copy-block-head">
        <span className="pipeline-copy-block-label">{label}</span>
        <button
          type="button"
          className="pipeline-copy-btn"
          onClick={() => {
            navigator.clipboard.writeText(body).then(() => toast.success("Copied")).catch(() => toast.error("Copy failed"));
          }}
        >
          Copy
        </button>
      </div>
      <div className="pipeline-formatted-body">
        {blocks.map((para, i) => (
          <p key={i} className="pipeline-copy-para">
            {para.split("\n").map((line, j, arr) => (
              <Fragment key={j}>
                {line}
                {j < arr.length - 1 ? <br /> : null}
              </Fragment>
            ))}
          </p>
        ))}
      </div>
    </div>
  );
}

function OutreachContactsBlock({ contacts }) {
  if (!Array.isArray(contacts) || contacts.length === 0) return null;
  const roleLabel = (bucket) =>
    ({
      recruiter_talent: "Recruiter",
      hiring_manager: "Manager",
      director_plus: "Director+",
      relevant_ic: "Relevant IC",
    }[bucket] || "Contact");

  return (
    <div className="pipeline-copy-block">
      <div className="pipeline-copy-block-head">
        <span className="pipeline-copy-block-label">Outreach contacts</span>
      </div>
      <div className="pipeline-formatted-body">
        {contacts.map((c, idx) => (
          <div key={`${c.id || c.linkedin_url || c.email || idx}`} className="pipeline-contact-card">
            <div className="pipeline-contact-row">
              <strong className="pipeline-contact-name">{c.name || "Contact"}</strong>
              <span className="pipeline-contact-badge" data-bucket={c.role_bucket}>{roleLabel(c.role_bucket)}</span>
            </div>
            {c.title ? <div className="pipeline-contact-title">{c.title}</div> : null}
            {c.fit_reason ? <div className="pipeline-contact-reason">{c.fit_reason}</div> : null}
            <div className="pipeline-contact-links">
              {c.linkedin_url ? (
                <a href={c.linkedin_url} target="_blank" rel="noopener noreferrer">
                  LinkedIn
                </a>
              ) : null}
              {c.email ? (
                <button
                  type="button"
                  className="pipeline-copy-btn"
                  onClick={() => {
                    navigator.clipboard.writeText(c.email).then(() => toast.success("Email copied")).catch(() => toast.error("Copy failed"));
                  }}
                >
                  {c.email}
                </button>
              ) : (
                <span className="pipeline-contact-noemail">No email</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

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
  return (
    <span className="pipeline-status-badge" data-status={status}>
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

const JOBAI_MATERIALS_PREFIX = "__JOBAI_MATERIALS_JSON__:";

function parseJobaiMaterialsFromNotes(notes) {
  if (!notes || typeof notes !== "string") return {};
  const line = notes.split("\n").find((l) => l.trim().startsWith(JOBAI_MATERIALS_PREFIX));
  if (!line) return {};
  const json = line.slice(line.indexOf(":") + 1).trim();
  try {
    return JSON.parse(json);
  } catch {
    return {};
  }
}

/** Merge column values with JSON embedded in `notes` when DB migration not applied. */
function materialsForApp(app) {
  const fromNotes = parseJobaiMaterialsFromNotes(app.notes || "");
  return {
    cover_letter: app.cover_letter || "",
    linkedin_note: app.linkedin_note || fromNotes.linkedin_note || "",
    cold_email: app.cold_email || fromNotes.cold_email || "",
    cold_email_subject: app.cold_email_subject || fromNotes.cold_email_subject || "",
  };
}

function displayUserNotes(notes) {
  if (!notes || typeof notes !== "string") return null;
  const stripped = notes
    .split("\n")
    .filter((l) => !l.trim().startsWith(JOBAI_MATERIALS_PREFIX))
    .join("\n")
    .trim();
  return stripped || null;
}

function outreachContactsForApp(app) {
  const rows = Array.isArray(app?.application_contacts) ? app.application_contacts : [];
  return rows
    .map((row) => ({
      ...(row?.contacts || {}),
      role_bucket: row?.role_bucket || "",
      fit_reason: row?.fit_reason || "",
      relevance_rank: Number(row?.relevance_rank || 999),
    }))
    .filter((c) => c && !c.do_not_contact)
    .sort((a, b) => a.relevance_rank - b.relevance_rank)
    .slice(0, 5);
}

function ResumePdfFrame({ resumeId }) {
  const [blobUrl, setBlobUrl] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const urlRef = useRef(null);

  useEffect(() => {
    if (!resumeId) return;
    let cancelled = false;
    setLoadError(null);
    setBlobUrl(null);
    (async () => {
      try {
        const blob = await fetchAuthenticatedBlob(`/api/resumes/${resumeId}/download?format=pdf`);
        if (cancelled) return;
        if (urlRef.current) URL.revokeObjectURL(urlRef.current);
        const u = URL.createObjectURL(blob);
        urlRef.current = u;
        setBlobUrl(u);
      } catch (e) {
        if (!cancelled) setLoadError(e?.message || "Could not load PDF");
      }
    })();
    return () => {
      cancelled = true;
      if (urlRef.current) {
        URL.revokeObjectURL(urlRef.current);
        urlRef.current = null;
      }
    };
  }, [resumeId]);

  if (loadError) {
    return <p className="pipeline-materials-empty">{loadError}</p>;
  }
  if (!blobUrl) {
    return <p className="pipeline-materials-empty">Loading PDF…</p>;
  }
  return (
    <>
      <iframe title="Tailored resume PDF" className="pipeline-pdf-frame" src={blobUrl} />
      <a className="pipeline-pdf-open" href={blobUrl} target="_blank" rel="noopener noreferrer">
        Open PDF in new tab
      </a>
    </>
  );
}

export default function Applied() {
  const [statusFilter, setStatusFilter] = useState(null);
  const [search, setSearch] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [expandedId, setExpandedId] = useState(null);

  const { data, isLoading } = useApplications(statusFilter);
  const updateStatus = useUpdateApplicationStatus();
  const prepare = usePrepareApplication();

  const filteredApps = useMemo(() => {
    const apps = data?.applications || [];
    const q = (search || "").trim().toLowerCase();
    const fromTs = fromDate ? new Date(`${fromDate}T00:00:00`).getTime() : null;
    const toTs = toDate ? new Date(`${toDate}T23:59:59.999`).getTime() : null;

    return apps.filter((app) => {
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
  }, [data?.applications, search, fromDate, toDate]);

  const handleUpdate = (appId, newStatus) => {
    updateStatus.mutate({ applicationId: appId, status: newStatus });
  };

  const count = filteredApps.length;

  return (
    <div className="pipeline-page">
      <header className="pipeline-header">
        <div>
          <h1 className="pipeline-title">Pipeline</h1>
          <p className="pipeline-subtitle">
            Track stages and next steps · {count} application{count === 1 ? "" : "s"}
          </p>
        </div>
      </header>

      <div className="pipeline-toolbar">
        <input
          className="pipeline-search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search company or role…"
          type="search"
          autoComplete="off"
          aria-label="Search applications"
        />

        <div className="pipeline-field">
          <span className="pipeline-field-label">From</span>
          <input
            className="pipeline-date"
            type="date"
            value={fromDate}
            onChange={(e) => setFromDate(e.target.value)}
            aria-label="Filter from date"
          />
        </div>

        <div className="pipeline-field">
          <span className="pipeline-field-label">To</span>
          <input
            className="pipeline-date"
            type="date"
            value={toDate}
            onChange={(e) => setToDate(e.target.value)}
            aria-label="Filter to date"
          />
        </div>

        <div className="pipeline-field">
          <span className="pipeline-field-label">Stage</span>
          <select
            className="pipeline-select"
            value={statusFilter ?? "all"}
            onChange={(e) => setStatusFilter(e.target.value === "all" ? null : e.target.value)}
            aria-label="Filter by stage"
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
        <div className="pipeline-error" role="alert">
          {updateStatus.error?.message || "Failed to update status"}
        </div>
      )}

      {isLoading ? (
        <div className="pipeline-loading" role="status" aria-live="polite">
          Loading your pipeline…
        </div>
      ) : filteredApps.length === 0 ? (
        <div className="pipeline-empty">
          <p className="pipeline-empty-title">No applications match</p>
          <p className="pipeline-empty-hint">
            Adjust the stage filter or date range, or clear search to see more.
          </p>
        </div>
      ) : (
        <div className="pipeline-table-shell">
          <div className="pipeline-table-scroll">
            <table className="pipeline-table">
              <thead>
                <tr>
                  <th scope="col" className="pipeline-col-toggle" />
                  <th scope="col">Company</th>
                  <th scope="col">Role</th>
                  <th scope="col">Applied</th>
                  <th scope="col">Resume</th>
                  <th scope="col">Listing</th>
                </tr>
              </thead>
              <tbody>
                {filteredApps.map((app) => {
                  const job = app.jobs || {};
                  const expanded = expandedId === app.id;
                  const actions = NEXT_ACTIONS[app.status] || [];
                  const appliedDate = fmtDate(getAppDate(app));
                  const mat = materialsForApp(app);
                  const outreachContacts = outreachContactsForApp(app);
                  const userNotesOnly = displayUserNotes(app.notes);
                  const resumeUrl = app.resume_id
                    ? resolveApiUrl(`/api/resumes/${app.resume_id}/download?format=pdf`)
                    : null;

                  return (
                    <tr key={app.id}>
                      <td
                        colSpan={expanded ? 6 : undefined}
                        className={expanded ? "pipeline-cell-expanded" : undefined}
                      >
                        {expanded ? (
                          <div>
                            <div className="pipeline-expanded-bar">
                              <button
                                type="button"
                                className="pipeline-expand-btn is-open"
                                onClick={() => setExpandedId(null)}
                                aria-label="Collapse row"
                                aria-expanded="true"
                              >
                                ›
                              </button>
                              <span className="pipeline-expanded-title">{job.title || "Unknown Role"}</span>
                              <StatusBadge status={app.status} />
                            </div>
                            <div className="pipeline-expanded-body">
                              <div className="pipeline-expanded-grid">
                                <div>
                                  <div className="pipeline-panel-label">Next steps</div>
                                  <div className="pipeline-actions-row">
                                    {actions.length ? (
                                      actions.map((a) => (
                                        <button
                                          key={a.status}
                                          type="button"
                                          className="pipeline-action-btn"
                                          data-action={a.status}
                                          onClick={() => handleUpdate(app.id, a.status)}
                                        >
                                          {a.label}
                                        </button>
                                      ))
                                    ) : (
                                      <span className="pipeline-actions-none">No actions for this stage.</span>
                                    )}
                                  </div>
                                </div>
                                <div className="pipeline-details-col">
                                  <div className="pipeline-panel-label">Details</div>
                                  <div>
                                    <div>Created {app.created_at ? new Date(app.created_at).toLocaleDateString() : "—"}</div>
                                    {job.source_board && (
                                      <div>
                                        Source: {job.source_board}
                                      </div>
                                    )}
                                    {job.is_remote ? <div className="pipeline-remote">Remote</div> : null}
                                    {userNotesOnly ? <div className="pipeline-notes">{userNotesOnly}</div> : null}
                                  </div>
                                </div>
                              </div>

                              <div className="pipeline-materials">
                                <div className="pipeline-materials-toolbar">
                                  <div className="pipeline-panel-label">Application materials</div>
                                  <button
                                    type="button"
                                    className="pipeline-regenerate-btn"
                                    disabled={prepare.isPending}
                                    onClick={() => {
                                      const tid = toast.loading("Regenerating materials…");
                                      prepare.mutate(app.id, {
                                        onSettled: () => toast.dismiss(tid),
                                        onSuccess: () => toast.success("Materials updated"),
                                        onError: (e) => toast.error(e?.message || "Failed to regenerate"),
                                      });
                                    }}
                                  >
                                    {prepare.isPending ? "Working…" : "Regenerate materials"}
                                  </button>
                                </div>
                                <p className="pipeline-materials-hint">
                                  Tailored resume PDF, cover letter, LinkedIn note, and cold email are generated when you add a job from the Job Board (or use Regenerate).
                                </p>
                                <div className="pipeline-materials-layout">
                                  <div className="pipeline-left-panels">
                                    {app.resume_id ? (
                                      <div className="pipeline-pdf-panel">
                                        <div className="pipeline-panel-label">Resume preview</div>
                                        <ResumePdfFrame resumeId={app.resume_id} />
                                      </div>
                                    ) : (
                                      <div className="pipeline-pdf-panel pipeline-pdf-panel--empty">
                                        <div className="pipeline-panel-label">Resume preview</div>
                                        <p className="pipeline-materials-empty">No tailored resume yet. Regenerate to create one.</p>
                                      </div>
                                    )}
                                    <FormattedCopyBlock label="Cover letter" text={mat.cover_letter} />
                                  </div>
                                  <div className="pipeline-text-panels">
                                    <OutreachContactsBlock contacts={outreachContacts} />
                                    <FormattedCopyBlock label="LinkedIn note" text={mat.linkedin_note} />
                                    <FormattedCopyBlock label="Cold email subject" text={mat.cold_email_subject} />
                                    <FormattedCopyBlock label="Cold email" text={mat.cold_email} />
                                    {!mat.cover_letter && !mat.cold_email && !mat.linkedin_note && !mat.cold_email_subject ? (
                                      <p className="pipeline-materials-empty">No text materials yet.</p>
                                    ) : null}
                                  </div>
                                </div>
                              </div>
                            </div>
                          </div>
                        ) : (
                          <button
                            type="button"
                            className="pipeline-expand-btn"
                            onClick={() => setExpandedId(app.id)}
                            aria-label="Expand row"
                            aria-expanded={false}
                          >
                            ›
                          </button>
                        )}
                      </td>
                      {!expanded && (
                        <>
                          <td className="pipeline-cell-muted">{job.company || "—"}</td>
                          <td>
                            <div className="pipeline-title-cell-inner">
                              <span className="pipeline-cell-title">{job.title || "Unknown Role"}</span>
                              <StatusBadge status={app.status} />
                            </div>
                          </td>
                          <td className="pipeline-cell-muted">{appliedDate}</td>
                          <td>
                            {resumeUrl ? (
                              <a className="pipeline-btn-resume" href={resumeUrl}>
                                Download
                              </a>
                            ) : (
                              <span className="pipeline-dash">—</span>
                            )}
                          </td>
                          <td>
                            {job.job_url ? (
                              <a
                                className="pipeline-btn-view"
                                href={job.job_url}
                                target="_blank"
                                rel="noopener noreferrer"
                              >
                                Open ↗
                              </a>
                            ) : (
                              <span className="pipeline-dash">—</span>
                            )}
                          </td>
                        </>
                      )}
                    </tr>
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
