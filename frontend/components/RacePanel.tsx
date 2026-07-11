"use client";

// Reusable divided-screen speed race: Gemma on AMD (left) vs a GPU baseline (right),
// same Gemma task, started at one instant. Used by the /race page AND embedded in
// the main analysis flow (scoped to that analysis's candidates) via different
// info/stream paths. SSE goes straight to API_BASE so the dev proxy can't buffer.

import { useEffect, useRef, useState } from "react";
import { API_BASE } from "../lib/api";

type SideKey = "primary" | "baseline";
type Card = { candidate: string; verdict: string; tps: number };
type SideState = {
  label: string;
  model: string;
  available: boolean;
  status: "idle" | "running" | "done" | "error";
  tokens: number;
  tps: number;
  elapsedMs: number;
  totalMs: number | null;
  cards: Card[];
  note?: string;
};

const FRESH = (label: string, model: string, available: boolean): SideState => ({
  label,
  model,
  available,
  status: "idle",
  tokens: 0,
  tps: 0,
  elapsedMs: 0,
  totalMs: null,
  cards: [],
});

function metaById(info: any): Record<string, any> {
  const meta: Record<string, any> = {};
  (info?.sides || []).forEach((s: any) => (meta[s.id] = s));
  return meta;
}

export function RacePanel({ infoPath, streamPath }: { infoPath: string; streamPath: string }) {
  const [info, setInfo] = useState<any>(null);
  const [running, setRunning] = useState(false);
  const [sides, setSides] = useState<Record<SideKey, SideState>>({
    primary: FRESH("Gemma on AMD", "gemma-4-31b", false),
    baseline: FRESH("GPU baseline", "", false),
  });
  const esRef = useRef<EventSource | null>(null);
  const startRef = useRef<Record<SideKey, number>>({ primary: 0, baseline: 0 });

  function resetSides(r: any) {
    const meta = metaById(r);
    setSides({
      primary: FRESH(meta.primary?.label || "Gemma on AMD", meta.primary?.model || "gemma-4-31b", !!meta.primary?.available),
      baseline: FRESH(meta.baseline?.label || "GPU baseline", meta.baseline?.model || "", !!meta.baseline?.available),
    });
  }

  useEffect(() => {
    fetch(infoPath)
      .then((r) => r.json())
      .then((r) => {
        setInfo(r);
        resetSides(r);
      })
      .catch(() => {});
    return () => esRef.current?.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [infoPath]);

  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => {
      setSides((prev) => {
        const next = { ...prev };
        (["primary", "baseline"] as SideKey[]).forEach((k) => {
          if (next[k].status === "running" && startRef.current[k]) {
            next[k] = { ...next[k], elapsedMs: Date.now() - startRef.current[k] };
          }
        });
        return next;
      });
    }, 50);
    return () => clearInterval(t);
  }, [running]);

  function patch(side: SideKey, p: Partial<SideState>) {
    setSides((prev) => ({ ...prev, [side]: { ...prev[side], ...p } }));
  }

  function start() {
    if (running) return;
    resetSides(info);
    setRunning(true);
    const es = new EventSource(`${API_BASE}${streamPath}`);
    esRef.current = es;
    es.onmessage = (e) => {
      const d = JSON.parse(e.data);
      const side = d.side as SideKey;
      switch (d.event) {
        case "start":
          startRef.current[side] = Date.now();
          patch(side, { status: "running", model: d.model });
          break;
        case "progress":
          patch(side, { tokens: d.tokens, tps: d.tokens_per_sec });
          break;
        case "card":
          setSides((prev) => ({
            ...prev,
            [side]: {
              ...prev[side],
              tokens: d.tokens,
              tps: d.tokens_per_sec,
              cards: [...prev[side].cards, { candidate: d.candidate, verdict: d.verdict, tps: d.card_tokens_per_sec }],
            },
          }));
          break;
        case "done":
          patch(side, { status: "done", totalMs: d.total_ms, elapsedMs: d.total_ms, tokens: d.tokens, tps: d.tokens_per_sec });
          break;
        case "error":
          patch(side, { status: "error", note: d.note || d.reason });
          break;
        case "all_done":
          es.close();
          setRunning(false);
          break;
      }
    };
    es.onerror = () => {
      es.close();
      setRunning(false);
    };
  }

  const c = sides.primary;
  const b = sides.baseline;
  const bothDone = c.totalMs != null && b.totalMs != null && c.totalMs > 0;
  const speedup = bothDone ? b.totalMs! / c.totalMs! : null;
  const totalCards = info?.total_cards ?? 3;

  return (
    <div className="space-y-5">
      <section className="card">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-100">⚡ Gemma on AMD vs GPU baseline — live speed race</h2>
            <p className="mt-1 text-sm text-slate-400">
              Same Gemma task. Same {totalCards} candidates. Same instant. The only variable is the hardware.
            </p>
            {info?.project?.title && (
              <p className="mt-2 text-xs text-slate-500">
                Task: passion-match each candidate against <b className="text-slate-300">{info.project.title}</b>
              </p>
            )}
          </div>
          <button className="btn text-base" onClick={start} disabled={running}>
            {running ? "Racing…" : c.status === "done" ? "Race again" : "Start race →"}
          </button>
        </div>
        <p className="mt-3 text-xs text-slate-500">
          Each full investigation fans out ~10 Gemma agents per candidate — the latency gap compounds with every inference.
        </p>
      </section>

      <div className="grid gap-5 md:grid-cols-2">
        <Pane side={c} accent winner={bothDone && c.totalMs! <= b.totalMs!} totalCards={totalCards} />
        <Pane side={b} accent={false} winner={bothDone && b.totalMs! < c.totalMs!} totalCards={totalCards} />
      </div>

      {speedup && (
        <section className="card text-center">
          <div className="text-sm uppercase tracking-wide text-slate-500">Result</div>
          <div className="mt-1 text-3xl font-bold text-brand">Gemma on AMD finished {speedup.toFixed(1)}× faster</div>
          <div className="mt-1 text-sm text-slate-400">
            {(c.totalMs! / 1000).toFixed(2)}s vs {(b.totalMs! / 1000).toFixed(2)}s · {c.tps.toFixed(0)} vs {b.tps.toFixed(0)} tokens/sec
          </div>
        </section>
      )}
    </div>
  );
}

function Pane({ side, accent, winner, totalCards }: { side: SideState; accent: boolean; winner: boolean; totalCards: number }) {
  const border = winner ? "border-brand" : accent ? "border-slate-700" : "border-slate-800";
  return (
    <div className={`card ${border}`}>
      <div className="mb-3 flex items-center justify-between">
        <div>
          <div className={`text-lg font-semibold ${accent ? "text-brand" : "text-slate-200"}`}>{side.label}</div>
          <div className="font-mono text-xs text-slate-500">{side.model}</div>
        </div>
        {winner && <span className="chip border-brand text-brand">winner</span>}
        {side.status === "error" && <span className="chip">unavailable</span>}
      </div>

      <div className="mb-4 grid grid-cols-3 gap-2 text-center">
        <Metric label="elapsed" value={`${(side.elapsedMs / 1000).toFixed(2)}s`} big />
        <Metric label="tokens/sec" value={side.tps ? side.tps.toFixed(0) : "—"} big accent={accent} />
        <Metric label="tokens" value={side.tokens ? String(side.tokens) : "—"} />
      </div>

      <div className="mb-3 h-1.5 rounded-full bg-slate-800">
        <div
          className={`h-1.5 rounded-full transition-all ${accent ? "bg-brand" : "bg-slate-500"}`}
          style={{ width: `${Math.min((side.cards.length / totalCards) * 100, 100)}%` }}
        />
      </div>

      {side.note && <p className="mb-2 text-xs text-amber-400">{side.note}</p>}

      <ol className="space-y-2">
        {side.cards.map((card, i) => (
          <li key={i} className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-slate-200">{card.candidate}</span>
              <span className="font-mono text-xs text-slate-500">{card.tps ? `${card.tps.toFixed(0)} tok/s` : ""}</span>
            </div>
            <p className="mt-1 text-xs text-slate-400">{card.verdict}</p>
          </li>
        ))}
        {side.status === "running" && side.cards.length < totalCards && (
          <li className="rounded-lg border border-dashed border-slate-800 p-3 text-xs text-slate-500">
            analyzing candidate {side.cards.length + 1} of {totalCards}…
          </li>
        )}
      </ol>
    </div>
  );
}

function Metric({ label, value, big, accent }: { label: string; value: string; big?: boolean; accent?: boolean }) {
  return (
    <div className="rounded-lg bg-slate-900/60 py-2">
      <div className={`font-mono ${big ? "text-xl" : "text-base"} ${accent ? "text-brand" : "text-slate-200"}`}>{value}</div>
      <div className="text-[10px] uppercase tracking-wide text-slate-500">{label}</div>
    </div>
  );
}
