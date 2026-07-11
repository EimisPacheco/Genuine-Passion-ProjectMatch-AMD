"""Command-line entry point.

    python -m backend.app.cli migrate          # create Cloud SQL tables
    python -m backend.app.cli run --demo        # full pipeline on seeded data
    python -m backend.app.cli run --top-n 3

Runs the whole pipeline and prints the ranked Top N plus the video output path.
Runs with no keys (heuristic fallback); GCP Cloud SQL optional.
"""
from __future__ import annotations

import argparse
import sys

from integrations.scrapers import demo_loader


def _run(top_n: int) -> int:
    from backend.app.graph.pipeline import run_pipeline

    company = demo_loader.load_company_project()
    candidates = demo_loader.list_candidates()
    print(f"\n=== Genuine Passion ProjectMatch AI ===")
    print(f"Company project : {company['title']}")
    print(f"Candidates      : {', '.join(c['name'] for c in candidates)}")
    print(f"Top N           : {top_n}\n")

    final = run_pipeline(company, candidates, top_n=top_n)

    print("--- Ranked candidates ---")
    name_by_id = {c["id"]: c["name"] for c in candidates}
    for r in final["ranking"][:top_n]:
        print(
            f"#{r['rank']}  {name_by_id.get(r['candidate_id'], r['candidate_id']):<16} "
            f"overall={r['overall_score']:.2f}  "
            f"similarity={r['project_similarity']:.2f}  "
            f"passion={r['genuine_passion']:.2f}  "
            f"({r['recommendation']})"
        )

    narratives = final.get("narratives", {})
    for r in final["ranking"][:top_n]:
        nar = narratives.get(r["candidate_id"], {})
        if nar.get("explanation"):
            print(f"\n  {name_by_id.get(r['candidate_id'])}: {nar['explanation']}")

    vid = final.get("video_report", {})
    print("\n--- Video ---")
    print(f"MP4    : {vid.get('mp4_path') or '(ffmpeg not available — script/srt only)'}")
    print(f"SRT    : {vid.get('srt_path')}")
    print(f"Length : {vid.get('duration_seconds', 0):.0f}s")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="projectmatch")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate")
    run_p = sub.add_parser("run")
    run_p.add_argument("--demo", action="store_true", help="use seeded demo data")
    run_p.add_argument("--top-n", type=int, default=3)

    args = parser.parse_args(argv)
    if args.cmd == "migrate":
        from database.migrations import main as migrate

        migrate()
        return 0
    if args.cmd == "run":
        return _run(args.top_n)
    return 1


if __name__ == "__main__":
    sys.exit(main())
