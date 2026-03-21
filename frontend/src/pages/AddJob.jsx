import { useState } from "react";
import { useAddManualJob, useResumes } from "../hooks/useJobs";

export default function AddJob() {
  const [title, setTitle] = useState("");
  const [company, setCompany] = useState("");
  const [jobUrl, setJobUrl] = useState("");
  const [location, setLocation] = useState("");
  const [description, setDescription] = useState("");
  const [isRemote, setIsRemote] = useState(false);
  const [tailor, setTailor] = useState(true);
  const [completedJobs, setCompletedJobs] = useState([]);
  const [selectedJob, setSelectedJob] = useState(null);

  const addJob = useAddManualJob();

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!title.trim() || !company.trim() || !jobUrl.trim()) return;

    addJob.mutate(
      { title, company, job_url: jobUrl, location, description, is_remote: isRemote, tailor },
      {
        onSuccess: (res) => {
          const entry = {
            id: res.job?.id,
            title,
            company,
            hasTailor: !!res.tailor_result,
            resumeId: res.tailor_result?.resume_id || null,
            pdfPath: res.tailor_result?.pdf_path || null,
          };
          setCompletedJobs((prev) => [entry, ...prev]);
          setSelectedJob(entry);
          setTitle("");
          setCompany("");
          setJobUrl("");
          setLocation("");
          setDescription("");
        },
      },
    );
  };

  return (
    <div style={{ padding: "32px 40px", maxWidth: 1100, margin: "0 auto" }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 4 }}>Add Job</h1>
      <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 28 }}>
        Paste a job link and description to add it to your pipeline and generate a tailored resume
      </p>

      <div style={{ display: "flex", gap: 32, alignItems: "flex-start", flexWrap: "wrap" }}>
        {/* Left: form */}
        <form
          onSubmit={handleSubmit}
          style={{
            flex: "1 1 360px", background: "var(--bg-surface)", borderRadius: 12,
            padding: 28, border: "1px solid var(--border)",
          }}
        >
          <div style={{ marginBottom: 20 }}>
            <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", display: "block", marginBottom: 6 }}>
              Job Title *
            </label>
            <input
              type="text" required value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Senior Software Engineer"
              style={{
                width: "100%", padding: "10px 14px", borderRadius: 8, fontSize: 13,
                background: "var(--bg-raised)", border: "1px solid var(--border)",
                color: "var(--text-primary)", outline: "none",
              }}
            />
          </div>

          <div style={{ marginBottom: 20 }}>
            <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", display: "block", marginBottom: 6 }}>
              Company *
            </label>
            <input
              type="text" required value={company}
              onChange={(e) => setCompany(e.target.value)}
              placeholder="Stripe"
              style={{
                width: "100%", padding: "10px 14px", borderRadius: 8, fontSize: 13,
                background: "var(--bg-raised)", border: "1px solid var(--border)",
                color: "var(--text-primary)", outline: "none",
              }}
            />
          </div>

          <div style={{ marginBottom: 20 }}>
            <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", display: "block", marginBottom: 6 }}>
              Job Link *
            </label>
            <input
              type="url" required value={jobUrl}
              onChange={(e) => setJobUrl(e.target.value)}
              placeholder="https://www.linkedin.com/jobs/view/..."
              style={{
                width: "100%", padding: "10px 14px", borderRadius: 8, fontSize: 13,
                background: "var(--bg-raised)", border: "1px solid var(--border)",
                color: "var(--text-primary)", outline: "none",
              }}
            />
          </div>

          <div style={{ display: "flex", gap: 16, marginBottom: 20 }}>
            <div style={{ flex: 1 }}>
              <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", display: "block", marginBottom: 6 }}>
                Location
              </label>
              <input
                type="text" value={location}
                onChange={(e) => setLocation(e.target.value)}
                placeholder="San Francisco, CA"
                style={{
                  width: "100%", padding: "10px 14px", borderRadius: 8, fontSize: 13,
                  background: "var(--bg-raised)", border: "1px solid var(--border)",
                  color: "var(--text-primary)", outline: "none",
                }}
              />
            </div>
            <label style={{
              display: "flex", alignItems: "flex-end", gap: 8, paddingBottom: 10,
              fontSize: 12, color: "var(--text-secondary)", cursor: "pointer", flexShrink: 0,
            }}>
              <input
                type="checkbox" checked={isRemote}
                onChange={(e) => setIsRemote(e.target.checked)}
                style={{ accentColor: "var(--accent)" }}
              />
              Remote
            </label>
          </div>

          <div style={{ marginBottom: 20 }}>
            <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", display: "block", marginBottom: 6 }}>
              Job Description
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Paste the full job description here..."
              rows={8}
              style={{
                width: "100%", padding: "10px 14px", borderRadius: 8, fontSize: 13,
                background: "var(--bg-raised)", border: "1px solid var(--border)",
                color: "var(--text-primary)", outline: "none", resize: "vertical",
                lineHeight: 1.6, fontFamily: "inherit",
              }}
            />
          </div>

          <label style={{
            display: "flex", alignItems: "center", gap: 8, marginBottom: 24,
            fontSize: 13, color: "var(--text-secondary)", cursor: "pointer",
          }}>
            <input
              type="checkbox" checked={tailor}
              onChange={(e) => setTailor(e.target.checked)}
              style={{ accentColor: "var(--accent)" }}
            />
            Auto-tailor resume for this job
          </label>

          <button
            type="submit"
            disabled={addJob.isPending || !title.trim() || !company.trim() || !jobUrl.trim()}
            style={{
              width: "100%", padding: "12px 0", borderRadius: 8, border: "none",
              cursor: addJob.isPending ? "wait" : "pointer",
              background: addJob.isPending ? "var(--border)" : "var(--accent)",
              color: "#fff", fontWeight: 700, fontSize: 14,
              opacity: addJob.isPending ? 0.7 : 1, transition: "all 0.15s",
            }}
          >
            {addJob.isPending ? "Adding…" : "Add Job"}
          </button>

          {addJob.isError && (
            <div style={{
              marginTop: 12, padding: "10px 14px", borderRadius: 8,
              background: "var(--red-dim)", color: "var(--red)", fontSize: 12,
            }}>
              {addJob.error?.message || "Failed to add job"}
            </div>
          )}
        </form>

        {/* Right: completed jobs list */}
        <div style={{ flex: "1 1 340px", minWidth: 300 }}>
          <div style={{
            background: "var(--bg-surface)", borderRadius: 12,
            border: "1px solid var(--border)", overflow: "hidden",
          }}>
            <div style={{
              padding: "16px 20px", borderBottom: "1px solid var(--border)",
              display: "flex", justifyContent: "space-between", alignItems: "center",
            }}>
              <span style={{ fontSize: 14, fontWeight: 600 }}>
                {completedJobs.length} Added Job{completedJobs.length !== 1 ? "s" : ""}
              </span>
            </div>

            {completedJobs.length === 0 ? (
              <div style={{ padding: "40px 20px", textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>
                Jobs you add will appear here with resume download links
              </div>
            ) : (
              <div>
                {completedJobs.map((cj) => (
                  <div
                    key={cj.id}
                    onClick={() => setSelectedJob(cj)}
                    style={{
                      padding: "14px 20px", cursor: "pointer",
                      borderBottom: "1px solid var(--border)",
                      background: selectedJob?.id === cj.id ? "var(--bg-hover)" : "transparent",
                      transition: "background 0.1s",
                    }}
                  >
                    <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)", marginBottom: 2 }}>
                      {cj.title}
                    </div>
                    <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>{cj.company}</div>
                    <div style={{ display: "flex", gap: 8, marginTop: 8, alignItems: "center" }}>
                      {cj.hasTailor ? (
                        <span style={{
                          fontSize: 11, padding: "2px 8px", borderRadius: 10,
                          background: "var(--green-dim)", color: "var(--green)", fontWeight: 600,
                        }}>
                          ✓ Resume Ready
                        </span>
                      ) : (
                        <span style={{
                          fontSize: 11, padding: "2px 8px", borderRadius: 10,
                          background: "var(--blue-dim)", color: "var(--blue)", fontWeight: 600,
                        }}>
                          Added
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Resume download panel */}
          {selectedJob?.resumeId && (
            <div style={{
              marginTop: 16, background: "var(--bg-surface)", borderRadius: 12,
              padding: 20, border: "1px solid var(--border)",
            }}>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>
                Resume for {selectedJob.title}
              </div>
              <div style={{ display: "flex", gap: 10 }}>
                <a
                  href={`/api/resumes/${selectedJob.resumeId}/download?format=pdf`}
                  style={{
                    padding: "8px 16px", borderRadius: 6, fontSize: 12, fontWeight: 600,
                    background: "var(--green)", color: "#fff", textDecoration: "none",
                    display: "inline-block",
                  }}
                >
                  Download PDF
                </a>
                <a
                  href={`/api/resumes/${selectedJob.resumeId}/download?format=tex`}
                  style={{
                    padding: "8px 16px", borderRadius: 6, fontSize: 12, fontWeight: 600,
                    background: "var(--bg-hover)", color: "var(--text-primary)",
                    border: "1px solid var(--border)", textDecoration: "none",
                    display: "inline-block",
                  }}
                >
                  Download TeX
                </a>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
