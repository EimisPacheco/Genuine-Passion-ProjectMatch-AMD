"use client";

import { useEffect, useMemo, useState } from "react";
import { api, PoolCandidate, PoolDetail } from "@/lib/api";

/**
 * The Talent Pool — everyone the system has ever found, across all analyses.
 * A recruiter browses who's already been discovered (and how to reach them)
 * instead of re-running a search. Click any card to see that person exactly as
 * they were first found — their full evidence trail. Discovery reuses these
 * people automatically.
 */
export default function PoolPage() {
  const [pool, setPool] = useState<PoolCandidate[] | null>(null);
  const [q, setQ] = useState("");
  const [onlyContactable, setOnlyContactable] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);

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
  const openCandidate = pool.find((c) => c.id === openId) || null;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">Talent pool</h1>
        <p className="mt-1 text-sm text-slate-400">
          Everyone found across every analysis — <b className="text-slate-200">{pool.length}</b> people,
          <b className="text-slate-200"> {contactable}</b> contactable. New runs reuse these instead of
          searching again. <span className="text-slate-500">Click anyone to see how they were first found.</span>
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
            <button
              key={c.id}
              onClick={() => setOpenId(c.id)}
              className="card cursor-pointer text-left transition hover:border-brand/50 hover:bg-slate-800/40 focus:outline-none focus:ring-1 focus:ring-brand/60"
            >
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
                  <a href={`https://github.com/${c.github_handle}`} target="_blank" onClick={(e) => e.stopPropagation()}
                    className="shrink-0 text-xs text-brand/70 hover:text-brand">github.com/{c.github_handle}</a>
                )}
              </div>

              <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-400">
                {[c.city, c.state, c.country].filter(Boolean).length > 0 && (
                  <span>📍 {[c.city, c.state, c.country].filter(Boolean).join(", ")}</span>
                )}
                {c.email && <a href={`mailto:${c.email}`} onClick={(e) => e.stopPropagation()} className="hover:text-brand">✉️ {c.email}</a>}
                {c.linkedin_url && (
                  <a href={c.linkedin_url} target="_blank" onClick={(e) => e.stopPropagation()} className="text-emerald-300 hover:text-emerald-200">🔗 LinkedIn</a>
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
              <div className="mt-2 text-[11px] text-brand/70">View how they were found →</div>
            </button>
          ))}
        </div>
      )}

      {openCandidate && <CandidateDrawer candidate={openCandidate} onClose={() => setOpenId(null)} />}
    </div>
  );
}

/** Slide-over detail: the candidate exactly as first found, with a clear way back. */
function CandidateDrawer({ candidate, onClose }: { candidate: PoolCandidate; onClose: () => void }) {
  const [detail, setDetail] = useState<PoolDetail | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setDetail(null);
    setFailed(false);
    api.poolCandidate(candidate.id).then(setDetail).catch(() => setFailed(true));
  }, [candidate.id]);

  // Esc closes; lock body scroll while open.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose]);

  const place = [candidate.city, candidate.state, candidate.country].filter(Boolean).join(", ");

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/60" onClick={onClose}>
      <div
        className="h-full w-full max-w-2xl overflow-y-auto border-l border-slate-700 bg-slate-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Sticky header with the return control — always reachable while scrolling. */}
        <div className="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-slate-800 bg-slate-900/95 px-5 py-3 backdrop-blur">
          <button onClick={onClose} className="flex items-center gap-1.5 text-sm text-slate-300 hover:text-brand">
            ← Back to pool
          </button>
          <button onClick={onClose} aria-label="Close" className="text-slate-500 hover:text-slate-200">✕</button>
        </div>

        <div className="space-y-5 px-5 py-5">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-xl font-bold text-slate-100">{candidate.name}</h2>
              {candidate.contactable ? (
                <span className="chip border-emerald-500/40 text-[10px] text-emerald-300">contactable</span>
              ) : (
                <span className="chip text-[10px] text-slate-500">no LinkedIn</span>
              )}
            </div>
            {candidate.headline && <p className="mt-1 text-sm text-slate-400">{candidate.headline}</p>}
            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-400">
              {candidate.github_handle && (
                <a href={`https://github.com/${candidate.github_handle}`} target="_blank" className="text-brand/80 hover:text-brand">github.com/{candidate.github_handle}</a>
              )}
              {place && <span>📍 {place}</span>}
              {candidate.email && <a href={`mailto:${candidate.email}`} className="hover:text-brand">✉️ {candidate.email}</a>}
              {candidate.linkedin_url && (
                <a href={candidate.linkedin_url} target="_blank" className="text-emerald-300 hover:text-emerald-200">🔗 LinkedIn</a>
              )}
            </div>
          </div>

          {(candidate.technologies?.length ?? 0) > 0 && (
            <div>
              <h3 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Technologies used</h3>
              <div className="flex flex-wrap gap-1">
                {candidate.technologies.map((t) => (
                  <span key={t} className="chip normal-case text-[10px]">{t}</span>
                ))}
              </div>
            </div>
          )}

          <div>
            <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              Evidence — as first found {detail && <span className="text-slate-600">({detail.evidence.length})</span>}
            </h3>
            {failed ? (
              <p className="text-sm text-slate-500">Couldn’t load this candidate’s evidence.</p>
            ) : !detail ? (
              <p className="text-sm text-slate-500">Loading evidence…</p>
            ) : detail.evidence.length === 0 ? (
              <p className="text-sm text-slate-500">No stored evidence for this candidate.</p>
            ) : (
              <div className="space-y-2.5">
                {detail.evidence.map((e) => (
                  <div key={e.id} className="rounded-lg border border-slate-800 bg-slate-800/30 p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        {e.url ? (
                          <a href={e.url} target="_blank" className="font-medium text-slate-100 hover:text-brand">{e.title || e.url}</a>
                        ) : (
                          <span className="font-medium text-slate-100">{e.title || "(untitled)"}</span>
                        )}
                      </div>
                      <span className="chip shrink-0 text-[10px] text-slate-400">{e.source || "source"}</span>
                    </div>
                    {e.description && <p className="mt-1 line-clamp-3 text-xs text-slate-400">{e.description}</p>}
                    <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] text-slate-500">
                      {e.evidence_date && <span>{e.evidence_date}</span>}
                      {e.technologies?.slice(0, 6).map((t) => (
                        <span key={t} className="chip normal-case text-[10px]">{t}</span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
