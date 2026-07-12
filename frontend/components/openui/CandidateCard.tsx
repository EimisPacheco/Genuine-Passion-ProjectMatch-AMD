// Generated with OpenUI (see frontend/openui/PROMPTS.md #2), exported to React+TS.
import { Candidate, pct } from "@/lib/api";
import { ScoreBar } from "./ScoreBar";

function ContactInfo({ c }: { c: Candidate }) {
  const place = [c.city, c.state, c.country].filter(Boolean).join(", ") || c.location;
  const items: JSX.Element[] = [];
  if (place) items.push(<span key="loc">📍 {place}</span>);
  if (c.email) items.push(<a key="mail" href={`mailto:${c.email}`} className="hover:text-brand">✉️ {c.email}</a>);
  if (c.linkedin_url)
    items.push(<a key="li" href={c.linkedin_url} target="_blank" className="text-emerald-300 hover:text-emerald-200">🔗 LinkedIn</a>);
  else
    items.push(<span key="noli" className="text-amber-300/90">⚠️ no LinkedIn — not contactable</span>);
  return (
    <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-400">
      {items}
    </div>
  );
}

export function CandidateCard({ c, onPick }: { c: Candidate; onPick: (cid: string) => void }) {
  return (
    <div className={`card ${c.selected ? "border-brand/50" : "opacity-70"}`}>
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-lg font-semibold text-slate-100">
              #{c.rank} {c.name}
            </span>
            {c.selected && <span className="chip border-brand/40 text-brand">selected</span>}
          </div>
          <div className="text-xs text-slate-500">{c.headline}</div>
          <ContactInfo c={c} />
        </div>
        <div className="text-right">
          <div className="text-2xl font-bold text-brand">{pct(c.overall_score)}</div>
          <div className="text-xs text-slate-500">overall match</div>
        </div>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-3">
        <ScoreBar label="Project similarity" value={c.project_similarity} />
        <ScoreBar label="Genuine passion" value={c.genuine_passion} />
        <ScoreBar label="Domain" value={c.domain_similarity} />
        <ScoreBar label="Code" value={c.code_score} />
        <ScoreBar label="Design" value={c.design_score} />
        <ScoreBar label="Evidence quality" value={c.evidence_quality} />
      </div>
      <div className="mt-3 flex items-center justify-between">
        <span className="text-sm text-slate-400">{c.recommendation}</span>
        <button className="btn-ghost text-sm" onClick={() => onPick(c.candidate_id)}>
          Details →
        </button>
      </div>
    </div>
  );
}
