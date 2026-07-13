"use client";

import { useEffect, useMemo, useState } from "react";
import { api, PoolCandidate } from "@/lib/api";

/**
 * The Talent Pool — everyone the system has ever found, across all analyses.
 * A recruiter browses who's already been discovered (and how to reach them)
 * instead of re-running a search. Discovery reuses these people automatically.
 */
export default function PoolPage() {
  const [pool, setPool] = useState<PoolCandidate[] | null>(null);
  const [q, setQ] = useState("");
  const [onlyContactable, setOnlyContactable] = useState(false);

  useEffect(() => {
    api.pool().then((r) => setPool(r.candidates)).catch(() => setPool([]));
  }, []);

  const shown = useMemo(() => {
    if (!pool) return [];
    const needle = q.trim().toLowerCase();
    return pool.filter((c) => {
      if (onlyContactable && !c.contactable) return false;
      if (!needle) return true;
      const hay = [
        c.name, c.github_handle, c.headline, c.city, c.state, c.country,
        ...(c.technologies || []),
      ].join(" ").toLowerCase();
      return hay.includes(needle);
    });
  }, [pool, q, onlyContactable]);

  if (pool === null) return <p className="text-slate-500">Loading the talent pool…</p>;

  const contactable = pool.filter((c) => c.contactable).length;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">Talent pool</h1>
        <p className="mt-1 text-sm text-slate-400">
          Everyone found across every analysis — <b className="text-slate-200">{pool.length}</b> people,
          <b className="text-slate-200"> {contactable}</b> contactable. New runs reuse these instead of
          searching again.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <input
          className="input max-w-md"
          placeholder="Search by name, handle, technology, location…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-300">
          <input type="checkbox" checked={onlyContactable} onChange={(e) => setOnlyContactable(e.target.checked)} />
          Has LinkedIn
        </label>
        <span className="ml-auto text-xs text-slate-500">{shown.length} shown</span>
      </div>

      {!shown.length ? (
        <p className="text-slate-500">
          {pool.length ? "No candidates match that filter." : "No candidates yet — run an analysis to populate the pool."}
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {shown.map((c) => (
            <div key={c.id} className="card">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="truncate font-semibold text-slate-100">{c.name}</span>
                    {c.contactable ? (
                      <span className="chip border-emerald-500/40 text-[10px] text-emerald-300">contactable</span>
                    ) : (
                      <span className="chip text-[10px] text-slate-500">no LinkedIn</span>
                    )}
                  </div>
                  {c.headline && <div className="truncate text-xs text-slate-500">{c.headline}</div>}
                </div>
                {c.github_handle && (
                  <a href={`https://github.com/${c.github_handle}`} target="_blank"
                    className="shrink-0 text-xs text-brand/70 hover:text-brand">github.com/{c.github_handle}</a>
                )}
              </div>

              <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-400">
                {[c.city, c.state, c.country].filter(Boolean).length > 0 && (
                  <span>📍 {[c.city, c.state, c.country].filter(Boolean).join(", ")}</span>
                )}
                {c.email && <a href={`mailto:${c.email}`} className="hover:text-brand">✉️ {c.email}</a>}
                {c.linkedin_url && (
                  <a href={c.linkedin_url} target="_blank" className="text-emerald-300 hover:text-emerald-200">🔗 LinkedIn</a>
                )}
                <span className="text-slate-600">· {c.evidence_count} evidence · {(c.sources || []).length} sources</span>
              </div>

              {(c.technologies?.length ?? 0) > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {c.technologies.slice(0, 12).map((t) => (
                    <span key={t} className="chip normal-case text-[10px]">{t}</span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
