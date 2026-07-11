"""Narrated hiring-briefing video for an analysis's Top-3 candidates.

Structure: intro scene (what the video is + which project) -> per candidate two
scenes (summary with scores, then evidence). One consistent narrator voice
(macOS `say`) runs across the whole video; each scene's Veo 3 b-roll is timed to
its narration. Run the backend first.
Usage: python scripts/make_briefing_video.py [analysis_id]
"""
from __future__ import annotations

import os
import re
import sys
import time
import textwrap
import tempfile

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
from video import veo_video as fv  # noqa: E402  (Veo 3 text-to-video)

BASE = os.environ.get("RECO_API", "http://localhost:8000")
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "video", "out")
os.makedirs(OUT_DIR, exist_ok=True)


def _pct(x):
    return f"{round((x or 0) * 100)}%"


def _clean(t):
    return " ".join(re.sub(r"\[[^\]]*\]", "", t or "").split())


def get_data(analysis_id=None):
    if not analysis_id:
        analysis_id = requests.post(f"{BASE}/api/analyses", json={"use_demo": True, "top_n": 3}, timeout=30).json()["analysis_id"]
    for _ in range(60):
        s = requests.get(f"{BASE}/api/analyses/{analysis_id}", timeout=15).json()
        if s.get("status") in ("done", "error"):
            break
        time.sleep(2)
    project = (s.get("company_project") or {}).get("title", "the target project")
    cands = requests.get(f"{BASE}/api/analyses/{analysis_id}/candidates", timeout=15).json()["candidates"][:3]
    for c in cands:
        ev = requests.get(f"{BASE}/api/analyses/{analysis_id}/candidates/{c['candidate_id']}/evidence", timeout=15).json()
        c["evidence"] = ev.get("evidence", [])[:3]
    return project, cands


def build_scenes(project, cands):
    scenes = [{
        "prompt": "Cinematic dark futuristic title sequence, glowing blue circuit particles, premium professional tech, no text",
        "lines": ["Candidate Briefing", project, "Top 3 · analyzed by Gemma on the AMD MI300X"],
        "narration": (
            f"Welcome to the candidate briefing for the project: {project}. "
            f"Our multi-agent system, powered by Gemma running on AMD, analyzed each candidate's real public work "
            f"to surface the top three builders for this project. Let's meet them."
        ),
    }]
    for c in cands:
        fn = c["name"].split()[0]
        why = _clean((c.get("narrative") or {}).get("explanation") or c.get("headline", ""))
        why_short = why.split(". ")[0].rstrip(".") + "."  # one sentence for narration (keeps it concise)
        ev_titles = [_clean(e.get("title", "")) for e in c.get("evidence", []) if e.get("title")]
        # scene A — summary + scores
        scenes.append({
            "prompt": f"{c['headline']}. Cinematic dark high-tech visualization, glowing blue, smooth motion, no text",
            "lines": [
                f"#{c['rank']}  {c['name']}",
                *textwrap.wrap(why, width=52)[:2],
                f"Match {_pct(c['overall_score'])}   Project similarity {_pct(c['project_similarity'])}   Passion {_pct(c['genuine_passion'])}",
            ],
            "narration": (
                f"Number {c['rank']}: {c['name']}. {why_short} "
                f"A {_pct(c['overall_score'])} match, with project similarity {_pct(c['project_similarity'])}."
            ),
        })
        # scene B — evidence
        ev_say = " ".join(ev_titles[:3]) if ev_titles else "their public repositories and projects"
        scenes.append({
            "prompt": "Glowing code repositories, data structures and project files floating, cinematic dark blue, no text",
            "lines": [
                f"#{c['rank']}  {c['name']} — evidence",
                *[f"• {t[:48]}" for t in ev_titles[:3]],
                f"Code {_pct(c.get('code_score'))}    Design {_pct(c.get('design_score'))}",
            ],
            "narration": (
                f"The evidence behind {fn}: {ev_say}. "
                f"On engineering, a code score of {_pct(c.get('code_score'))} and design {_pct(c.get('design_score'))}."
            ),
        })
    return scenes


def main():
    analysis_id = sys.argv[1] if len(sys.argv) > 1 else None
    project, cands = get_data(analysis_id)
    print(f"[brief] project: {project} | top-3: {[c['name'] for c in cands]}")
    scenes = build_scenes(project, cands)
    print(f"[brief] {len(scenes)} scenes (intro + 2/candidate)")

    # 1) narrate all scenes (local, fast) -> audio + duration
    for i, sc in enumerate(scenes):
        sc["audio"] = fv.narrate(sc["narration"], tempfile.mktemp(suffix=f"_n{i}.aac"))
        sc["dur"] = fv.audio_duration(sc["audio"])
    print(f"[brief] narrated; total ~{sum(s['dur'] for s in scenes):.0f}s")

    # 2) submit Veo 3 b-roll per scene, duration matched to narration (5..12s)
    for sc in scenes:
        d = max(5, min(12, round(sc["dur"])))
        sc["status"], sc["resp"] = fv.submit_scene(sc["prompt"], duration=d)
    print("[brief] Veo 3 scenes submitted")

    # 3) download + compose (caption + loop-to-narration + voice)
    parts = []
    for i, sc in enumerate(scenes):
        raw = tempfile.mktemp(suffix=f"_b{i}.mp4")
        fv.wait_and_download(sc["status"], sc["resp"], raw)
        out = tempfile.mktemp(suffix=f"_s{i}.mp4")
        fv.compose_scene(raw, sc["lines"], sc["audio"], out)
        parts.append(out)
        print(f"[brief] scene {i+1}/{len(scenes)} composed ({sc['dur']:.1f}s)")

    ts = int(time.time())
    final = os.path.join(OUT_DIR, f"briefing_{ts}.mp4")
    fv.stitch_av(parts, final)
    print(f"[brief] DONE -> {final} ({os.path.getsize(final)//1024} KB, {len(scenes)} scenes)")


if __name__ == "__main__":
    main()
