"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, API_BASE, Candidate, CaptionStyle, Evidence, VideoCaption, VisualAnalysis, pct } from "@/lib/api";
import { ScoreBar } from "@/components/openui/ScoreBar";
import { CandidateCard } from "@/components/openui/CandidateCard";
import { EvidenceCard } from "@/components/openui/EvidenceCard";
import { AgentProgressList } from "@/components/openui/AgentProgressList";

// Map lives inside Rankings; captions live under the Video. Speed race is hidden.
const TABS = ["Progress", "Rankings", "Candidate", "Evidence", "Video", "Traces"] as const;
type Tab = (typeof TABS)[number];

export default function AnalysisPage({ params }: { params: { id: string } }) {
  const { id } = params;
  const [tab, setTab] = useState<Tab>("Progress");
  const [events, setEvents] = useState<any[]>([]);
  const [status, setStatus] = useState("running");
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [selectedCid, setSelectedCid] = useState<string>("");
  const [topN, setTopN] = useState(3);
  const [elapsedMs, setElapsedMs] = useState(0);

  const loadedRef = useRef(false);
  const startedRef = useRef<number>(Date.now());

  // Elapsed-time clock: ticks while the analysis runs, freezes on done/error.
  useEffect(() => {
    if (status !== "running") return;
    const t = setInterval(() => setElapsedMs(Date.now() - startedRef.current), 250);
    return () => clearInterval(t);
  }, [status]);

  // SSE progress stream (direct to backend; the dev proxy can buffer SSE)
  useEffect(() => {
    const es = new EventSource(`${API_BASE}/api/analyses/${id}/stream`);
    es.onmessage = (e) => {
      const ev = JSON.parse(e.data);
      setEvents((prev) => [...prev, ev]);
      if (ev.status === "done" || ev.status === "error") {
        setStatus(ev.status);
        es.close();
        if (ev.status === "done") loadResults();
      }
    };
    es.onerror = () => es.close();
    return () => es.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // Polling fallback: guarantees results load even if the SSE stream drops or
  // the page is opened after the analysis already finished.
  useEffect(() => {
    let stop = false;
    const poll = async () => {
      try {
        const s = await api.getAnalysis(id);
        if (s.status === "done") return loadResults();
        if (s.status === "error") return setStatus("error");
      } catch {}
      if (!stop) setTimeout(poll, 3000);
    };
    poll();
    return () => {
      stop = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function loadResults() {
    if (loadedRef.current) return;
    loadedRef.current = true;
    setStatus("done");
    const r = await api.candidates(id);
    setCandidates(r.candidates);
    setTopN(r.top_n || 3);
    setSelectedCid(r.candidates.find((c) => c.selected)?.candidate_id || r.candidates[0]?.candidate_id || "");
    setTab("Rankings");
  }

  const pctDone = events.length ? events[events.length - 1].percent : 0;

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <Link href="/" className="text-sm text-slate-500 hover:text-brand">← New analysis</Link>
        <div className="text-xs text-slate-500">analysis {id}</div>
      </div>

      <div className="mb-5 flex flex-wrap gap-2">
        {TABS.map((t) => (
          <div key={t} className={`tab ${tab === t ? "tab-active" : ""}`} onClick={() => setTab(t)}>
            {t}
          </div>
        ))}
        <div className="ml-auto flex items-center gap-2 text-xs">
          <span className={`h-2 w-2 rounded-full ${status === "done" ? "bg-emerald-400" : status === "error" ? "bg-red-400" : "bg-amber-400 animate-pulse"}`} />
          {status}
        </div>
      </div>

      {tab === "Progress" && <Progress events={events} pctDone={pctDone} elapsedMs={elapsedMs} status={status} />}
      {tab === "Rankings" && <Rankings candidates={candidates} topN={topN} onPick={(c) => { setSelectedCid(c); setTab("Candidate"); }} />}
      {tab === "Candidate" && <CandidateDetail id={id} candidates={candidates} topN={topN} cid={selectedCid} setCid={setSelectedCid} onEvidence={() => setTab("Evidence")} />}
      {tab === "Evidence" && <EvidenceExplorer id={id} candidates={candidates} topN={topN} cid={selectedCid} setCid={setSelectedCid} />}
      {tab === "Video" && <VideoViewer id={id} status={status} />}
      {tab === "Traces" && <Traces id={id} events={events} />}
    </div>
  );
}

function Progress({ events, pctDone, elapsedMs, status }: { events: any[]; pctDone: number; elapsedMs: number; status: string }) {
  // OpenUI-generated component
  return <AgentProgressList events={events} pctDone={pctDone} elapsedMs={elapsedMs} running={status === "running"} />;
}

/**
 * The ONLY candidates the app ever shows: the Top-N the user asked for.
 * Prefer the selected (contactable) set; otherwise the Top-N by rank. Never the
 * whole discovered pool — a run that finds 60 people still shows only Top-N.
 */
function visibleCandidates(candidates: Candidate[], topN: number): Candidate[] {
  const inTopN = candidates.filter((c) => c.selected || c.rank <= topN);
  const shown = inTopN.length ? inTopN : candidates.slice().sort((a, b) => a.rank - b.rank).slice(0, topN);
  return shown.slice().sort((a, b) => a.rank - b.rank);
}

function Rankings({ candidates, topN, onPick }: { candidates: Candidate[]; topN: number; onPick: (cid: string) => void }) {
  if (!candidates.length) return <Empty msg="Rankings appear when the analysis finishes." />;
  const shown = visibleCandidates(candidates, topN);
  const hidden = candidates.length - shown.length;
  const missingLinkedin = shown.filter((c) => !c.contactable).length;
  return (
    <div className="space-y-3">
      {missingLinkedin > 0 && (
        <p className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-xs text-amber-200/90">
          {missingLinkedin} top-ranked candidate{missingLinkedin > 1 ? "s are" : " is"} not marked selected —
          no LinkedIn on file, so they can’t be contacted.
        </p>
      )}
      {shown.map((c) => (
        // OpenUI-generated component
        <CandidateCard key={c.candidate_id} c={c} onPick={onPick} />
      ))}
      {hidden > 0 && (
        <p className="pt-1 text-center text-xs text-slate-500">
          Showing the top {shown.length} of {candidates.length} candidates investigated.
        </p>
      )}
      {/* Map lives here now, under the rankings — same Top-N. */}
      <CandidateMap candidates={shown} onPick={onPick} />
    </div>
  );
}


// Load the Google Maps JS API once (shared across mounts).
let mapsPromise: Promise<any> | null = null;
function loadGoogleMaps(key: string): Promise<any> {
  if (typeof window === "undefined") return Promise.reject(new Error("no window"));
  const w = window as any;
  if (w.google?.maps) return Promise.resolve(w.google);
  if (mapsPromise) return mapsPromise;
  mapsPromise = new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}`;
    s.async = true;
    s.onload = () => resolve((window as any).google);
    s.onerror = () => { mapsPromise = null; reject(new Error("maps load failed")); };
    document.head.appendChild(s);
  });
  return mapsPromise;
}

function CandidateMap({ candidates, onPick }: { candidates: Candidate[]; onPick: (cid: string) => void }) {
  const [apiKey, setApiKey] = useState<string | null>(null); // null=loading, ""=none
  const [mapsFailed, setMapsFailed] = useState(false);
  useEffect(() => {
    api.config().then((c) => setApiKey(c.google_maps_api_key || "")).catch(() => setApiKey(""));
  }, []);

  if (!candidates.length) return <Empty msg="The map appears when the analysis finishes." />;
  const located = candidates.filter((c) => (c.location || "").trim());
  const missing = candidates.length - located.length;
  const useJs = !!apiKey && !mapsFailed;

  return (
    <div className="space-y-4">
      <div className="card">
        <h3 className="font-semibold text-slate-100">Where these builders are</h3>
        <p className="mt-1 text-sm text-slate-400">
          Each pin is the candidate’s <b>self-reported location</b> from their public profile
          (city / region — public profiles don’t expose street addresses). Geocoded and rendered by Google Maps.
        </p>
        {missing > 0 && (
          <p className="mt-2 text-xs text-slate-500">
            {missing} candidate{missing > 1 ? "s" : ""} did not list a public location.
          </p>
        )}
      </div>

      {!located.length ? (
        <Empty msg="None of these candidates listed a public location." />
      ) : useJs ? (
        <div className="card p-0 overflow-hidden">
          <GoogleCombinedMap candidates={located} apiKey={apiKey!} onFail={() => setMapsFailed(true)} />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {located.map((c) => (
            <div key={c.candidate_id} className="card overflow-hidden p-0">
              <div className="flex items-center justify-between gap-2 p-4">
                <div className="min-w-0">
                  <button onClick={() => onPick(c.candidate_id)} className="truncate text-left font-semibold text-slate-100 hover:text-brand">
                    #{c.rank} {c.name}
                  </button>
                  <div className="mt-0.5 flex items-center gap-1.5 text-sm text-slate-400">
                    <span>📍</span><span className="truncate">{c.location}</span>
                  </div>
                </div>
                {c.selected && <span className="chip shrink-0">Top pick</span>}
              </div>
              <iframe
                title={`Map of ${c.location}`}
                className="h-56 w-full border-0"
                loading="lazy"
                referrerPolicy="no-referrer-when-downgrade"
                src={`https://www.google.com/maps?q=${encodeURIComponent(c.location || "")}&z=5&output=embed`}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function GoogleCombinedMap(
  { candidates, apiKey, onFail }: { candidates: Candidate[]; apiKey: string; onFail: () => void },
) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let cancelled = false;
    loadGoogleMaps(apiKey)
      .then((google) => {
        if (cancelled || !ref.current) return;
        const map = new google.maps.Map(ref.current, {
          center: { lat: 20, lng: 0 }, zoom: 2,
          mapTypeControl: false, streetViewControl: false, fullscreenControl: false,
        });
        const geocoder = new google.maps.Geocoder();
        const bounds = new google.maps.LatLngBounds();
        const info = new google.maps.InfoWindow();
        let placed = 0;
        candidates.forEach((c) => {
          geocoder.geocode({ address: c.location }, (results: any, status: string) => {
            if (cancelled || status !== "OK" || !results?.[0]) return;
            const pos = results[0].geometry.location;
            const marker = new google.maps.Marker({
              position: pos, map, title: `#${c.rank} ${c.name} — ${c.location}`,
            });
            marker.addListener("click", () => {
              info.setContent(
                `<div style="color:#0f172a;font:13px system-ui"><b>#${c.rank} ${c.name}</b><br/>${c.location || ""}</div>`,
              );
              info.open(map, marker);
            });
            bounds.extend(pos);
            placed++;
            if (placed === 1) { map.setCenter(pos); map.setZoom(4); }
            else map.fitBounds(bounds);
          });
        });
      })
      .catch(() => { if (!cancelled) onFail(); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiKey, candidates]);
  return <div ref={ref} className="h-[28rem] w-full" />;
}

function CandidatePicker({ candidates, cid, setCid, topN }: { candidates: Candidate[]; cid: string; setCid: (c: string) => void; topN: number }) {
  // Only the Top-N — never every candidate investigated.
  const shown = visibleCandidates(candidates, topN);
  return (
    <div className="mb-4 flex flex-wrap gap-2">
      {shown.map((c) => (
        <button key={c.candidate_id} onClick={() => setCid(c.candidate_id)}
          className={c.candidate_id === cid ? "btn text-sm" : "btn-ghost text-sm"}>
          #{c.rank} {c.name}
        </button>
      ))}
    </div>
  );
}

function CandidateDetail({ id, candidates, topN, cid, setCid, onEvidence }: any) {
  if (!candidates.length) return <Empty msg="Candidate details appear when the analysis finishes." />;
  const c: Candidate = candidates.find((x: Candidate) => x.candidate_id === cid) || candidates[0];
  return (
    <div>
      <CandidatePicker candidates={candidates} topN={topN} cid={c.candidate_id} setCid={setCid} />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="card lg:col-span-2">
          <h3 className="text-lg font-semibold text-slate-100">#{c.rank} {c.name}</h3>
          <p className="mb-4 text-sm text-slate-400">{c.narrative?.headline}</p>
          <p className="text-slate-200">{c.narrative?.explanation}</p>
          {c.narrative?.passion_signals && (
            <div className="mt-4 rounded-lg border border-slate-800 bg-slate-900/40 p-3 text-sm text-slate-300">
              <div className="mb-1 text-xs font-semibold uppercase text-brand">Passion signals</div>
              {c.narrative.passion_signals}
            </div>
          )}
          <VisualStrip id={id} cid={c.candidate_id} />
          <div className="mt-4">
            <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Most relevant projects</div>
            <ul className="space-y-1">
              {(c.narrative?.supporting_projects || []).map((p) => (
                <li key={p.id}>
                  <a href={p.url} target="_blank" className="text-sm text-brand hover:underline">{p.title}</a>
                </li>
              ))}
            </ul>
          </div>
          <button className="btn-ghost mt-4 text-sm" onClick={onEvidence}>View all evidence →</button>
        </div>
        <div className="card space-y-3">
          <ScoreBar label="Overall" value={c.overall_score} />
          <ScoreBar label="Code" value={c.code_score} />
          <ScoreBar label="Design" value={c.design_score} />
          <ScoreBar label="Project similarity" value={c.project_similarity} />
          <ScoreBar label="Genuine passion" value={c.genuine_passion} />
          <ScoreBar label="Domain similarity" value={c.domain_similarity} />
          <ScoreBar label="Technology" value={c.technology_similarity} />
          <ScoreBar label="Builder consistency" value={c.builder_consistency} />
          <ScoreBar label="Voluntary effort" value={c.voluntary_effort} />
          <ScoreBar label="Innovation" value={c.innovation} />
          <ScoreBar label="Confidence" value={c.confidence} />
        </div>
      </div>
    </div>
  );
}

function VisualStrip({ id, cid }: { id: string; cid: string }) {
  const [items, setItems] = useState<VisualAnalysis[]>([]);
  useEffect(() => {
    if (cid) api.visual(id, cid).then((r) => setItems(r.visual || [])).catch(() => setItems([]));
  }, [id, cid]);
  if (!items.length) return null;
  const live = items.some((v) => v.provider !== "heuristic");
  return (
    <div className="mt-4">
      <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase text-brand">
        Visual portfolio
        <span className="chip normal-case">
          {live ? `Gemma 4 vision · ${items[0].model}` : "heuristic (configure Gemma on AMD for vision)"}
        </span>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {items.map((v, i) => (
          <a
            key={i}
            href={v.source_url}
            target="_blank"
            className="rounded-lg border border-slate-800 bg-slate-900/40 p-2 transition hover:border-brand"
          >
            {v.thumb_url && (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={v.thumb_url.startsWith("/") ? `${API_BASE}${v.thumb_url}` : v.thumb_url}
                alt={v.image_title}
                className="mb-2 h-32 w-full rounded object-cover"
              />
            )}
            <div className="text-xs font-medium text-slate-200">{v.image_title}</div>
            <p className="mt-1 text-xs text-slate-400">{v.caption}</p>
            <div className="mt-1 flex flex-wrap gap-1">
              {(v.signals || []).map((s, k) => (
                <span key={k} className="chip text-[10px]">{s}</span>
              ))}
            </div>
          </a>
        ))}
      </div>
    </div>
  );
}

function EvidenceExplorer({ id, candidates, topN, cid, setCid }: any) {
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  useEffect(() => {
    if (cid) api.evidence(id, cid).then((r) => setEvidence(r.evidence));
  }, [id, cid]);
  if (!candidates.length) return <Empty msg="Evidence appears when the analysis finishes." />;
  return (
    <div>
      <CandidatePicker candidates={candidates} topN={topN} cid={cid} setCid={setCid} />
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {/* OpenUI-generated component */}
        {evidence.map((e) => (
          <EvidenceCard key={e.id} e={e} />
        ))}
        {!evidence.length && <Empty msg="No evidence for this candidate." />}
      </div>
    </div>
  );
}

function VideoViewer({ id, status }: { id: string; status: string }) {
  const [meta, setMeta] = useState<any>(null);
  useEffect(() => {
    if (status === "done") api.video(id).then(setMeta).catch(() => {});
  }, [id, status]);
  if (status !== "done") return <Empty msg="The executive video is generated at the end of the analysis." />;
  if (!meta) return <Empty msg="Loading video…" />;
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <div className="card lg:col-span-2">
        <h3 className="mb-3 font-semibold">{meta.title}</h3>
        {meta.has_mp4 ? (
          <video controls className="w-full rounded-lg" src={meta.mp4_url}>
            <track kind="subtitles" src={meta.srt_url} default />
          </video>
        ) : (
          <p className="text-slate-400">MP4 not rendered (ffmpeg unavailable) — narration script below.</p>
        )}
        <div className="mt-3 flex gap-2">
          <a className="btn-ghost text-sm" href={meta.srt_url} target="_blank">Download .srt</a>
        </div>
        {/* Caption this video with Gemma, in a style you choose — on demand. */}
        <VideoCaptioner id={id} />
      </div>
      <div className="card">
        <div className="mb-2 text-xs font-semibold uppercase text-brand">Narration script</div>
        <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap text-sm text-slate-300">{meta.narration_script}</pre>
      </div>
    </div>
  );
}

const STYLE_OPTIONS: { key: CaptionStyle; label: string; hint: string }[] = [
  { key: "tech", label: "Tech hiring manager", hint: "Engineering substance — stack, architecture, what the work proves." },
  { key: "non_tech", label: "HR / recruiter", hint: "Plain language, no jargon — who they are and why they fit." },
];

function VideoCaptioner({ id }: { id: string }) {
  const [style, setStyle] = useState<CaptionStyle>("tech");
  const [result, setResult] = useState<VideoCaption | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function generate() {
    setLoading(true);
    setError("");
    setResult(null);
    try {
      setResult(await api.videoCaption(id, style));
    } catch (e: any) {
      setError(String(e?.message || e).slice(0, 160));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mt-5 border-t border-slate-800 pt-4">
      <div className="mb-1 text-xs font-semibold uppercase text-brand">Caption this video for…</div>
      <p className="mb-3 text-xs text-slate-500">
        {STYLE_OPTIONS.find((s) => s.key === style)?.hint}
      </p>
      <div className="mb-3 flex flex-wrap gap-2">
        {STYLE_OPTIONS.map((s) => (
          <button key={s.key} onClick={() => setStyle(s.key)}
            className={s.key === style ? "btn text-sm" : "btn-ghost text-sm"}>
            {s.label}
          </button>
        ))}
        <button className="btn text-sm" onClick={generate} disabled={loading}>
          {loading ? "Generating…" : "Generate caption →"}
        </button>
      </div>
      {loading && (
        <p className="text-sm text-slate-500">Gemma is watching the video…</p>
      )}
      {error && (
        <p className="rounded-lg border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-200">{error}</p>
      )}
      {result && (
        <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-3">
          <div className="mb-1 flex items-center justify-between gap-2">
            <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
              {STYLE_OPTIONS.find((s) => s.key === result.style)?.label}
            </span>
            <span className="chip text-[10px]">{result.provider} · {result.model}</span>
          </div>
          <p className="text-slate-200">{result.caption}</p>
        </div>
      )}
    </div>
  );
}

function Traces({ id, events }: { id: string; events: any[] }) {
  const [runs, setRuns] = useState<any[]>([]);
  const [lf, setLf] = useState<string | null>(null);
  useEffect(() => {
    api.traces(id).then((r) => { setRuns(r.agent_runs || []); setLf(r.langfuse_host); }).catch(() => {});
  }, [id, events.length]);
  const rows = runs.length ? runs : events.filter((e) => e.status === "ok").map((e) => ({ agent_name: e.agent, status: e.status, output_summary: e.detail, latency_ms: "" }));
  return (
    <div className="card">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="font-semibold">Agent Trace Viewer</h3>
        {lf && <span className="text-xs text-slate-500">Langfuse: {lf}</span>}
      </div>
      <table className="w-full text-sm">
        <thead><tr className="text-left text-xs uppercase text-slate-500">
          <th className="py-2">Agent</th><th>Status</th><th>Output</th><th className="text-right">Latency</th>
        </tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-slate-800">
              <td className="py-2 font-mono text-xs text-slate-300">{r.agent_name}</td>
              <td><span className={r.status === "ok" || r.status === "done" ? "text-emerald-400" : "text-amber-400"}>{r.status}</span></td>
              <td className="text-slate-400">{r.output_summary}</td>
              <td className="text-right text-slate-500">{r.latency_ms ? `${r.latency_ms}ms` : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Empty({ msg }: { msg: string }) {
  return <div className="card text-slate-500">{msg}</div>;
}
