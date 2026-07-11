// Generated with OpenUI (see frontend/openui/PROMPTS.md #1), exported to React+TS.
import { pct } from "@/lib/api";

export function ScoreBar({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs text-slate-400">
        <span>{label}</span>
        <span className="text-slate-300">{pct(value)}</span>
      </div>
      <div className="h-2 rounded-full bg-slate-800">
        <div className="h-2 rounded-full bg-brand" style={{ width: pct(value) }} />
      </div>
    </div>
  );
}
