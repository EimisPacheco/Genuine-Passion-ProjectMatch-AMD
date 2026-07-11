// Generated with OpenUI (see frontend/openui/PROMPTS.md #3), exported to React+TS.
import { Evidence, pct } from "@/lib/api";

export function EvidenceCard({ e }: { e: Evidence }) {
  return (
    <a href={e.url} target="_blank" className="card transition hover:border-brand/50">
      <div className="mb-1 flex items-center gap-2">
        <span className="chip uppercase">{e.source}</span>
        <span className="text-xs text-slate-500">{e.evidence_date}</span>
        <span className="ml-auto text-xs text-slate-500">conf {pct(e.confidence)}</span>
      </div>
      <div className="font-medium text-slate-100">{e.title}</div>
      <p className="mt-1 line-clamp-3 text-sm text-slate-400">{e.description}</p>
      <div className="mt-2 truncate text-xs text-brand/70">{e.url}</div>
    </a>
  );
}
