# Deployment — public, permanent, no SSH tunnel

## Why there is no tunnel any more

Ollama has **no authentication**, so it is meant to be reached only from the machine
it runs on. While the backend lived on a laptop and the GPU lived on the droplet, an
SSH tunnel was the bridge between them — and it died whenever the laptop slept or the
session ended. That architecture cannot be published.

The fix is to remove the split: **the backend now runs on the droplet, next to the
GPU**, and talks to Ollama over `localhost`. No tunnel exists, and nothing depends on
a laptop.

```
Browser → Vercel (Next.js) → https://<host>/api/*  →  Caddy (TLS)
                                                        └→ FastAPI backend  (127.0.0.1:8000)
                                                             ├→ Ollama / Gemma  (127.0.0.1:11434)
                                                             └→ Cloud SQL (pgvector)
```

## Live endpoint

| | |
|---|---|
| Backend | `https://129-212-179-131.sslip.io` |
| Health | `https://129-212-179-131.sslip.io/api/health` |

`sslip.io` resolves `129-212-179-131.sslip.io` → `129.212.179.131`, so Caddy can get a
free Let's Encrypt certificate without buying a domain. HTTPS is required: a Vercel
(HTTPS) front-end may not call a plain-HTTP backend.

## Front-end (Vercel)

Set one environment variable and redeploy:

```
NEXT_PUBLIC_API_BASE=https://129-212-179-131.sslip.io
```

It drives both the `/api/*` rewrite in `frontend/next.config.mjs` and the SSE
`EventSource` in `frontend/lib/api.ts`.

## What runs on the droplet (Ubuntu 24.04, MI300X)

| Unit | Purpose | Survives reboot |
|---|---|---|
| `ollama` (docker) | Gemma + embeddings on `127.0.0.1:11434` | `--restart unless-stopped` |
| `projectmatch` (systemd) | FastAPI backend on `127.0.0.1:8000` | `systemctl enable` |
| `caddy` (systemd) | TLS termination + reverse proxy | `systemctl enable` |

Code lives in `/opt/projectmatch`. Secrets (`.env`, `gcp-sa-key.json`) are `chmod 600`
and are **never** committed.

### Operating it

```bash
ssh root@129.212.179.131
cd /opt/projectmatch && git pull && systemctl restart projectmatch   # deploy
systemctl status projectmatch                                        # state
tail -f /var/log/projectmatch.log                                    # logs
```

## Security notes

1. **Ollama is currently reachable on `0.0.0.0:11434`** — anyone who finds the IP can
   run inference on the GPU, unauthenticated, at your cost. The backend only needs
   `localhost`, so close the public port when convenient:
   ```bash
   ufw allow 22 && ufw allow 80 && ufw allow 443 && ufw deny 11434 && ufw --force enable
   ```
2. **The backend has no auth** — any visitor can start an analysis, and each one costs
   GPU time. Add rate limiting before sharing the link widely.
3. **Restrict the Google Maps key** to your Vercel domain (HTTP-referrer restriction);
   it is served to the browser by design.
4. Cloud SQL allows connections only from authorized networks — the droplet IP
   (`129.212.179.131/32`) is allowlisted.
