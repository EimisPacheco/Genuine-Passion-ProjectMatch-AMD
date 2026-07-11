"""Generate a recommendation video for an analysis's Top-3 candidates.

Each scene = Veo 3 text-to-video b-roll matched to the candidate's domain, with the
explanation (name, why-they-fit, Code/Design/Match scores) burned in by ffmpeg.
Run the backend first; usage: python scripts/make_reco_video.py [analysis_id]
"""
from __future__ import annotations

import os
import sys
import time
import textwrap
import tempfile

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
from video import veo_video as veo  # noqa: E402

BASE = os.environ.get("RECO_API", "http://localhost:8000")
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "video", "out")
os.makedirs(OUT_DIR, exist_ok=True)


def _pct(x):
    return f"{round((x or 0) * 100)}%"


def get_topn(analysis_id=None):
    if not analysis_id:
        analysis_id = requests.post(f"{BASE}/api/analyses", json={"use_demo": True, "top_n": 3}, timeout=30).json()["analysis_id"]
    for _ in range(60):
        s = requests.get(f"{BASE}/api/analyses/{analysis_id}", timeout=15).json()
        if s.get("status") in ("done", "error"):
            break
        time.sleep(2)
    project = (s.get("company_project") or {}).get("title", "the target project")
    cands = requests.get(f"{BASE}/api/analyses/{analysis_id}/candidates", timeout=15).json()["candidates"]
    return project, cands[:3]


def scene_prompt(c):
    return (
        f"{c['headline']}. Cinematic dark high-tech visualization, glowing blue accents, "
        f"abstract data and code, smooth camera motion, professional, no text."
    )


def caption(c, project):
    import re
    why = (c.get("narrative") or {}).get("explanation") or c.get("headline", "")
    why = re.sub(r"\[[^\]]*\]", "", why)  # strip [ev_...] evidence-id citations
    why = " ".join(why.split())
    wrapped = textwrap.wrap(why, width=52)[:3]
    return [
        f"#{c['rank']}  {c['name']}",
        *wrapped,
        f"Match {_pct(c['overall_score'])}   Code {_pct(c.get('code_score'))}   Design {_pct(c.get('design_score'))}",
    ]


def main():
    analysis_id = sys.argv[1] if len(sys.argv) > 1 else None
    project, cands = get_topn(analysis_id)
    print(f"[reco] project: {project} | top-{len(cands)}: {[c['name'] for c in cands]}")

    scenes = [{
        "prompt": f"Cinematic dark futuristic title sequence, glowing circuit particles, professional recruiting intelligence, premium tech aesthetic, no text",
        "lines": ["Top 3 Candidates", project, "Multi-Agent Passion Intelligence · Gemma on the AMD MI300X"],
    }]
    for c in cands:
        scenes.append({"prompt": scene_prompt(c), "lines": caption(c, project)})

    # submit all scenes concurrently
    print(f"[reco] submitting {len(scenes)} scenes to Veo 3 ({veo.VEO_MODEL})...")
    for sc in scenes:
        sc["status"], sc["resp"] = veo.submit_scene(sc["prompt"], duration=5)

    # download + overlay each
    final_parts = []
    for i, sc in enumerate(scenes):
        raw = tempfile.mktemp(suffix=f"_raw{i}.mp4")
        veo.wait_and_download(sc["status"], sc["resp"], raw)
        out = tempfile.mktemp(suffix=f"_scene{i}.mp4")
        veo.overlay_text(raw, out, sc["lines"])
        final_parts.append(out)
        print(f"[reco] scene {i+1}/{len(scenes)} done")

    ts = int(time.time())
    final = os.path.join(OUT_DIR, f"recommendation_{ts}.mp4")
    veo.stitch(final_parts, final)
    size = os.path.getsize(final)
    print(f"[reco] DONE -> {final} ({size//1024} KB, {len(scenes)} scenes)")


if __name__ == "__main__":
    main()
