# Multi-Agent Passion Intelligence

**A swarm of Gemma agents on an AMD Instinct MI300X discovers what people can't stop building.**

🔗 **Live app:** <https://passion-intelligence.vercel.app> · **API health:** <https://129-212-179-131.sslip.io/api/health>

> Built for the **AMD Developer Hackathon (ACT II — Track 3)**. Everything runs on
> **Gemma 4 31B served by Ollama on the AMD MI300X**: text reasoning, vision, *and*
> embeddings. See [docs/AMD_SUBMISSION.md](docs/AMD_SUBMISSION.md).

Resumes describe what people *say* they can do. Side projects reveal what they
*can't stop building*. This system turns that into a **10-agent investigation**:
Gemma agents read a person's public technical work (GitHub, hackathons, Kaggle,
blogs) **and their images** (architecture diagrams, product screenshots), build a
passion fingerprint, and match it to a mission — every claim cited to a real URL.

> Main question: *What does this person repeatedly, voluntarily choose to build —
> and what mission is that genuine obsession a match for?*

### Why startups care

Startups can't outspend Big Tech on salary or brand. They win by hiring the few
people **already building toward their problem** — most of whom will never apply.
**Free Discovery** finds those people from your mission alone.

---

## Architecture

```mermaid
flowchart TB
  R([Recruiter / founder]) --> FE[Next.js dashboard · Vercel]
  FE --> API[FastAPI + SSE · droplet]

  subgraph P[LangGraph · 10-agent pipeline]
    direction LR
    A1[1 Project<br/>Understanding] --> A2[2 Evidence<br/>Discovery] --> A3[3 GitHub<br/>Analysis] --> A4[4 Hackathon<br/>Analysis] --> A5[5 Visual Portfolio<br/>Gemma vision] --> A6[6 Passion<br/>Detection] --> A7[7 Similarity<br/>vector search] --> A8[8 Ranking] --> A9[9 Storytelling] --> A10[10 Recommendation<br/>Video]
  end

  API --> P
  SRC[GitHub · Dev.to · HN · Devpost · Kaggle · blogs] --> A2
  P --> GEMMA[Gemma 4 31B · Ollama on AMD MI300X<br/>text + vision]
  A7 --> EMB[all-minilm embeddings · same MI300X<br/>384-dim]
  EMB --> DB[(Google Cloud SQL · PostgreSQL + pgvector)]
  A7 --> DB
  A10 --> TTS[Google Cloud TTS · Studio voice]
  A10 --> VID[ffmpeg → MP4 + timed captions]
  P --> LF[Langfuse · tracing]
```

The **backend runs on the droplet next to the GPU**, so it reaches Ollama over
`localhost` — there is no SSH tunnel, and nothing depends on a laptop.
See [docs/DEPLOY.md](docs/DEPLOY.md).

---

## The tech actually used

| What | Where | Notes |
|---|---|---|
| **Gemma 4 31B** (`gemma4:31b`) | Ollama on the **AMD Instinct MI300X** | Reasoning **and** vision — one model does both |
| **AMD GPU embeddings** | `all-minilm` via Ollama on the **same MI300X** | 384-dim, feeds pgvector |
| **Google Cloud SQL (PostgreSQL + pgvector)** | GCP | Evidence, scores, embeddings, vector search — and whole analyses, so a shared link survives a restart |
| **Google Cloud Text-to-Speech** | GCP | `en-US-Studio-O` — the video's narrator |
| **Google Maps + Geocoding** | GCP | Candidate map; free-text location → city / state / country |
| **GitHub REST API** | — | Discovery, profile enrichment, and candidate *search* for Free Discovery |
| **LangGraph** | droplet | The 10-agent pipeline |
| **FastAPI + SSE** | droplet (systemd + Caddy TLS) | API and live progress |
| **Next.js / OpenUI** | **Vercel** | Recruiter dashboard |
| **Langfuse** | — | Traces every agent span and Gemma call |
| **ffmpeg + Pillow** | droplet | Renders the recommendation video |

### Deliberately *not* used — so nobody is misled

- **Veo** — the Gemini API returns `429` (no Veo quota on the free tier). The video
  is therefore the **ffmpeg narrated slideshow**, not generated footage.
- **Bright Data** — the client exists
  ([brightdata_client.py](integrations/scrapers/brightdata_client.py)), but no Web
  Unlocker zone is provisioned on the account, so LinkedIn/Medium unblocking is
  **not active**. Every other source is read directly.
- **sentence-transformers** — superseded by GPU embeddings on the MI300X.

---

## What it does

Two ways in:

- **🔍 Free Discovery** — you provide **nothing** about people. The app searches
  GitHub from your mission alone, finds builders who never applied, and
  investigates them.
- **📋 Applicants** — only a **GitHub handle** is required. Name and links are
  optional; the app auto-discovers the rest (Dev.to, HN, Devpost, Kaggle, personal
  site, Medium) from the GitHub profile.

Then:

1. Evidence is discovered across every public source, and **every item keeps its URL**.
2. **Gemma vision** reads architecture diagrams and product screenshots (photos of
   people are filtered out).
3. Passion, similarity (tag overlap + **pgvector** search over MI300X embeddings)
   and a transparent weighted score rank the candidates.
4. **LinkedIn is required to be selected** — the shortlist is people you can
   actually contact. A **map** shows where they are.
5. A **narrated recommendation video** is rendered and captioned for **two
   audiences** — a *technical hiring manager* and an *HR recruiter* — with the
   captions and the narration script **synced to playback**.

---

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # point AMD_LLM_BASE_URL at Ollama on the MI300X

uvicorn backend.app.main:app --reload      # API on :8000
cd frontend && npm install && npm run dev  # UI on :3000
```

With no Gemma reachable every agent degrades to deterministic heuristics, so the
seeded demo still runs offline. `LIVE_MODE=false` (default) uses `demo_data/`.

---

## Anti-hallucination

Scores are deterministic and traceable; Gemma writes the prose and the image
captions, and must cite evidence by id / URL. The suite enforces:

- every ranked candidate has non-empty `evidence_ids`,
- every referenced id exists in the discovered evidence,
- every narrative project maps to a real evidence id **and** URL,
- no evidence lacks a source URL.

```bash
pytest -q        # 18 tests, incl. tests/test_no_hallucination.py
```

---

More: [docs/DEPLOY.md](docs/DEPLOY.md) · [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · [docs/AMD_SUBMISSION.md](docs/AMD_SUBMISSION.md)
