// Generated with OpenUI (see frontend/openui/PROMPTS.md #1), exported to React+TS.
"use client";

import { useState } from "react";
import { pct } from "@/lib/api";

/**
 * A score you can interrogate. Click it to see WHY this candidate got this number.
 * The explanation is derived from the same inputs the score was computed from, so
 * it can never disagree with the number it explains.
 */
export function ScoreBar({ label, value, reason }: { label: string; value: number; reason?: string }) {
  const [open, setOpen] = useState(false);
  const canExplain = Boolean(reason);

  return (
    <div>
      <button
        type="button"
        onClick={() => canExplain && setOpen((o) => !o)}
        disabled={!canExplain}
        aria-expanded={open}
        title={canExplain ? "Why this score?" : undefined}
        className={`group w-full text-left ${canExplain ? "cursor-pointer" : "cursor-default"}`}
      >
        <div className="mb-1 flex items-center justify-between text-xs text-slate-400">
          <span className={canExplain ? "group-hover:text-slate-200" : ""}>
            {label}
            {canExplain && (
              <span
                className={`ml-1 inline-block text-[9px] text-slate-600 transition-transform group-hover:text-brand ${
                  open ? "rotate-90" : ""
                }`}
              >
                ▶
              </span>
            )}
          </span>
          <span className="tabular-nums text-slate-300">{pct(value)}</span>
        </div>
        <div className="h-2 rounded-full bg-slate-800">
          <div className="h-2 rounded-full bg-brand transition-all" style={{ width: pct(value) }} />
        </div>
      </button>
      {open && reason && (
        <p className="mt-2 rounded-lg border border-slate-800 bg-slate-900/60 p-2.5 text-[11px] leading-relaxed text-slate-400">
          {reason}
        </p>
      )}
    </div>
  );
}
