import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

/** Normalize FastAPI / Starlette error bodies into a string. */
export function parseApiError(payload, fallback) {
  if (payload == null) return fallback;
  const d = payload.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) {
    return d
      .map((e) => (typeof e === "object" && e?.msg ? e.msg : JSON.stringify(e)))
      .join("; ");
  }
  if (typeof d === "object" && d !== null) return JSON.stringify(d);
  return fallback;
}

export async function api(path, opts) {
  const r = await fetch(path, opts);
  const text = await r.text();
  let body = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = { detail: text.slice(0, 200) };
    }
  }
  if (!r.ok) {
    const msg = parseApiError(body, r.statusText || `HTTP ${r.status}`);
    throw new Error(msg);
  }
  return body;
}

export function useStats() {
  return useQuery({
    queryKey: ["stats"],
    queryFn: () => api("/api/jobs/stats"),
  });
}

export function useAnalytics(days = 30) {
  return useQuery({
    queryKey: ["analytics", days],
    queryFn: () => api(`/api/jobs/analytics?days=${days}`),
    staleTime: 60_000,
  });
}

export function useJobs({ verdict, search, minScore, isRemote, sinceDays, limit = 50, offset = 0 } = {}) {
  const params = new URLSearchParams();
  if (verdict) params.set("verdict", verdict);
  if (search) params.set("search", search);
  if (minScore) params.set("min_score", String(minScore));
  if (isRemote !== undefined && isRemote !== null) params.set("is_remote", String(isRemote));
  if (sinceDays) params.set("since_days", String(sinceDays));
  params.set("limit", String(limit));
  params.set("offset", String(offset));

  return useQuery({
    queryKey: ["jobs", verdict, search, minScore, isRemote, sinceDays, limit, offset],
    queryFn: () => api(`/api/jobs?${params}`),
  });
}

export function useJob(id) {
  return useQuery({
    queryKey: ["job", id],
    queryFn: () => api(`/api/jobs/${id}`),
    enabled: !!id,
  });
}

export function useTriggerScrape() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (dryRun = false) =>
      api("/api/jobs/scrape", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dry_run: dryRun }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agentRuns"] });
      setTimeout(() => {
        qc.invalidateQueries({ queryKey: ["stats"] });
        qc.invalidateQueries({ queryKey: ["jobs"] });
      }, 5000);
    },
  });
}

export function useOverrideVerdict() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ jobId, verdict, reason }) =>
      api(`/api/jobs/${jobId}/verdict`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ verdict, reason }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["stats"] });
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
}

export function useAgentRuns(limit = 25) {
  return useQuery({
    queryKey: ["agentRuns", limit],
    queryFn: () => api(`/api/agent-runs?limit=${limit}`),
    refetchInterval: 15_000,
  });
}

export function useTailorResume() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (jobId) =>
      api("/api/resumes/tailor", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: jobId }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["resumes"] });
    },
  });
}

// ── Applications ──────────────────────────────────────────────────────

export function useApplications(status, { limit = 100 } = {}) {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  params.set("limit", String(Math.min(limit, 200)));

  return useQuery({
    queryKey: ["applications", status, limit],
    queryFn: () => api(`/api/applications?${params}`),
  });
}

/** All application job_ids (paginated GET) for Job Board "Added ✓" state. */
export function useApplicationJobIds() {
  return useQuery({
    queryKey: ["applications", "jobIds"],
    queryFn: async () => {
      const ids = new Set();
      let offset = 0;
      const limit = 200;
      for (;;) {
        const data = await api(`/api/applications?limit=${limit}&offset=${offset}`);
        const apps = data.applications || [];
        for (const a of apps) {
          if (a.job_id) ids.add(a.job_id);
        }
        if (apps.length < limit) break;
        offset += limit;
      }
      return ids;
    },
    staleTime: 30_000,
  });
}

export function useCreateApplication() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (jobId) =>
      api("/api/applications", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: jobId }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["applications"] });
      qc.invalidateQueries({ queryKey: ["applications", "jobIds"] });
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
}

export function useUpdateApplicationStatus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ applicationId, status, notes }) =>
      api(`/api/applications/${applicationId}/status`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status, notes }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["applications"] });
    },
  });
}

export function useAddManualJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data) =>
      api("/api/jobs/manual", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
    },
  });
}

export function useResumes(jobId) {
  const params = new URLSearchParams();
  if (jobId) params.set("job_id", jobId);
  return useQuery({
    queryKey: ["resumes", jobId],
    queryFn: () => api(`/api/resumes?${params}`),
    enabled: jobId !== undefined,
  });
}

// ── Profile (candidate_profile.json) ─────────────────────────────────

export function useProfile() {
  return useQuery({
    queryKey: ["profile"],
    queryFn: () => api("/api/profile"),
    staleTime: 30_000,
  });
}

export function useSaveProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload) =>
      api("/api/profile", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["profile"] });
    },
  });
}
