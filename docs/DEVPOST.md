# Multi-Agent Passion Intelligence

*A multi-agent system that reads people's real public work to find who's genuinely
built for a project — powered by the **AMD MI300X** for GPU inference (Gemma via
Ollama in thinking mode; all-minilm embeddings on the same GPU) and **Bright
Data** for the web data that makes it possible.*

## Inspiration
Resumes describe what people *say* they can do. But a person's side projects reveal
what they *can't stop building*. I kept noticing that the most passionate engineers
I admired had years of public evidence — repos, hackathon projects, Kaggle
notebooks, write-ups — that no resume screener ever looks at. The problem is that
this evidence is (a) spread across the messy, bot-protected open web, and (b)
useless unless you can turn it into vectors and reason over it at scale. That's
exactly where **Bright Data** and the **AMD MI300X** come in: one gets me the data,
the other runs the model.

## What it does
I give it a project (the role you're hiring for) and a few candidates. A swarm of
agents then investigates each person's real public work — across **GitHub, Dev.to,
Hacker News, Devpost, Kaggle**, plus **LinkedIn, Medium, and lablab** unblocked
through **Bright Data Web Unlocker** — and even *reads their images* (architecture
diagrams and app screenshots) with vision. Every candidate's evidence is embedded on
the **AMD MI300X** (`all-minilm` via Ollama, 384-dim), matched to the project with
**Cloud SQL pgvector** similarity search, scored for genuine passion / Code / Design fit,
ranked with cited evidence, and turned into a narrated recommendation video.

## How I built it
- **AMD MI300X — GPU inference.** Candidate and project text are
  embedded (`all-minilm`, 384-dim) by **Ollama on the AMD MI300X** ([amd/](../amd/)).
  The backend calls it live; the returned
  vectors land in **Google Cloud SQL `pgvector`** and drive the candidate-to-project match. The
  same GPU also serves **Gemma** (thinking mode) for the language and vision work, so
  the whole swarm runs on AMD hardware.
- **Bright Data — the open web, unblocked.** LinkedIn, Medium, and lablab all block
  plain scraping (auth walls, Cloudflare). I route those through **Bright Data Web
  Unlocker**, which returns the rendered page so the agents can extract real
  evidence. The free, well-behaved sources (GitHub, Dev.to, Hacker News, Devpost,
  Kaggle) are queried directly; every candidate is checked across *all* of them, and
  empty sources simply return nothing.
- **Agents:** a 10-node **LangGraph** pipeline (understanding → discovery → GitHub /
  hackathon / visual analysis → passion → similarity → ranking → storytelling →
  video), exposed through **FastAPI** with live **SSE** progress.
- **Multimodal + reasoning:** **Gemma on the AMD MI300X** (via Ollama, thinking mode)
  does the language and
  vision; a Visual Portfolio agent feeds real diagrams/screenshots to the model and
  folds the signal into the scores.
- **Data:** **Google Cloud SQL for PostgreSQL + pgvector** stores evidence, scores, and the
  AMD-generated embeddings, and runs the vector similarity search inside the database.
- **Front-end:** **Next.js** dashboard on **Vercel**; **Veo 3** (Veo 3.1 via the Gemini API)
  for the cinematic recommendation video.

## Challenges I ran into
- **Bright Data zones & permissions.** My first token had no zones and couldn't
  create one via API, so the unblocker returned "zone not found." I learned the Web
  Unlocker needs a named zone, and wired the client to take the zone + token from
  config so it just works once the zone exists.
- **Thinking-mode Gemma's answer field.** In thinking mode Gemma returns its answer
  in a separate reasoning field, so the provider layer has to salvage it (and budget a
  larger token allowance) rather than reading the top-level content — otherwise the
  visible response comes back empty.
- **Reasoning at scale.** I run a *swarm* of inferences per candidate, so reasoning
  quality is the product — which is why both the model and the embeddings run on the
  AMD MI300X (Gemma via Ollama, thinking mode) instead of a laptop CPU.

## Accomplishments that I'm proud of
- The **AMD MI300X** serving both **Gemma** (thinking mode) and live **all-minilm**
  embedding requests on one GPU, so the whole swarm runs on AMD hardware.
- **Bright Data Web Unlocker** turning the bot-walled parts of the web (LinkedIn,
  Medium, lablab) into usable evidence — the agents read sources a plain scraper
  can't touch.
- An end-to-end loop: Bright Data → agents → **AMD GPU embeddings** → **Cloud SQL pgvector**
  match → evidence-cited shortlist, where every claim links to a real URL.
- It genuinely *adapts*: I tested 5 real builders across 5 domains against 3
  different projects, and the right specialist topped their own project every time.

## What I learned
- **The AMD MI300X handles the whole swarm on one GPU.** Serving Gemma (thinking
  mode) and the all-minilm embeddings on the same MI300X keeps language, vision, and
  vector work on a single piece of AMD hardware.
- **Bright Data makes the open web actually addressable.** The hardest, most
  valuable evidence lives behind anti-bot walls; an unblocker is the difference
  between "we support that source" and "we actually read it."
- A clean abstraction (one provider layer, one store facade, one embeddings
  chokepoint) is what let me drop in the AMD MI300X and a Bright Data backend
  late in the build without touching the agents.

## What's next for Multi-Agent Passion Intelligence
- **Deeper AMD pipeline:** a preprocessing stage feeding the MI300X embedding step,
  plus a GPU cross-encoder reranker — pushing more of the ranking work onto the
  AMD GPU.
- **More Bright Data:** dedicated structured datasets (LinkedIn, etc.) for richer,
  cleaner evidence than HTML extraction.
- "Find me the 10 people on the internet obsessed with X" — open-ended discovery,
  co-founder/team matching, and a feedback loop that learns which signals predicted
  great hires.
