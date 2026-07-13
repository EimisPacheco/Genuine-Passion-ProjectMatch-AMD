# AMD Developer Hackathon: ACT II — Submission

**Project:** Multi-Agent Passion Intelligence
**Track:** 3 — Unicorn (build your startup)
**Also entering:** Best Use of Gemma Models

A swarm of **Gemma** agents reads a person's real public work (GitHub, hackathons,
Kaggle, portfolios — and their *images*) to find who is genuinely built for a
project, then ranks candidates with cited evidence and a narrated video. For ACT II
the whole thing runs on **AMD**: Gemma inference via **Ollama on the AMD MI300X**, and
embeddings (`all-minilm`) served by **Ollama on the same MI300X** — all on **ROCm**.

![AMD architecture](architecture_amd.png)

## How we use the AMD stack

| Requirement | How we meet it |
|---|---|
| **Gemma on AMD** | The `amd` provider ([backend/app/llm/providers/](../backend/app/llm/providers/__init__.py)) talks to **Ollama** running on the **AMD MI300X** over its OpenAI-compatible API. `LLM_PROVIDER=amd` routes the entire 10-agent swarm — reasoning on `gemma4:31b` (thinking mode) and vision on `gemma3:12b` — through AMD-hosted Gemma. |
| **AMD Instinct MI300X + ROCm (AMD GPUs)** | Ollama runs on the MI300X using **ROCm** as the GPU compute layer. The same Ollama instance serves the `all-minilm` embedding model (384-dim); those vectors feed Google Cloud SQL `pgvector` similarity search. Set `OLLAMA_EMBEDDINGS_URL` / `OLLAMA_EMBEDDINGS_MODEL` and the backend uses it. |
| **Gemma** | Gemma is the core reasoning + vision model across all 10 agents; on AMD it is served by Ollama on the MI300X. |
| **Containerized submission** | Backend ships as a Docker image ([Dockerfile](../Dockerfile)); Gemma and the embedding model are served by Ollama on the MI300X pod and reached over an SSH tunnel. |

## What makes it a Unicorn-track product

- **Real product, not a benchmark run.** Recruiters/founders paste a project + a few
  candidates and get an evidence-cited shortlist with a recommendation video — every
  claim links to a real URL.
- **Multi-agent + multimodal.** Ten specialized LangGraph agents; a Visual Portfolio
  agent reads architecture diagrams and screenshots with Gemma vision.
- **Three modalities, one GPU.** Reasoning, vision *and* embeddings all run on the
  **AMD Instinct MI300X** via Ollama/ROCm — verified with `rocm-smi` and `ollama ps`
  (gemma4:31b, 100% GPU-resident). Track 3 does not score speed, so there is no
  benchmark showcase.
- **Genuinely adaptive.** Tested with real builders across multiple domains against
  different projects; the right specialist tops their own project every time.

## Run it on AMD

```bash
# 1. On the AMD MI300X pod: Ollama (ROCm) serves Gemma + embeddings
ollama serve
ollama pull gemma4:31b      # reasoning (thinking mode)
ollama pull gemma3:12b      # vision
ollama pull all-minilm      # embeddings (384-dim)
# expose Ollama (:11434) to your laptop over an SSH tunnel

# 2. Point the backend at AMD-hosted Gemma + embeddings
#    .env:  LLM_PROVIDER=amd
#           AMD_LLM_BASE_URL=http://localhost:11434/v1
#           AMD_LLM_MODEL=gemma4:31b
#           AMD_LLM_VISION_MODEL=gemma3:12b
#           OLLAMA_EMBEDDINGS_URL=http://localhost:11434
#           OLLAMA_EMBEDDINGS_MODEL=all-minilm

# 3. Backend (containerized)
docker build -t passion-backend .
docker run --rm -p 8080:8080 --env-file .env passion-backend
```

See [docs/AMD_RUNBOOK.md](AMD_RUNBOOK.md) for the AMD MI300X setup and the main
[README](../README.md) for the full architecture.
