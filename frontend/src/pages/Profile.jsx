import { useEffect, useState } from "react";
import { useProfile, useSaveProfile } from "../hooks/useJobs";
import "./Profile.css";

const emptyEdu = () => ({
  university: "",
  degree: "",
  major: "",
  graduation_year: "",
  gpa: "",
});

const emptyExp = () => ({
  company: "",
  role: "",
  duration: "",
  bulletsText: "",
});

const emptyProj = () => ({
  name: "",
  description: "",
  techStack: "",
  github_url: "",
  impact: "",
});

function formatSaved(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export default function Profile() {
  const { data, isLoading, isError, error } = useProfile();
  const save = useSaveProfile();

  const [personal, setPersonal] = useState({
    full_name: "",
    phone: "",
    email: "",
    linkedin: "",
    github: "",
    website: "",
  });
  const [skills, setSkills] = useState("");
  const [education, setEducation] = useState([emptyEdu()]);
  const [experience, setExperience] = useState([emptyExp()]);
  const [projects, setProjects] = useState([emptyProj()]);
  const [lastSaved, setLastSaved] = useState(null);

  useEffect(() => {
    if (!data?.form) return;
    const f = data.form;
    setPersonal({
      full_name: f.personal?.full_name || "",
      phone: f.personal?.phone || "",
      email: f.personal?.email || "",
      linkedin: f.personal?.linkedin || "",
      github: f.personal?.github || "",
      website: f.personal?.website || "",
    });
    setSkills(f.skills || "");
    const edu = (f.education || []).length ? f.education : [emptyEdu()];
    setEducation(
      edu.map((e) => ({
        university: e.university || "",
        degree: e.degree || "",
        major: e.major || "",
        graduation_year: e.graduation_year != null ? String(e.graduation_year) : "",
        gpa: e.gpa || "",
      })),
    );
    const ex = (f.work_experience || []).length
      ? f.work_experience.map((w) => ({
          company: w.company || "",
          role: w.role || "",
          duration: w.duration || "",
          bulletsText: Array.isArray(w.bullets) ? w.bullets.join("\n") : "",
        }))
      : [emptyExp()];
    setExperience(ex);
    const pr = (f.projects || []).length
      ? f.projects.map((p) => ({
          name: p.name || "",
          description: p.description || "",
          techStack: Array.isArray(p.tech_stack) ? p.tech_stack.join(", ") : "",
          github_url: p.github_url || "",
          impact: p.impact || "",
        }))
      : [emptyProj()];
    setProjects(pr);
    setLastSaved(data.last_saved);
  }, [data]);

  useEffect(() => {
    if (save.isSuccess && save.data?.last_saved) {
      setLastSaved(save.data.last_saved);
    }
  }, [save.isSuccess, save.data]);

  const handleSubmit = (e) => {
    e.preventDefault();
    const payload = {
      personal: {
        full_name: personal.full_name.trim(),
        phone: personal.phone.trim(),
        email: personal.email.trim(),
        linkedin: personal.linkedin.trim(),
        github: personal.github.trim(),
        website: personal.website.trim(),
      },
      skills: skills.trim(),
      education: education.map((e) => ({
        university: e.university.trim(),
        degree: e.degree.trim(),
        major: e.major.trim(),
        graduation_year: e.graduation_year === "" ? null : parseInt(e.graduation_year, 10) || null,
        gpa: e.gpa.trim(),
      })),
      work_experience: experience.map((w) => ({
        company: w.company.trim(),
        role: w.role.trim(),
        duration: w.duration.trim(),
        bullets: w.bulletsText
          .split("\n")
          .map((s) => s.trim())
          .filter(Boolean),
      })),
      projects: projects.map((p) => ({
        name: p.name.trim(),
        description: p.description.trim(),
        tech_stack: p.techStack
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        github_url: p.github_url.trim(),
        impact: p.impact.trim(),
      })),
    };
    save.mutate(payload);
  };

  const eduEmpty = education.every(
    (e) => !e.university && !e.degree && !e.major && !e.graduation_year && !e.gpa,
  );
  const expEmpty = experience.every((w) => !w.company && !w.role && !w.duration && !w.bulletsText);
  const projEmpty = projects.every(
    (p) => !p.name && !p.description && !p.techStack && !p.github_url && !p.impact,
  );

  if (isLoading) {
    return (
      <div className="profile-page" style={{ color: "var(--text-muted)" }}>
        Loading profile…
      </div>
    );
  }

  if (isError) {
    return (
      <div className="profile-page">
        <h1 className="profile-page__title">Profile</h1>
        <p style={{ color: "var(--red)", fontSize: 14 }}>{error?.message || "Could not load profile."}</p>
        <p style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 16, lineHeight: 1.6 }}>
          Ensure <code style={{ fontSize: 12 }}>data/candidate_profile.json</code> exists in the repo. The API
          reads and writes that file.
        </p>
      </div>
    );
  }

  return (
    <div className="profile-page">
      <header className="profile-page__hero">
        <h1 className="profile-page__title">Profile</h1>
        <p className="profile-page__subtitle">Candidate details used for resume tailoring and job matching.</p>
        <p className="profile-page__meta">Last saved · {formatSaved(lastSaved || data?.last_saved)}</p>
      </header>

      <form onSubmit={handleSubmit}>
        <div className="profile-card">
          <div className="profile-card__inner">
            <div className="profile-card__head">
              <p className="profile-card__kicker">Contact</p>
              <h2 className="profile-card__title">Personal information</h2>
              <p className="profile-card__hint">Name, phone, and links appear on tailored resumes and outreach.</p>
            </div>
            <div className="profile-grid-2">
              <div>
                <label className="profile-label">
                  Full name<span className="req">*</span>
                </label>
                <input
                  required
                  className="profile-input"
                  value={personal.full_name}
                  onChange={(e) => setPersonal((p) => ({ ...p, full_name: e.target.value }))}
                  placeholder="John Doe"
                />
              </div>
              <div>
                <label className="profile-label">
                  Phone<span className="req">*</span>
                </label>
                <input
                  required
                  className="profile-input"
                  value={personal.phone}
                  onChange={(e) => setPersonal((p) => ({ ...p, phone: e.target.value }))}
                  placeholder="(555) 123-4567"
                />
              </div>
              <div>
                <label className="profile-label">
                  Email<span className="req">*</span>
                </label>
                <input
                  required
                  type="email"
                  className="profile-input"
                  value={personal.email}
                  onChange={(e) => setPersonal((p) => ({ ...p, email: e.target.value }))}
                  placeholder="you@example.com"
                />
              </div>
              <div>
                <label className="profile-label">LinkedIn</label>
                <input
                  className="profile-input"
                  value={personal.linkedin}
                  onChange={(e) => setPersonal((p) => ({ ...p, linkedin: e.target.value }))}
                  placeholder="https://linkedin.com/in/..."
                />
              </div>
              <div>
                <label className="profile-label">GitHub</label>
                <input
                  className="profile-input"
                  value={personal.github}
                  onChange={(e) => setPersonal((p) => ({ ...p, github: e.target.value }))}
                  placeholder="https://github.com/..."
                />
              </div>
              <div>
                <label className="profile-label">Website</label>
                <input
                  className="profile-input"
                  value={personal.website}
                  onChange={(e) => setPersonal((p) => ({ ...p, website: e.target.value }))}
                  placeholder="https://yoursite.com"
                />
              </div>
            </div>
          </div>
        </div>

        <div className="profile-card">
          <div className="profile-card__inner">
            <div className="profile-card__head">
              <p className="profile-card__kicker">Skills</p>
              <h2 className="profile-card__title">Technical keywords</h2>
              <p className="profile-card__hint">Comma-separated list. Used for ATS alignment and job filters.</p>
            </div>
            <div>
              <label className="profile-label">
                Skills<span className="req">*</span>
              </label>
              <textarea
                required
                className="profile-textarea"
                value={skills}
                onChange={(e) => setSkills(e.target.value)}
                placeholder="Python, SQL, Pandas, NumPy, AWS, Tableau, Power BI, …"
                rows={4}
              />
            </div>
          </div>
        </div>

        <div className="profile-card">
          <div className="profile-card__inner">
            <div className="profile-card__head">
              <p className="profile-card__kicker">Education</p>
              <h2 className="profile-card__title">Degrees & programs</h2>
              <p className="profile-card__hint">One entry per school or program.</p>
            </div>

            {eduEmpty && <div className="profile-empty">No education added yet.</div>}

            {education.map((edu, i) => (
              <div key={i} className="profile-entry">
                <div className="profile-entry__bar">
                  <span className="profile-entry__badge">School {i + 1}</span>
                  {education.length > 1 && (
                    <button
                      type="button"
                      className="profile-entry__remove"
                      onClick={() => setEducation((ed) => ed.filter((_, j) => j !== i))}
                    >
                      Remove
                    </button>
                  )}
                </div>
                <div className="profile-grid-2">
                  <div>
                    <label className="profile-label">University</label>
                    <input
                      className="profile-input"
                      value={edu.university}
                      onChange={(e) => {
                        const v = e.target.value;
                        setEducation((ed) => ed.map((x, j) => (j === i ? { ...x, university: v } : x)));
                      }}
                    />
                  </div>
                  <div>
                    <label className="profile-label">Degree</label>
                    <input
                      className="profile-input"
                      value={edu.degree}
                      onChange={(e) => {
                        const v = e.target.value;
                        setEducation((ed) => ed.map((x, j) => (j === i ? { ...x, degree: v } : x)));
                      }}
                    />
                  </div>
                  <div>
                    <label className="profile-label">Major</label>
                    <input
                      className="profile-input"
                      value={edu.major}
                      onChange={(e) => {
                        const v = e.target.value;
                        setEducation((ed) => ed.map((x, j) => (j === i ? { ...x, major: v } : x)));
                      }}
                    />
                  </div>
                  <div>
                    <label className="profile-label">Graduation year</label>
                    <input
                      className="profile-input"
                      value={edu.graduation_year}
                      onChange={(e) => {
                        const v = e.target.value;
                        setEducation((ed) => ed.map((x, j) => (j === i ? { ...x, graduation_year: v } : x)));
                      }}
                      placeholder="2026"
                    />
                  </div>
                  <div style={{ gridColumn: "1 / -1" }}>
                    <label className="profile-label">GPA</label>
                    <input
                      className="profile-input"
                      value={edu.gpa}
                      onChange={(e) => {
                        const v = e.target.value;
                        setEducation((ed) => ed.map((x, j) => (j === i ? { ...x, gpa: v } : x)));
                      }}
                      placeholder="3.8/4.0"
                    />
                  </div>
                </div>
              </div>
            ))}

            <div className="profile-section-footer">
              <button
                type="button"
                className="profile-add-btn"
                onClick={() => setEducation((ed) => [...ed, emptyEdu()])}
              >
                + Add education
              </button>
            </div>
          </div>
        </div>

        <div className="profile-card">
          <div className="profile-card__inner">
            <div className="profile-card__head">
              <p className="profile-card__kicker">Experience</p>
              <h2 className="profile-card__title">Work history</h2>
              <p className="profile-card__hint">One role per block. Bullets: one line each.</p>
            </div>

            {expEmpty && <div className="profile-empty">No experience added yet.</div>}

            {experience.map((w, i) => (
              <div key={i} className="profile-entry">
                <div className="profile-entry__bar">
                  <span className="profile-entry__badge">Role {i + 1}</span>
                  {experience.length > 1 && (
                    <button
                      type="button"
                      className="profile-entry__remove"
                      onClick={() => setExperience((ex) => ex.filter((_, j) => j !== i))}
                    >
                      Remove
                    </button>
                  )}
                </div>
                <div className="profile-grid-2">
                  <div>
                    <label className="profile-label">Company</label>
                    <input
                      className="profile-input"
                      value={w.company}
                      onChange={(e) => {
                        const v = e.target.value;
                        setExperience((ex) => ex.map((x, j) => (j === i ? { ...x, company: v } : x)));
                      }}
                    />
                  </div>
                  <div>
                    <label className="profile-label">Role</label>
                    <input
                      className="profile-input"
                      value={w.role}
                      onChange={(e) => {
                        const v = e.target.value;
                        setExperience((ex) => ex.map((x, j) => (j === i ? { ...x, role: v } : x)));
                      }}
                    />
                  </div>
                  <div style={{ gridColumn: "1 / -1" }}>
                    <label className="profile-label">Duration</label>
                    <input
                      className="profile-input"
                      value={w.duration}
                      onChange={(e) => {
                        const v = e.target.value;
                        setExperience((ex) => ex.map((x, j) => (j === i ? { ...x, duration: v } : x)));
                      }}
                      placeholder="Jan 2024 – Present"
                    />
                  </div>
                  <div style={{ gridColumn: "1 / -1" }}>
                    <label className="profile-label">Bullets (one per line)</label>
                    <textarea
                      className="profile-textarea"
                      value={w.bulletsText}
                      onChange={(e) => {
                        const v = e.target.value;
                        setExperience((ex) => ex.map((x, j) => (j === i ? { ...x, bulletsText: v } : x)));
                      }}
                      rows={5}
                      placeholder="Led migration that cut latency by 40%…"
                    />
                  </div>
                </div>
              </div>
            ))}

            <div className="profile-section-footer">
              <button
                type="button"
                className="profile-add-btn"
                onClick={() => setExperience((ex) => [...ex, emptyExp()])}
              >
                + Add experience
              </button>
            </div>
          </div>
        </div>

        <div className="profile-card">
          <div className="profile-card__inner">
            <div className="profile-card__head">
              <p className="profile-card__kicker">Projects</p>
              <h2 className="profile-card__title">Selected work</h2>
              <p className="profile-card__hint">Shipped work, stack, and measurable outcomes.</p>
            </div>

            {projEmpty && <div className="profile-empty">No projects added yet.</div>}

            {projects.map((p, i) => (
              <div key={i} className="profile-entry">
                <div className="profile-entry__bar">
                  <span className="profile-entry__badge">Project {i + 1}</span>
                  {projects.length > 1 && (
                    <button
                      type="button"
                      className="profile-entry__remove"
                      onClick={() => setProjects((pr) => pr.filter((_, j) => j !== i))}
                    >
                      Remove
                    </button>
                  )}
                </div>
                <div>
                  <label className="profile-label">Name</label>
                  <input
                    className="profile-input"
                    value={p.name}
                    onChange={(e) => {
                      const v = e.target.value;
                      setProjects((pr) => pr.map((x, j) => (j === i ? { ...x, name: v } : x)));
                    }}
                  />
                </div>
                <div style={{ marginTop: 14 }}>
                  <label className="profile-label">Description</label>
                  <textarea
                    className="profile-textarea"
                    value={p.description}
                    onChange={(e) => {
                      const v = e.target.value;
                      setProjects((pr) => pr.map((x, j) => (j === i ? { ...x, description: v } : x)));
                    }}
                    rows={3}
                  />
                </div>
                <div style={{ marginTop: 14 }}>
                  <label className="profile-label">Tech stack (comma-separated)</label>
                  <input
                    className="profile-input"
                    value={p.techStack}
                    onChange={(e) => {
                      const v = e.target.value;
                      setProjects((pr) => pr.map((x, j) => (j === i ? { ...x, techStack: v } : x)));
                    }}
                  />
                </div>
                <div className="profile-grid-2" style={{ marginTop: 14 }}>
                  <div>
                    <label className="profile-label">GitHub URL</label>
                    <input
                      className="profile-input"
                      value={p.github_url}
                      onChange={(e) => {
                        const v = e.target.value;
                        setProjects((pr) => pr.map((x, j) => (j === i ? { ...x, github_url: v } : x)));
                      }}
                    />
                  </div>
                  <div>
                    <label className="profile-label">Impact</label>
                    <input
                      className="profile-input"
                      value={p.impact}
                      onChange={(e) => {
                        const v = e.target.value;
                        setProjects((pr) => pr.map((x, j) => (j === i ? { ...x, impact: v } : x)));
                      }}
                    />
                  </div>
                </div>
              </div>
            ))}

            <div className="profile-section-footer">
              <button
                type="button"
                className="profile-add-btn"
                onClick={() => setProjects((pr) => [...pr, emptyProj()])}
              >
                + Add project
              </button>
            </div>
          </div>
        </div>

        {save.isError && (
          <div className="profile-alert profile-alert--error" style={{ marginBottom: 16 }}>
            {save.error?.message || "Save failed"}
          </div>
        )}

        {save.isSuccess && (
          <div className="profile-alert profile-alert--ok" style={{ marginBottom: 16 }}>
            Profile saved.
          </div>
        )}

        <div className="profile-save-bar">
          <button type="submit" className="profile-save-btn" disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save profile"}
          </button>
        </div>
      </form>
    </div>
  );
}
