"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

type Cand = { id: string; name: string; headline: string; github_handle: string; links?: string[]; linksText?: string };
type Mode = "discovery" | "applicants";

const PRESETS: {
  label: string;
  mode: Mode;
  live: boolean;
  project: any;
  candidates: Cand[];
}[] = [
  {
    label: "LIVE · LLM inference platform",
    mode: "applicants",
    live: true,
    project: {
      title: "Serverless GPU LLM Inference Platform",
      description:
        "A platform to deploy and autoscale open-source LLMs on GPUs with scale-to-zero, OpenAI-compatible APIs, and low cold-start. Core problems: vLLM serving, quantization (GPTQ/AWQ/GGUF), GPU memory snapshots, CUDA graphs, and minimizing serverless cold-start latency.",
      business_problem: "Teams want to serve open LLMs cheaply and elastically but hit slow GPU cold starts and complex quantized-serving setups.",
      target_users: "ML platform engineers and AI product teams.",
      expected_technologies: ["vLLM", "Python", "CUDA", "quantization", "GPU", "serverless", "inference"],
    },
    candidates: [
      { id: "gh_infinitylogesh", name: "Logesh Kumar Umapathi", headline: "vLLM serverless cold-start · StarCoder co-author", github_handle: "infinitylogesh" },
      { id: "gh_chu-tianxiang", name: "CHU Tianxiang", headline: "Quantized inference; GPTQ merged into vLLM", github_handle: "chu-tianxiang" },
      { id: "gh_carteakey", name: "Kartikey Chauhan", headline: "Local LLM inference optimization (llama.cpp/QAT)", github_handle: "carteakey" },
      { id: "gh_yousefed_ctrl", name: "Yousef El-Dardiry", headline: "Local-first / CRDT editors (cross-domain)", github_handle: "YousefED" },
      { id: "gh_doguilmak_ctrl", name: "Doğu İlmak", headline: "Geospatial / remote-sensing ML (cross-domain)", github_handle: "doguilmak" },
    ],
  },
  {
    label: "LIVE · Local-first (CRDT)",
    mode: "applicants",
    live: true,
    project: {
      title: "Local-First Collaborative Editor (CRDTs)",
      description:
        "An offline-first, real-time collaborative code/notes editor built on CRDTs (Yjs, Automerge), with a sync engine and end-to-end encryption. Needs deep local-first and CRDT expertise, offline sync, and conflict-free replication.",
      business_problem: "Users need real-time collaboration that also works offline, with data ownership and no central lock-in.",
      target_users: "Engineers building collaborative, offline-capable apps.",
      expected_technologies: ["CRDT", "yjs", "automerge", "typescript", "rust", "sqlite", "offline", "collaboration"],
    },
    candidates: [
      { id: "gh_yousefed", name: "Yousef El-Dardiry", headline: "BlockNote, SyncedStore, Matrix-CRDT (Yjs)", github_handle: "YousefED" },
      { id: "gh_horusiath", name: "Bartosz Sypytkowski", headline: "Yrs (Rust Yjs) core; CRDT internals", github_handle: "Horusiath" },
      { id: "gh_alexanderop", name: "Alexander Opalic", headline: "awesome-local-first; offline-first apps", github_handle: "alexanderop" },
      { id: "gh_infinitylogesh_ctrl", name: "Logesh Kumar Umapathi", headline: "LLM inference infra (cross-domain)", github_handle: "infinitylogesh" },
      { id: "gh_doguilmak_ctrl2", name: "Doğu İlmak", headline: "Geospatial ML (cross-domain)", github_handle: "doguilmak" },
    ],
  },
  {
    label: "LIVE · Geospatial / climate ML",
    mode: "applicants",
    live: true,
    project: {
      title: "Geospatial ML for Wildfire & Climate",
      description:
        "A system that uses satellite and aerial imagery with ML to detect and predict wildfires and deforestation. Needs remote sensing, earth observation, geospatial ML, segmentation on satellite data, and work with Sentinel/Landsat/MODIS datasets.",
      business_problem: "Agencies need earlier, more accurate wildfire and deforestation detection from satellite data.",
      target_users: "Climate-tech teams and geospatial data scientists.",
      expected_technologies: ["satellite", "segmentation", "pytorch", "tensorflow", "rasterio", "geospatial", "cnn", "remote-sensing"],
    },
    candidates: [
      { id: "gh_doguilmak", name: "Doğu İlmak", headline: "Wildfire/EO deep learning; ISPRS paper", github_handle: "doguilmak" },
      { id: "gh_jbric16", name: "Jose Bric", headline: "NASA Space Apps wildfire ConvLSTM", github_handle: "jbric16" },
      { id: "gh_triveditr1013", name: "Triveditr", headline: "NASA wildfire detection (MODIS/EarthData)", github_handle: "triveditr1013" },
      { id: "gh_chu-tianxiang_ctrl", name: "CHU Tianxiang", headline: "LLM quantization (cross-domain)", github_handle: "chu-tianxiang" },
      { id: "gh_horusiath_ctrl", name: "Bartosz Sypytkowski", headline: "CRDT internals (cross-domain)", github_handle: "Horusiath" },
    ],
  },
];

export default function Home() {
  const router = useRouter();
  const [project, setProject] = useState<any>(PRESETS[0].project);
  const [sources, setSources] = useState<Cand[]>(PRESETS[0].candidates);
  const [topN, setTopN] = useState(3);
  // Every run is live: the seeded demo is hidden, so there is no seeded evidence
  // to fall back on — an un-ticked 'live' run would simply find nothing.
  const [live] = useState(true);
  const [loading, setLoading] = useState(false);
  const [activePreset, setActivePreset] = useState(0);
  const [mode, setMode] = useState<Mode>("applicants");

  useEffect(() => {
    // hydrate expected_features from the backend defaults
    api.defaults().then((d) => {
      setProject((p: any) => ({ ...p, expected_features: d.company_project.expected_features }));
    }).catch(() => {});
  }, []);

  function applyPreset(i: number) {
    setActivePreset(i);
    setProject(PRESETS[i].project);
    setSources(PRESETS[i].candidates.map((c) => ({ ...c })));
    setMode(PRESETS[i].mode);
  }

  function switchMode(m: Mode) {
    setMode(m);
  }

  function updateCand(i: number, field: keyof Cand, value: string) {
    setSources((s) => s.map((c, j) => (j === i ? { ...c, [field]: value } : c)));
  }
  function addCand() {
    setSources((s) => [...s, { id: `cand_${Date.now()}`, name: "", headline: "", github_handle: "" }]);
  }
  function removeCand(i: number) {
    setSources((s) => s.filter((_, j) => j !== i));
  }

  async function launch() {
    setLoading(true);
    try {
      const discover = mode === "discovery";
      const body: any = {
        live_mode: discover ? true : live,
        top_n: topN,
        discover_candidates: discover,
        company_project: {
          title: project.title,
          description: project.description,
          business_problem: project.business_problem,
          target_users: project.target_users,
          expected_features: project.expected_features || [],
          expected_technologies: project.expected_technologies || [],
          desired_candidates: topN,
        },
      };
      // Free Discovery sends no people — the backend finds them from the mission.
      if (!discover) {
        body.candidate_sources = sources
          .filter((c) => c.github_handle || c.name || (c.links && c.links.length) || c.linksText)
          .map((c) => ({
            id: c.id,
            name: c.name || c.github_handle,
            headline: c.headline,
            github_handle: c.github_handle,
            sources: [
              ...(c.github_handle ? [`https://github.com/${c.github_handle}`] : []),
              ...(c.links || []),
              // Extra links the applicant provided (LinkedIn/Medium…). Optional —
              // the backend also auto-discovers sources from the GitHub profile.
              ...(c.linksText || "").split(/[\s,]+/).map((s) => s.trim()).filter(Boolean),
            ],
          }));
      }
      const { analysis_id } = await api.createAnalysis(body);
      router.push(`/analysis/${analysis_id}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <CathedralHero />

      {/* Presets */}
      <section className="card">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-brand">
          Quick-start examples
        </h2>
        <div className="flex flex-wrap gap-2">
          {PRESETS.map((p, i) => (
            <button
              key={p.label}
              onClick={() => applyPreset(i)}
              className={i === activePreset ? "btn text-sm" : "btn-ghost text-sm"}
            >
              {p.label}
            </button>
          ))}
        </div>
        <p className="mt-3 text-xs text-slate-500">
          Every candidate is investigated across <b>all</b> sources — GitHub, Dev.to, Hacker News,
          Devpost, Kaggle and their personal site — plus <b>LinkedIn, Medium and lablab.ai</b>,
          unblocked with Bright Data. Everything is read live; nothing is pre-canned.
        </p>
      </section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Project Intake */}
        <section className="card lg:col-span-2">
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-brand">
            1 · The mission
          </h2>
          <div className="space-y-3">
            <div>
              <label className="label">Project title</label>
              <input className="input" value={project.title}
                onChange={(e) => setProject({ ...project, title: e.target.value })} />
            </div>
            <div>
              <label className="label">Description</label>
              <textarea className="input h-24" value={project.description}
                onChange={(e) => setProject({ ...project, description: e.target.value })} />
            </div>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <div>
                <label className="label">Business problem</label>
                <textarea className="input h-20" value={project.business_problem}
                  onChange={(e) => setProject({ ...project, business_problem: e.target.value })} />
              </div>
              <div>
                <label className="label">Target users</label>
                <textarea className="input h-20" value={project.target_users}
                  onChange={(e) => setProject({ ...project, target_users: e.target.value })} />
              </div>
            </div>
            <div className="flex flex-wrap gap-2 pt-1">
              {(project.expected_technologies || []).map((t: string) => (
                <span key={t} className="chip">{t}</span>
              ))}
            </div>
          </div>
        </section>

        {/* Run */}
        <section className="card flex flex-col justify-between">
          <div>
            <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-brand">Run</h2>
            <label className="label">Number of candidates (Top N)</label>
            <div className="flex gap-2">
              {[3, 5, 10].map((n) => (
                <button key={n} onClick={() => setTopN(n)}
                  className={n === topN ? "btn" : "btn-ghost"}>Top {n}</button>
              ))}
            </div>
            <p className="mt-5 text-xs text-slate-500">
              Every source is queried live for each candidate — GitHub, Dev.to, Hacker News,
              Devpost, Kaggle, their personal site, plus <b className="text-slate-300">LinkedIn,
              Medium and lablab.ai</b> through Bright Data. A source with nothing for a candidate
              simply returns nothing.
            </p>
            <p className="mt-2 text-xs text-amber-200/70">
              Real scraping and Gemma on one GPU — a run takes a few minutes.
            </p>
          </div>
          <button className="btn mt-6 w-full" onClick={launch}
            disabled={loading || (mode === "applicants" && !sources.some((c) => c.github_handle))}>
            {loading ? "Starting…" : mode === "discovery" ? "Discover passion →" : "Match applicants →"}
          </button>
        </section>

        {/* Candidate Input */}
        <section className="card lg:col-span-3">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-brand">
              2 · Who to investigate
            </h2>
            {mode === "applicants" && (
              <button className="btn-ghost text-sm" onClick={addCand}>+ Add candidate</button>
            )}
          </div>

          {/* Mode tabs */}
          <div className="mb-3 flex flex-wrap gap-2">
            <div className={`tab ${mode === "discovery" ? "tab-active" : ""}`} onClick={() => switchMode("discovery")}>
              🔍 Free Discovery
            </div>
            <div className={`tab ${mode === "applicants" ? "tab-active" : ""}`} onClick={() => switchMode("applicants")}>
              📋 Applicants
            </div>
          </div>

          {mode === "discovery" ? (
            <div className="rounded-lg border border-dashed border-slate-700 bg-slate-900/30 p-6 text-center">
              <div className="mb-2 text-2xl">🔭</div>
              <h3 className="text-base font-semibold text-slate-100">
                Sourcing people who never applied
              </h3>
              <p className="mx-auto mt-2 max-w-xl text-sm text-slate-400">
                You add nothing here. The app searches GitHub for builders whose public
                work matches <b className="text-slate-300">{project.title || "the mission above"}</b>,
                then investigates each one — their repos, hackathons, blog, Dev.to and Kaggle —
                and ranks the <b className="text-slate-300">Top {topN}</b> with cited evidence.
              </p>
              <div className="mt-4 flex flex-wrap justify-center gap-2">
                {(project.expected_technologies || []).slice(0, 6).map((t: string) => (
                  <span key={t} className="chip">{t}</span>
                ))}
              </div>
              <p className="mt-4 text-[11px] text-slate-500">
                Tip: the more specific the project’s technologies, the sharper the people it finds.
              </p>
            </div>
          ) : (
            <>
              <p className="mb-4 text-xs text-slate-500">
                People who actually applied. Only the <b className="text-slate-300">GitHub handle</b> is
                required — name and other links are optional, and the app still auto-discovers
                their Dev.to, Kaggle, Devpost, personal site, Medium and hackathons from the handle.
              </p>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                {sources.map((c, i) => (
                  <div key={c.id} className="rounded-lg border border-slate-800 p-4">
                    <div className="mb-2 flex items-center justify-between">
                      <input className="input" placeholder="Name (optional)" value={c.name}
                        onChange={(e) => updateCand(i, "name", e.target.value)} />
                      <button className="ml-2 text-slate-600 hover:text-red-400" onClick={() => removeCand(i)}>✕</button>
                    </div>
                    <input className="input mb-2" placeholder="GitHub handle — required (e.g. gaearon)" value={c.github_handle}
                      onChange={(e) => updateCand(i, "github_handle", e.target.value)} />
                    {c.github_handle && (
                      <div className="mb-2 truncate text-xs text-brand/70">github.com/{c.github_handle}</div>
                    )}
                    <input className="input" placeholder="Other links — LinkedIn, Medium… (optional)"
                      value={c.linksText || ""} onChange={(e) => updateCand(i, "linksText", e.target.value)} />
                    <div className="mt-1 text-[10px] text-slate-500">
                      Auto-checked from the handle: Dev.to · HN · Devpost · Kaggle · personal site · Medium · hackathons.
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
}

/**
 * Pure CSS/SVG cathedral hero — no external image, always loads. A cathedral of
 * light: the mission is the altar, and we match the people who are genuinely
 * called to build toward it.
 */
function CathedralHero() {
  return (
    <section className="relative overflow-hidden rounded-2xl border border-slate-800">
      <svg viewBox="0 0 1200 420" className="absolute inset-0 h-full w-full" preserveAspectRatio="xMidYMid slice" aria-hidden>
        <defs>
          <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#1e1b4b" />
            <stop offset="45%" stopColor="#312e81" />
            <stop offset="100%" stopColor="#0f172a" />
          </linearGradient>
          <radialGradient id="halo" cx="50%" cy="34%" r="42%">
            <stop offset="0%" stopColor="#fbbf24" stopOpacity="0.55" />
            <stop offset="45%" stopColor="#f472b6" stopOpacity="0.18" />
            <stop offset="100%" stopColor="#312e81" stopOpacity="0" />
          </radialGradient>
          <radialGradient id="rose" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#fde68a" />
            <stop offset="35%" stopColor="#fb7185" />
            <stop offset="65%" stopColor="#a78bfa" />
            <stop offset="100%" stopColor="#38bdf8" />
          </radialGradient>
          <linearGradient id="stone" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#0b1022" stopOpacity="0.92" />
            <stop offset="100%" stopColor="#020617" stopOpacity="0.98" />
          </linearGradient>
        </defs>

        <rect width="1200" height="420" fill="url(#sky)" />
        <rect width="1200" height="420" fill="url(#halo)" />

        {/* Light rays from behind the spire */}
        <g opacity="0.35" transform="translate(600 150)">
          {Array.from({ length: 11 }).map((_, i) => (
            <polygon key={i} points="0,0 -34,-520 34,-520" fill="#fcd34d" opacity={0.08 + (i % 3) * 0.03}
              transform={`rotate(${(i - 5) * 15})`} />
          ))}
        </g>

        {/* Cathedral silhouette */}
        <g fill="url(#stone)">
          {/* left & right towers */}
          <rect x="300" y="180" width="70" height="240" />
          <polygon points="300,180 335,110 370,180" />
          <rect x="830" y="180" width="70" height="240" />
          <polygon points="830,180 865,110 900,180" />
          {/* nave */}
          <rect x="430" y="210" width="340" height="210" />
          {/* central spire */}
          <polygon points="600,40 560,210 640,210" />
          {/* pointed-arch doorway */}
          <path d="M560 420 L560 320 Q600 270 640 320 L640 420 Z" fill="#020617" />
        </g>

        {/* Rose window */}
        <g transform="translate(600 190)">
          <circle r="46" fill="url(#rose)" opacity="0.95" />
          {Array.from({ length: 12 }).map((_, i) => (
            <line key={i} x1="0" y1="0" x2="0" y2="-46" stroke="#0b1022" strokeWidth="2.5"
              transform={`rotate(${i * 30})`} />
          ))}
          <circle r="46" fill="none" stroke="#0b1022" strokeWidth="4" />
          <circle r="14" fill="#fffbeb" opacity="0.9" />
        </g>

        {/* Lancet windows glowing in the nave */}
        <g fill="#fbbf24" opacity="0.6">
          {[470, 520, 680, 730].map((x) => (
            <path key={x} d={`M${x} 400 L${x} 310 Q${x + 14} 288 ${x + 28} 310 L${x + 28} 400 Z`} />
          ))}
        </g>
      </svg>

      <div className="relative px-8 py-14 sm:px-12 sm:py-20">
        <p className="mb-3 text-xs font-semibold uppercase tracking-[0.25em] text-amber-300/80">
          Multi-Agent Passion Intelligence
        </p>
        <h1 className="max-w-2xl text-3xl font-bold leading-tight text-white sm:text-4xl">
          Find the people who <span className="text-amber-300">can’t stop building</span> toward your mission.
        </h1>
        <p className="mt-4 max-w-2xl text-sm leading-relaxed text-slate-300 sm:text-base">
          A cathedral is built by people who believe in it. A swarm of Gemma agents reads a person’s
          real public work — code, hackathons, writing, and images — to reveal genuine passion,
          then matches it to the mission you’re building. Evidence-cited. No resumes required.
        </p>
        <div className="mt-6 flex flex-wrap gap-2 text-xs text-slate-400">
          <span className="rounded-full border border-slate-700 bg-slate-900/50 px-3 py-1">10 agents</span>
          <span className="rounded-full border border-slate-700 bg-slate-900/50 px-3 py-1">Multimodal · reads images</span>
          <span className="rounded-full border border-slate-700 bg-slate-900/50 px-3 py-1">Gemma on AMD MI300X</span>
          <span className="rounded-full border border-slate-700 bg-slate-900/50 px-3 py-1">Cited evidence</span>
        </div>
      </div>
    </section>
  );
}
