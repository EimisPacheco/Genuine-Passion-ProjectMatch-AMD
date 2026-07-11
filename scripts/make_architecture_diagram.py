"""Regenerate the architecture infographics with Gemini 3 Pro Image.

The architecture infographic (docs/architecture_amd.png) — the multi-agent / speed-race view.

Both reflect the AMD GPU embeddings (Ollama all-minilm) + Bright Data (Web
Unlocker) stack. Requires GEMINI_API_KEY in the environment / .env.

Usage:
    python scripts/make_architecture_diagram.py            # regenerate docs/architecture_amd.png
"""
from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
MODEL = "gemini-3-pro-image"
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

STYLE = (
    "Clean, modern flat infographic, light lavender-to-white gradient background. "
    "Three large rounded-rectangle panels side by side, each a soft solid color with "
    "a darker small ALL-CAPS kicker label and a big bold panel title. Inside each "
    "panel are white rounded cards, each card with a thin monoline outline icon on the "
    "left, a bold card title, a one-line gray subtitle, and a small colored rounded "
    "pill tag in the top-right corner. Bold blue arrows connect the panels left to "
    "right with short labels above them, and a blue arrow loops along the bottom back "
    "to a small person icon. Crisp, legible sans-serif text, generous spacing, 16:9. "
    "Render ALL text exactly as written, spelled correctly, no extra or placeholder text."
)

MAIN = STYLE + """

Top centered italic gray title: "Multi-Agent Passion Intelligence — Gemma on the AMD MI300X. Colors = platform layer."

PANEL 1 (warm yellow), kicker "PANEL", title "1. Experience & Intake":
  - Card icon dashboard, tag "Next.js": title "Next.js Dashboard", subtitle "Investigate / Rankings / Speed Race / Video"
  - Card icon form, tag "App": title "Project & Candidate Intake", subtitle "handles + any links (LinkedIn, Medium)"

Arrow between panel 1 and 2 labeled "Project + Candidates".

PANEL 2 (medium blue), kicker "PANEL", title "2. Multi-Agent Investigation":
  - Card icon globe, tag "Bright Data": title "Evidence Discovery", subtitle "GitHub, Dev.to, Hacker News, Devpost, Kaggle"
  - Card icon network graph, tag "LangGraph": title "10-Agent LangGraph Pipeline", subtitle "understand -> discover -> analyze -> rank -> story"
  - Card icon eye, tag "Gemma": title "Visual Portfolio (vision)", subtitle "diagrams + screenshots read by Gemma vision"
  - Card icon lightning bolt, tag "Race": title "Speed Race", subtitle "Gemma on AMD vs GPU baseline, live tokens/sec"

Arrow between panel 2 and 3 labeled "Prompts + Embeddings".

PANEL 3 (coral orange), kicker "PANEL", title "3. Models & Data":
  - Card icon chip, tag "AMD": title "Gemma on AMD MI300X", subtitle "text + vision, thinking mode"
  - Card icon sparkles, tag "Google": title "Gemini (GPU baseline)", subtitle "race comparison only"
  - Card icon GPU database, tag "AMD": title "GPU Embeddings + Vector Search", subtitle "all-minilm on AMD + Cloud SQL pgvector"
  - Card icon video player, tag "Veo 3": title "Recommendation Video", subtitle "Veo 3 text-to-video + narration"

Bottom blue arrow labeled "Ranked candidates + evidence + video" pointing to a person icon labeled "Recruiter / Founder".
"""



DIAGRAMS = {
    "main": ("docs/architecture_amd.png", MAIN),
}


def _load_key() -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        env = ROOT / ".env"
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("GEMINI_API_KEY="):
                    key = line.split("=", 1)[1].strip()
                    break
    if not key:
        sys.exit("GEMINI_API_KEY not set (env or .env)")
    return key


def generate(name: str, key: str) -> None:
    rel, prompt = DIAGRAMS[name]
    out = ROOT / rel
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {"aspectRatio": "16:9"},
        },
    }
    print(f"[{name}] generating -> {rel} ...")
    resp = httpx.post(URL, params={"key": key}, json=body, timeout=180)
    resp.raise_for_status()
    data = resp.json()
    parts = data["candidates"][0]["content"]["parts"]
    for part in parts:
        inline = part.get("inlineData") or part.get("inline_data")
        if inline and inline.get("data"):
            out.write_bytes(base64.b64decode(inline["data"]))
            print(f"[{name}] saved {out} ({out.stat().st_size // 1024} KB)")
            return
    sys.exit(f"[{name}] no image in response: {data}")


def main() -> None:
    key = _load_key()
    which = sys.argv[1:] or ["main"]
    for name in which:
        if name not in DIAGRAMS:
            sys.exit(f"unknown diagram '{name}' (choose from {list(DIAGRAMS)})")
        generate(name, key)


if __name__ == "__main__":
    main()
