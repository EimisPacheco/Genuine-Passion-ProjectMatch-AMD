"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, API_BASE, Candidate, Evidence, VisualAnalysis, pct } from "@/lib/api";
import { ScoreBar } from "@/components/openui/ScoreBar";
import { CandidateCard } from "@/components/openui/CandidateCard";
import { EvidenceCard } from "@/components/openui/EvidenceCard";
import { AgentProgressList } from "@/components/openui/AgentProgressList";
import { RacePanel } from "@/components/RacePanel";

const TABS = ["Progress", "⚡ Speed", "Rankings", "Candidate", "Evidence", "Video", "Traces"] as const;
type Tab = (typeof TABS)[number];

export default function AnalysisPage({ params }: { params: { id: string } }) {
  const { id } = params;
  const [tab, setTab] = useState<Tab>("Progress");
  const [events, setEvents] = useState<any[]>([]);
  const [status, setStatus] = useState("running");
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [selectedCid, setSelectedCid] = useState<string>("");
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
      {tab === "⚡ Speed" && (
        <RacePanel infoPath={`/api/analyses/${id}/race/info`} streamPath={`/api/analyses/${id}/race/stream`} />
      )}
      {tab === "Rankings" && <Rankings candidates={candidates} onPick={(c) => { setSelectedCid(c); setTab("Candidate"); }} />}
      {tab === "Candidate" && <CandidateDetail id={id} candidates={candidates} cid={selectedCid} setCid={setSelectedCid} onEvidence={() => setTab("Evidence")} />}
      {tab === "Evidence" && <EvidenceExplorer id={id} candidates={candidates} cid={selectedCid} setCid={setSelectedCid} />}
      {tab === "Video" && <VideoViewer id={id} status={status} />}
      {tab === "Traces" && <Traces id={id} events={events} />}
    </div>
  );
}

function Progress({ events, pctDone, elapsedMs, status }: { events: any[]; pctDone: number; elapsedMs: number; status: string }) {
  // OpenUI-generated component
  return <AgentProgressList events={events} pctDone={pctDone} elapsedMs={elapsedMs} running={status === "running"} />;
}

function Rankings({ candidates, onPick }: { candidates: Candidate[]; onPick: (cid: string) => void }) {
  if (!candidates.length) return <Empty msg="Rankings appear when the analysis finishes." />;
  // Show ONLY the Top-N the user asked for (backend flags them `selected`), not
  // every candidate submitted. Fall back to all if nothing is flagged.
  const selected = candidates.filter((c) => c.selected);
  const shown = selected.length ? selected : candidates;
  const hidden = candidates.length - shown.length;
  return (
    <div className="space-y-3">
      {shown.map((c) => (
        // OpenUI-generated component
        <CandidateCard key={c.candidate_id} c={c} onPick={onPick} />
      ))}
      {hidden > 0 && (
        <p className="pt-1 text-center text-xs text-slate-500">
          Showing the top {shown.length} of {candidates.length} candidates investigated.
        </p>
      )}
    </div>
  );
}

function CandidatePicker({ candidates, cid, setCid }: { candidates: Candidate[]; cid: string; setCid: (c: string) => void }) {
  return (
    <div className="mb-4 flex flex-wrap gap-2">
      {candidates.map((c) => (
        <button key={c.candidate_id} onClick={() => setCid(c.candidate_id)}
          className={c.candidate_id === cid ? "btn text-sm" : "btn-ghost text-sm"}>
          #{c.rank} {c.name}
        </button>
      ))}
    </div>
  );
}

function CandidateDetail({ id, candidates, cid, setCid, onEvidence }: any) {
  if (!candidates.length) return <Empty msg="Candidate details appear when the analysis finishes." />;
  const c: Candidate = candidates.find((x: Candidate) => x.candidate_id === cid) || candidates[0];
  return (
    <div>
      <CandidatePicker candidates={candidates} cid={c.candidate_id} setCid={setCid} />
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

function EvidenceExplorer({ id, candidates, cid, setCid }: any) {
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  useEffect(() => {
    if (cid) api.evidence(id, cid).then((r) => setEvidence(r.evidence));
  }, [id, cid]);
  if (!candidates.length) return <Empty msg="Evidence appears when the analysis finishes." />;
  return (
    <div>
      <CandidatePicker candidates={candidates} cid={cid} setCid={setCid} />
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
      </div>
      <div className="card">
        <div className="mb-2 text-xs font-semibold uppercase text-brand">Narration script</div>
        <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap text-sm text-slate-300">{meta.narration_script}</pre>
      </div>
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
