// Generated with OpenUI (see frontend/openui/PROMPTS.md #4), exported to React+TS.

function dot(status: string): string {
  if (status === "ok") return "bg-emerald-400";
  if (status === "error") return "bg-red-400";
  if (status === "done") return "bg-brand";
  return "bg-amber-400";
}

function fmtElapsed(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(s / 60);
  return m > 0 ? `${m}m ${String(s % 60).padStart(2, "0")}s` : `${s}s`;
}

export function AgentProgressList(
  { events, pctDone, elapsedMs, running }:
  { events: any[]; pctDone: number; elapsedMs?: number; running?: boolean },
) {
  return (
    <div className="card">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="font-semibold">Analysis Progress</h3>
        <div className="flex items-center gap-3 text-sm text-slate-400">
          {elapsedMs !== undefined && (
            <span className="inline-flex items-center gap-1.5 font-mono tabular-nums">
              <span className={`h-1.5 w-1.5 rounded-full ${running ? "bg-amber-400 animate-pulse" : "bg-emerald-400"}`} />
              {running ? "Elapsed" : "Finished in"} {fmtElapsed(elapsedMs)}
            </span>
          )}
          <span>{pctDone}%</span>
        </div>
      </div>
      <div className="mb-5 h-2 rounded-full bg-slate-800">
        <div className="h-2 rounded-full bg-brand transition-all" style={{ width: `${pctDone}%` }} />
      </div>
      <ol className="space-y-2">
        {events.map((e, i) => (
          <li key={i} className="flex items-center gap-3 text-sm">
            <span className={`h-2 w-2 rounded-full ${dot(e.status)}`} />
            <span className="w-44 font-mono text-xs text-slate-400">{e.agent}</span>
            <span className="text-slate-300">{e.detail || e.status}</span>
          </li>
        ))}
        {!events.length && <p className="text-slate-500">Waiting for agents to start…</p>}
      </ol>
    </div>
  );
}
