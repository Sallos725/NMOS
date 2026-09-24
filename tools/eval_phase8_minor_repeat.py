"""Phase 8 follow-up: repeat the Phase 7 minor-event scenes with extract-v7 and extract-v8.

The Phase 8 real-model tier found "minor: chores" at 1/3 with extract-v8 (two runs extracted no event
at all), against the Phase 7 bar of 2/3. This runs each minor scene N more times with both prompts, to
tell a regression from run-to-run variance. Synthetic scenes, test data only.

    cd apps/sidecar && uv run python ../../tools/eval_phase8_minor_repeat.py \\
        --url http://127.0.0.1:11434/v1 --model deepseek-v4.1-flash:cloud --runs 10 \\
        --out ../../fixtures/model/phase8/2026-09-24-deepseek-v4.1-flash/minor-repeat.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_extraction_model import call  # noqa: E402
from eval_phase7_model import SCENES as PHASE7_SCENES  # noqa: E402
from eval_phase8_model import v7_prompt  # noqa: E402

from nmos_sidecar.extraction import SYSTEM_PROMPT, build_prompt, normalize  # noqa: E402
from nmos_sidecar.llm import parse_json_object  # noqa: E402
from nmos_sidecar.predicates import registry_prompt  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    prompts = {"v7": v7_prompt(), "v8": SYSTEM_PROMPT.format(registry=registry_prompt())}
    scenes = [s for s in PHASE7_SCENES if s.category == "minor"]
    jobs = [(v, s, run) for s in scenes for v in prompts for run in range(args.runs)]

    def work(job):
        variant, scene, run = job
        reply = call(args.url, args.model, prompts[variant], build_prompt(scene.ctx(), scene.hints, scene.listed()), 180)
        items = (parse_json_object(reply["text"]) or {}).get("assertions") if reply.get("text") else []
        rows = normalize(items if isinstance(items, list) else [], "\n".join(x for _, _, x in scene.target), scene.hints)
        ok, detail = scene.check(rows, scene)
        return {"scene": scene.name, "variant": variant, "run": run, "pass": ok, "detail": detail,
                "error": reply.get("error"), "usage": reply.get("usage")}

    with ThreadPoolExecutor(args.workers) as pool:
        records = list(pool.map(work, jobs))
    Path(args.out).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
    for s in scenes:
        for v in prompts:
            rs = [r for r in records if r["scene"] == s.name and r["variant"] == v]
            empty = sum("events=[]" in r["detail"] for r in rs)
            print(f"{s.name} {v}: {sum(r['pass'] for r in rs)}/{len(rs)} pass, {empty} with no event")


if __name__ == "__main__":
    main()
