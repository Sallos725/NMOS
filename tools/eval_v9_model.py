"""Real-model tier for `extract-v9` (ADRs 0024, 0025; docs/perf/extract-v9.md).

Runs the sidecar's own `extract-v9` prompt and validation on short Korean scenes written for this
evaluation, several times each, against one OpenAI-compatible endpoint:

- salience: turning points told in words (an admission, a change of speech level or form of address, a
  relationship allowed) and an incident others must deal with must get a `major` event; routine scenes
  must not;
- unnamed characters: a character shown without a name is named by a "?" description; a later turn that
  reveals who a listed description is gives a valid `also_called`; a turn that does not reveal it gives
  none.

The Phase 6, 7 and 8 scenes are re-run with `extract-v9` for their bars. The scenes are synthetic test
data, not a user's chat.

    cd apps/sidecar && uv run python ../../tools/eval_v9_model.py \\
        --url http://127.0.0.1:11434/v1 --model deepseek-v4.1-flash:cloud --runs 3 \\
        --out ../../fixtures/model/v9/2026-09-25-deepseek-v4.1-flash
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_extraction_model import ROOT, call, norm  # noqa: E402
from eval_phase6_model import SCENES as PHASE6_SCENES  # noqa: E402
from eval_phase7_model import SCENES as PHASE7_SCENES, events_of, salience_is  # noqa: E402
from eval_phase8_model import SCENES as PHASE8_SCENES, Scene, hint  # noqa: E402

from nmos_sidecar.entities import UNNAMED  # noqa: E402
from nmos_sidecar.extraction import SYSTEM_PROMPT, build_prompt, normalize  # noqa: E402
from nmos_sidecar.generations import fingerprint  # noqa: E402
from nmos_sidecar.llm import parse_json_object  # noqa: E402
from nmos_sidecar.predicates import registry_prompt  # noqa: E402

V8_COMMIT = "1340f61"  # v0.1.0-beta.16: the extract-v8 prompt and registry
U, C, CHAR = "user", "char", "character"
MASK = "?은빛 가면의 인물"


def no_major(items, scene):
    """Routine: any events, none labeled major."""
    events = events_of(items)
    return "major" not in [a.get("salience") for a in events], str([(a["subject"], a["value"], a.get("salience"))
                                                                     for a in events])


def unnamed_named(items, scene):
    """The nameless figure is written as a "?" description somewhere (subject, object or participant)."""
    names = [a["subject"] for a in items] + [a.get("object") or "" for a in items]
    names += [p["name"] for a in items for p in a.get("participants") or []]
    return any(n.startswith(UNNAMED) for n in names), str(sorted({n for n in names if n}))


def aliases(items) -> list[tuple[str, str, str]]:
    return [(a["subject"], a.get("value"), a["status"]) for a in items if a["predicate"] == "also_called"]


def reveals(name: str, description: str):
    def check(items, scene):
        want = {norm(name), norm(description)}
        return any({norm(s), norm(v)} == want and st == "valid" for s, v, st in aliases(items)), str(aliases(items))
    return check


def no_reveal(description: str):
    def check(items, scene):
        return not any(norm(description) in (norm(s), norm(v)) and st == "valid" for s, v, st in aliases(items)), \
            str(aliases(items))
    return check


SCENES: list[Scene] = [
    # --- turning points told in words, and incidents -------------------------------------------------
    Scene("major: admission", "major",
          context=[[("", U, "결계가 왜 무너졌는지 아무도 몰라?"),
                    ("", C, "마을 사람들은 사흘째 무너진 결계의 원인을 찾고 있었다.")]],
          target=[("", U, "서연이 할 말이 있대."),
                  ("", C, '서연은 한참 망설이다가 입을 열었다. "그 결계석, 사실 제가 건드렸어요. 그날 밤에요." 촌장의 '
                          '얼굴이 굳었다.')],
          hints=hint(("서연", CHAR), ("촌장", CHAR)), check=salience_is("major")),
    Scene("major: speech level", "major",
          target=[("", U, "유이, 이제 말 편하게 해도 돼."),
                  ("", C, '유이는 눈을 동그랗게 떴다가 작게 웃었다. "……응. 그럼 카이토도 나한테 존댓말 하지 마." 그날부터 '
                          '둘은 서로에게 말을 놓았다.')],
          hints=hint(("유이", CHAR), ("카이토", CHAR)), check=salience_is("major")),
    Scene("major: form of address", "major",
          target=[("", U, "레온은 하나를 보며 웃었다."),
                  ("", C, '하나는 머뭇거리다가 레온의 소매를 잡았다. "……오빠. 이렇게 불러도 돼?" 레온은 대답 대신 하나의 '
                          '머리를 쓰다듬었다.')],
          hints=hint(("하나", CHAR), ("레온", CHAR)), check=salience_is("major")),
    Scene("major: relationship allowed", "major",
          target=[("", U, "아버지, 저 미나랑 사귀어요."),
                  ("", C, '카이토의 아버지는 오래 침묵하다가 신문을 접었다. "……반대는 안 하마. 대신 미나를 울리면 '
                          '가만두지 않을 거다."')],
          hints=hint(("카이토", CHAR), ("미나", CHAR)), check=salience_is("major")),
    Scene("major: device explodes", "major",
          target=[("", U, "민호는 측정 수정구에 손을 얹었다."),
                  ("", C, "수정구가 눈부시게 빛나더니 쩍 금이 가며 산산조각 났다. 파편이 사방으로 튀었다. 감독관은 "
                          "굳은 얼굴로 기록지에 '측정 불가, 등급 판정 보류'라고 적었다.")],
          hints=hint(("민호", CHAR), ("감독관", CHAR)), check=salience_is("major")),
    # --- routine: no major event ----------------------------------------------------------------------
    Scene("routine: dinner", "routine",
          target=[("", U, "저녁 먹자."),
                  ("", C, "유이와 카이토는 식탁에 마주 앉아 감자 스튜를 나눠 먹었다. 카이토가 빵을 한 조각 더 건넸다.")],
          hints=hint(("유이", CHAR), ("카이토", CHAR)), check=no_major),
    Scene("routine: chores", "routine",
          target=[("", U, "설거지는 내가 할게."),
                  ("", C, "하나가 그릇을 헹구는 동안 레온은 빨래를 걷어 개었다. 부엌에는 물소리만 났다.")],
          hints=hint(("하나", CHAR), ("레온", CHAR)), check=no_major),
    Scene("routine: walk to market", "routine",
          target=[("", U, "시장에 가자."),
                  ("", C, "서연은 바구니를 들고 촌장과 함께 시장까지 걸어갔다. 가는 길에 사과를 몇 알 샀다.")],
          hints=hint(("서연", CHAR), ("촌장", CHAR)), check=no_major),
    # --- unnamed characters and reveals ---------------------------------------------------------------
    Scene("unnamed: first sight", "unnamed",
          target=[("", U, "누군가 지켜보는 것 같아."),
                  ("", C, "안개 낀 다리 위에서 은빛 가면을 쓴 누군가가 카이토를 가만히 내려다보고 있었다. 카이토가 "
                          "고개를 들자 그 인물은 망토를 휘날리며 사라졌다.")],
          hints=hint(("카이토", CHAR)), check=unnamed_named),
    Scene("unnamed: reveal", "reveal",
          context=[[("", U, "누군가 지켜보는 것 같아."),
                    ("", C, "안개 낀 다리 위에서 은빛 가면을 쓴 누군가가 카이토를 가만히 내려다보고 있었다.")]],
          target=[("", U, "다리 위의 그 사람을 쫓아간다."),
                  ("", C, "골목 끝에서 따라잡힌 인물이 천천히 은빛 가면을 벗었다. 드러난 얼굴은 세라였다. \"오랜만이야, "
                          "카이토.\"")],
          hints=hint(("카이토", CHAR), (MASK, CHAR)), check=reveals("세라", MASK)),
    Scene("unnamed: another person arrives", "no reveal",
          context=[[("", U, "누군가 지켜보는 것 같아."),
                    ("", C, "안개 낀 다리 위에서 은빛 가면을 쓴 누군가가 카이토를 가만히 내려다보고 있었다.")]],
          target=[("", U, "여관으로 돌아간다."),
                  ("", C, "여관 문이 열리고 리안이 들어왔다. 리안은 카이토 옆에 앉아 맥주를 주문했다. 다리 위의 가면 쓴 "
                          "인물이 누구였는지는 아무도 몰랐다.")],
          hints=hint(("카이토", CHAR), (MASK, CHAR)), check=no_reveal(MASK)),
    Scene("unnamed: unrelated scene", "no reveal",
          target=[("", U, "빵 굽자."), ("", C, "하나는 반죽을 치대 오븐에 넣었다. 부엌에 고소한 냄새가 퍼졌다.")],
          hints=hint(("하나", CHAR), (MASK, CHAR)), check=no_reveal(MASK)),
]


def v8_prompt() -> str:
    """The extract-v8 system prompt, formatted with the v8 registry, read from git history."""
    def source(path: str) -> str:
        return subprocess.run(["git", "-C", str(ROOT), "show", f"{V8_COMMIT}:{path}"], check=True,
                              capture_output=True, text=True).stdout
    ns: dict[str, Any] = {}
    exec(compile(source("apps/sidecar/src/nmos_sidecar/predicates.py").replace("from .entities import node\n",
                                                                                "node = lambda *a: a\n"),
                 "predicates_v8", "exec"), ns)
    tree = ast.parse(source("apps/sidecar/src/nmos_sidecar/extraction.py"))
    prompt = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                  and any(getattr(t, "id", None) == "SYSTEM_PROMPT" for t in n.targets))
    return prompt.format(registry=ns["registry_prompt"]())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--out", required=True)
    ap.add_argument("--timeout", type=float, default=180)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--v8", action="store_true", help="also run the v9 scenes with the extract-v8 prompt")
    ap.add_argument("--baseline", action="store_true",
                    help="run every scene set with the extract-v8 prompt only (the baseline for the Phase 6-8 bars)")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    system = SYSTEM_PROMPT.format(registry=registry_prompt())
    system_v8 = v8_prompt()

    jobs: list[tuple[str, Any, int, str, str]] = []
    sets = [("", SCENES), ("-phase6", PHASE6_SCENES), ("-phase7", PHASE7_SCENES), ("-phase8", PHASE8_SCENES)]
    if args.baseline:
        variants = [("v8" + suffix, scenes, system_v8) for suffix, scenes in sets]
    else:
        variants = [("v9" + suffix, scenes, system) for suffix, scenes in sets]
        if args.v8:
            variants.append(("v8", SCENES, system_v8))
    for variant, scenes, sys_prompt in variants:
        for scene in scenes:
            for run in range(args.runs):
                listed = scene.listed() if hasattr(scene, "listed") else []
                jobs.append((variant, scene, run, sys_prompt, build_prompt(scene.ctx(), scene.hints, listed)))
    for scene in (s for s in PHASE6_SCENES if s.category == "control" and not args.baseline):  # prompt tokens
        jobs.append(("v8-tokens", scene, 0, system_v8, build_prompt(scene.ctx(), scene.hints)))
        jobs.append(("v9-tokens", scene, 0, system, build_prompt(scene.ctx(), scene.hints)))

    def work(job):
        variant, scene, run, sys_prompt, user = job
        reply = call(args.url, args.model, sys_prompt, user, args.timeout)
        record = {"scene": scene.name, "category": scene.category, "variant": variant, "run": run,
                  "system_fingerprint": fingerprint(sys_prompt), "user": user, **reply}
        if not variant.endswith("-tokens") and not reply.get("error"):
            parsed = parse_json_object(reply["text"]) if reply["text"] else {}
            items = parsed.get("assertions") if isinstance(parsed.get("assertions"), list) else []
            turn_text = "\n".join(x for _, _, x in scene.target)
            record["assertions"] = normalize(items, turn_text, scene.hints)
            if scene.check:
                ok, detail = scene.check(record["assertions"], scene)
                record["check"] = {"pass": ok, "detail": detail}
        return record

    with ThreadPoolExecutor(args.workers) as pool:
        records = list(pool.map(work, jobs))
    with (out / "runs.jsonl").open("w") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False, default=list) + "\n")
    summary = summarize(records, args)
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=list) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=list))


def summarize(records: list[dict[str, Any]], args) -> dict[str, Any]:
    errors = [f"{r['variant']} {r['scene']}#{r['run']}: {r['error']}" for r in records if r.get("error")]

    def by_scene(variant: str) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for r in records:
            if r["variant"] != variant:
                continue
            s = out.setdefault(r["scene"], {"category": r["category"], "pass": 0, "runs": 0, "details": []})
            s["runs"] += 1
            if "check" in r:
                s["pass"] += r["check"]["pass"]
                s["details"].append(r["check"]["detail"])
        return out

    def per(scenes, category):
        return {n: f"{s['pass']}/{s['runs']}" for n, s in scenes.items() if s["category"] == category}

    def mean(variant, key):
        vals = [r["usage"][key] for r in records if r["variant"] == variant and r["usage"].get(key)]
        return round(sum(vals) / len(vals), 1) if vals else None

    v = "v8" if args.baseline else "v9"  # the prompt the Phase 6-8 sets ran with
    v9, v8 = by_scene(v), by_scene("v8") if not args.baseline else {}
    p6, p7, p8 = by_scene(f"{v}-phase6"), by_scene(f"{v}-phase7"), by_scene(f"{v}-phase8")
    return {
        "model": args.model, "url": args.url, "runs": args.runs, "calls": len(records), "errors": errors,
        "prompt": v,
        "bars": {k: per(v9, k) for k in ("major", "routine", "unnamed", "reveal", "no reveal")},
        "v8_same_scenes": {k: per(v8, k) for k in ("major", "routine", "unnamed", "reveal", "no reveal")} if v8 else None,
        # Phase 6 controls have no check here: they are the prompt-token sample.
        "phase6": {k: per(p6, k) for k in ("end", "damaged", "whereabouts", "loss")},
        "phase7": {k: per(p7, k) for k in ("open", "kept", "broken", "released", "control", "reported", "major",
                                           "minor")},
        "phase8": {k: per(p8, k) for k in ("participants", "control", "secret")},
        "prompt_tokens_mean_controls": {"v8": mean("v8-tokens", "prompt_tokens"), "v9": mean("v9-tokens", "prompt_tokens")},
        "scenes": {**{f"{v} {k}": x for k, x in v9.items()}, **{f"v8 {k}": x for k, x in v8.items()},
                   **{f"phase6 {k}": x for k, x in p6.items()}, **{f"phase7 {k}": x for k, x in p7.items()},
                   **{f"phase8 {k}": x for k, x in p8.items()}},
    }


if __name__ == "__main__":
    main()
