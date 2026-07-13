# AMD Developer Cloud runbook — Gemma + embeddings on an MI300X (Ollama)

Goal: run **Gemma via Ollama** and **`all-minilm` embeddings** (also via Ollama) on one
AMD Instinct MI300X pod (ROCm), expose Ollama over an SSH tunnel, and point the app at it
(`LLM_PROVIDER=amd`). MI300X has 192 GB, so `gemma4:31b` fits comfortably alongside the
`gemma3:12b` vision model and the tiny embedding model.

Environment: **AMD Developer Cloud** on-demand **1× MI300X** VM (SSH access), ~$100 /
~25 GPU-hours. Billing is **continuous (~$1.99/hr)** while the VM runs — **stop the
droplet when idle**. Topology: one Ollama instance on the VM serves Gemma **and**
embeddings on `:11434`; an SSH tunnel forwards `:11434` to your laptop / backend.

---

## Before the VM
**SSH keypair** — on your laptop: `ssh-keygen -t ed25519 -C amd-cloud -f ~/.ssh/amd_cloud`
(Enter for no passphrase). Upload the **public** key `~/.ssh/amd_cloud.pub` when launching
the VM. Never share the private key.

## Launch + connect
1. AMD Developer Cloud console → new GPU instance → **1× MI300X** → prefer a **ROCm**
   image → paste your SSH public key → launch.
2. `ssh -i ~/.ssh/amd_cloud <user>@<vm-public-ip>` (console shows the exact user/IP).

---

## Step 0 — recon (run first, paste me the output)
```bash
rocm-smi
which ollama tmux
```
Confirms the AMD GPU is visible and Ollama is available. (If Ollama isn't installed:
`curl -fsSL https://ollama.com/install.sh | sh` — it uses ROCm on the MI300X.)

---

## Step 1 — serve Gemma + embeddings with Ollama (OpenAI-compatible, port 11434)
Use tmux so it keeps running: `tmux new -s ollama`
```bash
ollama serve                 # listens on :11434 (Ctrl-b d to detach)
```
Then pull the models (first pull downloads weights):
```bash
ollama pull gemma4:31b       # reasoning (thinking mode)
ollama pull gemma3:12b       # vision
ollama pull all-minilm       # embeddings (384-dim)
```
Verify:
```bash
curl -s http://localhost:11434/v1/models
curl -s http://localhost:11434/v1/chat/completions -H "Content-Type: application/json" \
  -d '{"model":"gemma4:31b","messages":[{"role":"user","content":"say OK"}],"max_tokens":8}'
curl -s http://localhost:11434/api/embeddings -H "Content-Type: application/json" \
  -d '{"model":"all-minilm","prompt":"hello"}'
```

## Step 2 — expose Ollama over an SSH tunnel
From your laptop (or wherever the backend runs), forward the remote `:11434` to local:
```bash
ssh -i ~/.ssh/amd_cloud -N -L 11434:localhost:11434 <user>@<vm-public-ip>
```
Leave this running; `http://localhost:11434` now reaches Ollama on the MI300X.

## Step 3 — point the app at AMD-hosted Gemma + embeddings
Set in `.env`:
```
LLM_PROVIDER=amd
AMD_LLM_BASE_URL=http://localhost:11434/v1
AMD_LLM_MODEL=gemma4:31b
AMD_LLM_VISION_MODEL=gemma3:12b
OLLAMA_EMBEDDINGS_URL=http://localhost:11434
OLLAMA_EMBEDDINGS_MODEL=all-minilm
```
Then run the pipeline end-to-end to confirm Gemma (reasoning + vision) and embeddings are
all executing on the AMD MI300X.

---

## When done (stop the credit meter)
```bash
# in the ollama tmux session: Ctrl-c
```
Then **stop/terminate the MI300X instance** in the AMD Developer Cloud console — billing
is per GPU-hour, so an idle running pod still costs.
