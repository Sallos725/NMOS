"""Real-model tier for `extract-v10` (ADR 0028; docs/perf/extract-v10.md).

Runs the sidecar's own `extract-v10` prompt and validation on short Korean scenes written for this
evaluation, several times each, against one OpenAI-compatible endpoint:

- settled speech: an agreement to speak informally, a form of address asked for and accepted, and a
  decided change back must give a valid, narrated, actual `addresses` for the right direction;
- controls: a reply that only slips into another speech level, a scene that continues speech settled
  earlier, and a routine scene must give no `addresses`;
- the `extract-v9` scenes (salience by change, unnamed characters and reveals) are re-run with the
  `extract-v10` prompt for their bars (`tools/eval_v9_model.py`).

The scenes are synthetic test data, not a user's chat.

    cd apps/sidecar && uv run python ../../tools/eval_v10_model.py \\
        --url http://127.0.0.1:11434/v1 --model gemma4:31b-cloud --runs 3 \\
        --out ../../fixtures/model/v10/2026-09-26-gemma4-31b
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_extraction_model import call, norm  # noqa: E402
from eval_phase8_model import Scene, hint  # noqa: E402
from eval_v9_model import SCENES as V9_SCENES  # noqa: E402

from nmos_sidecar.extraction import SYSTEM_PROMPT, build_prompt, normalize  # noqa: E402
from nmos_sidecar.generations import fingerprint  # noqa: E402
from nmos_sidecar.llm import parse_json_object  # noqa: E402
from nmos_sidecar.predicates import registry_prompt  # noqa: E402

U, C, CHAR = "user", "char", "character"


def addresses_of(items) -> list[dict[str, Any]]:
    return [a for a in items if a["predicate"] == "addresses"]


def describe(items) -> str:
    return str([(a["subject"], a.get("object"), a.get("value"), a["status"], a.get("source"), a.get("modality"))
                for a in addresses_of(items)])


def settles(subject: str, obj: str, *words: str):
    """A valid, narrated, actual `addresses` from `subject` to `obj` whose value has one of `words`."""
    def check(items, scene):
        ok = any(norm(a["subject"]) == norm(subject) and norm(a.get("object")) == norm(obj)
                 and a["status"] == "valid" and a.get("source") == "narration" and a.get("modality") == "actual"
                 and any(w in (a.get("value") or "") for w in words) for a in addresses_of(items))
        return ok, describe(items)
    return check


def none_valid(items, scene):
    return not any(a["status"] == "valid" for a in addresses_of(items)), describe(items)


AGREED = [("", U, "유이, 이제 말 편하게 해도 돼."),
          ("", C, '유이는 눈을 동그랗게 떴다가 작게 웃었다. "……응. 그럼 카이토도 나한테 존댓말 하지 마." 그날부터 둘은 '
                  '서로에게 말을 놓았다.')]

SCENES: list[Scene] = [
    Scene("settled: agree informally (유이 → 카이토)", "settled", target=AGREED,
          hints=hint(("유이", CHAR), ("카이토", CHAR)), check=settles("유이", "카이토", "반말", "말을 놓", "편하게")),
    Scene("settled: agree informally (카이토 → 유이)", "settled", target=AGREED,
          hints=hint(("유이", CHAR), ("카이토", CHAR)), check=settles("카이토", "유이", "반말", "말을 놓", "편하게")),
    Scene("settled: form of address accepted", "settled",
          target=[("", U, "레온은 하나를 보며 웃었다."),
                  ("", C, '하나는 머뭇거리다가 레온의 소매를 잡았다. "……오빠. 이렇게 불러도 돼?" 레온이 "그래, 그렇게 '
                          '불러." 하고 머리를 쓰다듬자, 하나는 그 뒤로 레온을 오빠라고 불렀다.')],
          hints=hint(("하나", CHAR), ("레온", CHAR)), check=settles("하나", "레온", "오빠")),
    Scene("settled: change back decided", "settled",
          context=[AGREED],
          target=[("", U, "카이토가 유이의 비밀을 다른 사람에게 말해 버렸다."),
                  ("", C, '유이는 한참 말이 없다가 고개를 들었다. "……앞으로는 존댓말 쓸게요, 카이토 씨. 그게 맞는 것 '
                          '같아요." 카이토는 아무 말도 하지 못했다.')],
          hints=hint(("유이", CHAR), ("카이토", CHAR)), check=settles("유이", "카이토", "존댓말", "카이토 씨")),
    Scene("control: slip into formal speech", "control",
          context=[AGREED],
          target=[("", U, "카이토는 유이에게 우산을 건넸다."),
                  ("", C, '유이는 우산을 받아 들었다. "고마워요. 내일 돌려드릴게요." 빗소리가 창을 두드렸다.')],
          hints=hint(("유이", CHAR), ("카이토", CHAR)), check=none_valid),
    Scene("control: speech settled earlier continues", "control",
          context=[AGREED],
          target=[("", U, "같이 저녁 먹을래?"),
                  ("", C, '유이가 고개를 끄덕였다. "응, 좋아. 카이토가 사는 거지?" 둘은 시장 쪽으로 걸었다.')],
          hints=hint(("유이", CHAR), ("카이토", CHAR)), check=none_valid),
    Scene("control: routine", "control",
          target=[("", U, "설거지는 내가 할게."),
                  ("", C, "하나가 그릇을 헹구는 동안 레온은 빨래를 걷어 개었다. 부엌에는 물소리만 났다.")],
          hints=hint(("하나", CHAR), ("레온", CHAR)), check=none_valid),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--out", required=True)
    ap.add_argument("--timeout", type=float, default=180)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    system = SYSTEM_PROMPT.format(registry=registry_prompt())
    jobs = [(variant, scene, run, build_prompt(scene.ctx(), scene.hints, scene.listed()))
            for variant, scenes in (("v10", SCENES), ("v10-v9scenes", V9_SCENES))
            for scene in scenes for run in range(args.runs)]

    def work(job):
        variant, scene, run, user = job
        reply = call(args.url, args.model, system, user, args.timeout)
        record = {"scene": scene.name, "category": scene.category, "variant": variant, "run": run,
                  "system_fingerprint": fingerprint(system), "user": user, **reply}
        if not reply.get("error"):
            parsed = parse_json_object(reply["text"]) if reply["text"] else {}
            items = parsed.get("assertions") if isinstance(parsed.get("assertions"), list) else []
            record["assertions"] = normalize(items, "\n".join(x for _, _, x in scene.target), scene.hints)
            ok, detail = scene.check(record["assertions"], scene)
            record["check"] = {"pass": ok, "detail": detail}
        return record

    with ThreadPoolExecutor(args.workers) as pool:
        records = list(pool.map(work, jobs))
    with (out / "runs.jsonl").open("w") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False, default=list) + "\n")
    scenes: dict[str, dict[str, Any]] = {}
    for r in records:
        s = scenes.setdefault(f"{r['variant']} {r['scene']}", {"category": r["category"], "pass": 0, "runs": 0,
                                                              "details": []})
        s["runs"] += 1
        if "check" in r:
            s["pass"] += r["check"]["pass"]
            s["details"].append(r["check"]["detail"])
    summary = {"model": args.model, "url": args.url, "runs": args.runs, "calls": len(records),
               "errors": [f"{r['variant']} {r['scene']}#{r['run']}: {r['error']}" for r in records if r.get("error")],
               "bars": {k: f"{s['pass']}/{s['runs']}" for k, s in scenes.items()}, "scenes": scenes}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=list) + "\n")
    print(json.dumps(summary["bars"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
