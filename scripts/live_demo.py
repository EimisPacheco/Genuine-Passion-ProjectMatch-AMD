"""LIVE demo: analyze REAL GitHub users with REAL repositories (no seeded data).

Usage:
    python scripts/live_demo.py                      # default: real AI-agent devs
    python scripts/live_demo.py octocat torvalds ...  # your own list of GitHub handles

Forces LIVE_MODE=true so Evidence Discovery scrapes live GitHub via the REST API
(needs GITHUB_TOKEN in .env for good rate limits). Prints the real repositories
discovered (with clickable URLs) and the ranking on real data.
"""
import os
import sys

os.environ["LIVE_MODE"] = "true"

from dotenv import load_dotenv  # noqa: E402

load_dotenv()
from backend.app.config import get_settings  # noqa: E402

get_settings.cache_clear()
import backend.app.config as cfg  # noqa: E402

cfg.settings = get_settings()
for m in ["integrations.scrapers.dispatch", "integrations.scrapers.github_api",
          "backend.app.store"]:
    __import__(m)
    setattr(sys.modules[m], "settings", cfg.settings)

from backend.app.graph.pipeline import run_pipeline  # noqa: E402

DEFAULT_HANDLES = ["karpathy", "yoheinakajima", "hwchase17"]

COMPANY = {
    "title": "Build an Autonomous AI Agent Framework",
    "description": "An open-source framework for building autonomous LLM agents that plan, "
                   "use tools, and self-improve, with strong developer ergonomics.",
    "business_problem": "Developers need a robust framework to build autonomous, tool-using LLM agents.",
    "expected_technologies": ["Python", "LLM", "agents", "transformers", "PyTorch"],
    "expected_features": ["autonomous agents", "tool use", "planning", "LLM orchestration"],
    "desired_candidates": 3,
}


def main():
    handles = sys.argv[1:] or DEFAULT_HANDLES
    candidates = [
        {"id": f"gh_{h}", "name": h, "github_handle": h, "sources": [f"https://github.com/{h}"]}
        for h in handles
    ]
    print(f"LIVE_MODE={cfg.settings.live_mode}  github_token={'set' if cfg.settings.github_token else 'MISSING'}")
    print(f"Analyzing real GitHub users: {', '.join(handles)}\n")

    final = run_pipeline(COMPANY, candidates, top_n=len(handles))

    print("==== REAL EVIDENCE DISCOVERED (live from GitHub) ====")
    for cid, items in final["evidence"].items():
        name = next(c["name"] for c in candidates if c["id"] == cid)
        print(f"\n{name} — {len(items)} repositories:")
        for e in items[:8]:
            print(f"   • {e['title'][:55]:55} {e['url']}")

    print("\n==== RANKING ON REAL DATA ====")
    name_by = {c["id"]: c["name"] for c in candidates}
    for r in final["ranking"]:
        print(f"  #{r['rank']} {name_by[r['candidate_id']]:<16} overall={r['overall_score']:.2f} "
              f"sim={r['project_similarity']:.2f} passion={r['genuine_passion']:.2f}")
    vid = final.get("video_report", {})
    print(f"\nExecutive video: {vid.get('mp4_path') or '(srt only)'}")


if __name__ == "__main__":
    main()
