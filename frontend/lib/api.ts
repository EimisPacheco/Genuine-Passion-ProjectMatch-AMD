// Thin API client. All calls are same-origin /api/* (proxied to FastAPI by
// next.config rewrites), so SSE and file downloads work without CORS in dev.

export type Candidate = {
  candidate_id: string;
  name: string;
  headline: string;
  location?: string;
  city?: string;
  state?: string;
  country?: string;
  email?: string;
  linkedin_url?: string;
  contactable?: boolean;
  rank: number;
  selected: boolean;
  overall_score: number;
  project_similarity: number;
  genuine_passion: number;
  domain_similarity: number;
  technology_similarity: number;
  evidence_quality: number;
  confidence: number;
  innovation: number;
  builder_consistency: number;
  voluntary_effort: number;
  code_score: number;
  design_score: number;
  recommendation: string;
  evidence_ids: string[];
  narrative: {
    headline?: string;
    explanation?: string;
    passion_signals?: string;
    supporting_projects?: { title: string; url: string; id: string }[];
  };
};

export type Evidence = {
  id: string;
  source: string;
  title: string;
  url: string;
  description: string;
  technologies: string[];
  domain_tags: string[];
  evidence_date: string;
  confidence: number;
};

export type VisualAnalysis = {
  candidate_id: string;
  image_title: string;
  source_url: string;
  thumb_url: string;
  caption: string;
  signals: string[];
  polish: number;
  domain: string;
  provider: string;
  model: string;
};

// Two audiences read the same recommendation video: technical hiring managers, and HR.
export type CaptionStyle = "tech" | "non_tech";

/** One scene of the video, with its place on the timeline. */
export type VideoScene = {
  index: number;
  title: string;
  label: string;
  narration: string;
  start: number;
  end: number;
};

/** A timed caption cue — start/end let the UI follow the playhead. */
export type CaptionCue = { start: number; end: number; text: string };

// For SSE we connect EventSource straight to the backend: the Next.js dev proxy
// buffers streaming responses, which makes the live progress bar look frozen.
// Normal fetches stay relative (proxied). CORS on the backend is open.
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

async function j<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

export const api = {
  defaults: () => fetch("/api/demo/defaults").then(j<any>),
  config: () => fetch("/api/config").then(j<{ google_maps_api_key: string }>),
  health: () => fetch("/api/health").then(j<any>),
  raceInfo: () => fetch("/api/race/info").then(j<any>),
  createAnalysis: (body: any) =>
    fetch("/api/analyses", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(j<{ analysis_id: string }>),
  getAnalysis: (id: string) => fetch(`/api/analyses/${id}`).then(j<any>),
  candidates: (id: string) =>
    fetch(`/api/analyses/${id}/candidates`).then(j<{ top_n: number; candidates: Candidate[] }>),
  evidence: (id: string, cid: string) =>
    fetch(`/api/analyses/${id}/candidates/${cid}/evidence`).then(j<{ evidence: Evidence[] }>),
  visual: (id: string, cid: string) =>
    fetch(`/api/analyses/${id}/candidates/${cid}/visual`).then(j<{ visual: VisualAnalysis[] }>),
  traces: (id: string) => fetch(`/api/analyses/${id}/traces`).then(j<any>),
  video: (id: string) => fetch(`/api/analyses/${id}/video`).then(j<any>),
};

export const pct = (n: number) => `${Math.round((n || 0) * 100)}%`;
