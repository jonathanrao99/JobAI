"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

function apiAuthHeaders() {
  const t =
    typeof process !== "undefined" && process.env.NEXT_PUBLIC_JOBAI_API_TOKEN
      ? process.env.NEXT_PUBLIC_JOBAI_API_TOKEN.trim()
      : "";
  if (!t) return {};
  return { Authorization: `Bearer ${t}` };
}

/**
 * Resolve /api/... to the FastAPI origin in development so requests never go through
 * Next.js dev proxy (which times out on long routes like POST /applications/{id}/prepare).
 * NEXT_PUBLIC_API_URL wins when set (e.g. production override).
 * In the browser on localhost or a LAN IP, use the same hostname with port 8000.
 */
function apiUrl(path) {
  if (typeof path === "string" && path.startsWith("http")) return path;
  const normalized = path.startsWith("/") ? path : `/${path}`;

  const fromEnv =
    typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_URL
      ? String(process.env.NEXT_PUBLIC_API_URL).replace(/\/$/, "")
      : "";
  if (fromEnv) return `${fromEnv}${normalized}`;

  const isDev =
    typeof process !== "undefined" && process.env.NODE_ENV === "development";
  if (isDev) {
    if (typeof window !== "undefined") {
      const h = window.location.hostname;
      return `http://${h}:8000${normalized}`;
    }
    return `http://127.0.0.1:8000${normalized}`;
  }

  return normalized;
}

/** Same rules as internal apiUrl — use for <iframe src>, <a href>, etc. */
export function resolveApiUrl(path) {
  return apiUrl(path);
}

/** For PDF/binary routes: <iframe> cannot send Authorization; use this with a blob URL. */
export async function fetchAuthenticatedBlob(path) {
  const headers = { ...apiAuthHeaders() };
  const r = await fetch(apiUrl(path), { headers });
  if (!r.ok) {
    const text = await r.text();
    let msg = `HTTP ${r.status}`;
    try {
      const j = JSON.parse(text);
      if (j?.detail) msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {
      if (text) msg = text.slice(0, 200);
    }
    throw new Error(msg);
  }
  return r.blob();
}

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

export async function api(path, opts = {}) {
  const headers = {
    ...apiAuthHeaders(),
    ...(opts.headers && typeof opts.headers === "object" ? opts.headers : {}),
  };
  const r = await fetch(apiUrl(path), { ...opts, headers });
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

export function useStats(queryOptions = {}) {
  const { staleTime, refetchInterval, ...rest } = queryOptions;
  return useQuery({
    queryKey: ["stats"],
    queryFn: () => api("/api/jobs/stats"),
    staleTime: staleTime ?? 30_000,
    refetchInterval,
    ...rest,
  });
}

export function useAnalytics(days = 30) {
  return useQuery({
    queryKey: ["analytics", days],
    queryFn: () => api(`/api/jobs/analytics?days=${days}`),
    staleTime: 60_000,
  });
}

export function useJobs({
  verdict,
  search,
  minScore,
  isRemote,
  sinceDays,
  includeDescription = false,
  limit = 50,
  offset = 0,
} = {}) {
  const params = new URLSearchParams();
  if (verdict) params.set("verdict", verdict);
  if (search) params.set("search", search);
  if (minScore) params.set("min_score", String(minScore));
  if (isRemote !== undefined && isRemote !== null) params.set("is_remote", String(isRemote));
  if (sinceDays != null) params.set("since_days", String(sinceDays));
  if (includeDescription) params.set("include_description", "true");
  params.set("limit", String(limit));
  params.set("offset", String(offset));

  return useQuery({
    queryKey: ["jobs", verdict, search, minScore, isRemote, sinceDays, includeDescription, limit, offset],
    queryFn: () => api(`/api/jobs?${params}`),
    staleTime: 20_000,
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
        qc.invalidateQueries({ queryKey: ["admin", "opsSummary"] });
      }, 5000);
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

export function useAdminOpsSummary() {
  return useQuery({
    queryKey: ["admin", "opsSummary"],
    queryFn: () => api("/api/admin/ops-summary"),
    staleTime: 20_000,
    refetchInterval: 30_000,
  });
}

export function useApplications(status, { limit = 100 } = {}) {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  params.set("limit", String(Math.min(limit, 200)));

  return useQuery({
    queryKey: ["applications", status, limit],
    queryFn: () => api(`/api/applications?${params}`),
  });
}

export function useApplicationJobIds() {
  return useQuery({
    queryKey: ["applications", "jobIds"],
    queryFn: async () => {
      const data = await api("/api/applications/job-ids");
      return new Set(data.job_ids || []);
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

export function usePrepareApplication() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (applicationId) =>
      api(`/api/applications/${encodeURIComponent(applicationId)}/prepare`, {
        method: "POST",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["applications"] });
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
