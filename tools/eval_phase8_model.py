"""Real-model tier of the Phase 8 evaluation (docs/phases/PHASE-8.md, "Real-model tier").

Runs the sidecar's own `extract-v8` prompt and validation on short Korean scenes written for this
evaluation, several times each, against one OpenAI-compatible endpoint. Each positive scene names the
people an assertion must cover (its subject, object or typed participants), with the participants'
types; controls must produce no participant at all. A relationship report records what the extractor
does with relationship changes, read with the fact fold, without a bar. The Phase 5, 6 and 7 scenes
are re-run with `extract-v8` for their bars. The scenes are synthetic test data, not a user's chat.

    cd apps/sidecar && uv run python ../../tools/eval_phase8_model.py \\
        --url http://127.0.0.1:11434/v1 --model deepseek-v4.1-flash:cloud --runs 3 \\
        --out ../../fixtures/model/phase8/2026-09-24-deepseek-v4.1-flash
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_extraction_model import ROOT, Line, call, norm  # noqa: E402
from eval_phase6_model import SCENES as PHASE6_SCENES, narrated  # noqa: E402
from eval_phase7_model import SCENES as PHASE7_SCENES  # noqa: E402

from nmos_sidecar.extraction import SYSTEM_PROMPT, build_prompt, normalize  # noqa: E402
from nmos_sidecar.facts import _versions, version_key  # noqa: E402
from nmos_sidecar.generations import fingerprint  # noqa: E402
from nmos_sidecar.llm import parse_json_object  # noqa: E402
from nmos_sidecar.predicates import registry_prompt  # noqa: E402

V7_COMMIT = "23b13a8"  # v0.1.0-beta.14: the extract-v7 prompt and registry
U, C = "user", "char"
CHAR, GROUP = "character", "group"


def valid(items):
    return [a for a in items if a["status"] == "valid" and a["predicate"] != "also_called"]


def people(a: dict[str, Any]) -> dict[str, str]:
    """name → type of everyone an assertion covers: subject, object (people only) and participants."""
    out = {}
    for name, kind in ((a["subject"], a.get("subject_type")), (a.get("object"), a.get("object_type"))):
        if name and kind in (CHAR, GROUP):
            out[norm(name)] = kind
    for p in a.get("participants") or []:
        out[norm(p["name"])] = p["type"]
    return out


def covers(predicates: tuple[str, ...], expected: dict[str, str]):
    """Some assertion of `predicates` covers every expected person with the right type, and at least one
    of them only as a typed participant (the Phase 8 field did the work)."""
    def check(items, scene):
        hits = []
        def find(names: dict[str, str], n: str) -> str | None:  # "암살자" matches "검은 망토의 암살자"
            return next((t for got, t in names.items() if norm(n) in got), None)

        for a in valid(items):
            if a["predicate"] not in predicates:
                continue
            got = people(a)
            by_with = {norm(p["name"]): p["type"] for p in a.get("participants") or []}
            if all(find(got, n) == t for n, t in expected.items()) and any(find(by_with, n) for n in expected):
                hits.append(a)
        return bool(hits), describe(items)
    return check


def no_participants(items, scene):
    return not any(a.get("participants") for a in items), describe(items)


def describe(items) -> str:
    return str([(a["subject"], a["predicate"], a.get("object"), a.get("value"),
                 [(p["name"], p["type"]) for p in a.get("participants") or []], a.get("known_by"),
                 a.get("hidden_from")) for a in valid(items)])


def named_in_turn(items, scene) -> list[str]:
    """Participants the TARGET turn does not name (must be none)."""
    text = norm(" ".join(x for _, _, x in scene.target))
    return [p["name"] for a in items for p in a.get("participants") or [] if norm(p["name"]) not in text]


@dataclass
class Scene:
    name: str
    category: str  # participants | control | secret | relationship
    target: list[Line]
    context: list[list[Line]] = field(default_factory=list)
    hints: list[dict[str, str]] | None = None
    check: Callable[[list[dict[str, Any]], "Scene"], tuple[bool, str]] | None = None
    prior: list[dict[str, Any]] = field(default_factory=list)  # earlier facts (relationship report)
    secret_person: str = ""

    def ctx(self) -> dict[str, Any]:
        rows = []
        for t, turn in enumerate(self.context):
            rows += [{"turn": t, "metadata": {"name": s or None, "role": r}, "content": x} for s, r, x in turn]
        target = len(self.context)
        members = [{"turn": target, "metadata": {"name": s or None, "role": r}, "content": x}
                   for s, r, x in self.target]
        return {"context": rows, "members": members, "target": {"turn": target}}

    def listed(self):
        return []


def hint(*pairs: tuple[str, str]) -> list[dict[str, str]]:
    return [{"name": n, "type": t} for n, t in pairs]


def relation(subject: str, predicate: str, obj: str, value: str) -> dict[str, Any]:
    return {"subject": subject, "subject_type": CHAR, "predicate": predicate, "object": obj, "object_type": CHAR,
            "value": value, "polarity": "positive", "modality": "actual", "source": "narration", "status": "valid"}


EV = ("event",)
SCENES: list[Scene] = [
    # --- two-person events --------------------------------------------------------------------------
    Scene("giving: key", "participants",
          target=[("", U, "그 열쇠 어떻게 됐어?"),
                  ("", C, "유이는 망설이다가 은빛 열쇠를 카이토의 손에 쥐여 주었다. \"네가 가지고 있어.\"")],
          hints=hint(("유이", CHAR), ("카이토", CHAR), ("은빛 열쇠", "item")),
          check=covers(EV, {"유이": CHAR, "카이토": CHAR})),
    Scene("giving: letter", "participants",
          target=[("", U, "하나가 뭘 건네고 있어?"),
                  ("", C, "하나는 봉투에 든 편지를 유이에게 건넸다. 유이는 조심스럽게 편지를 받아 들었다.")],
          hints=hint(("하나", CHAR), ("유이", CHAR), ("편지", "item")),
          check=covers(EV, {"하나": CHAR, "유이": CHAR})),
    Scene("attack", "participants",
          target=[("", U, "카이토, 뒤를 조심해!"),
                  ("", C, "검은 망토의 암살자가 어둠 속에서 뛰쳐나와 카이토의 등을 향해 단검을 휘둘렀다.")],
          hints=hint(("카이토", CHAR)),
          check=covers(EV, {"카이토": CHAR, "암살자": CHAR})),
    Scene("confession: kaito", "participants",
          target=[("", U, "하나, 무슨 말을 하려던 거야?"),
                  ("", C, "하나는 카이토의 눈을 똑바로 바라보며 말했다. \"카이토, 나 너를 좋아해.\" 카이토의 얼굴이 "
                          "붉어졌다.")],
          hints=hint(("하나", CHAR), ("카이토", CHAR)),
          check=covers(EV, {"하나": CHAR, "카이토": CHAR})),
    Scene("confession: yui", "participants",
          target=[("", U, "카이토가 유이를 불러냈대."),
                  ("", C, "달빛 아래에서 카이토는 유이에게 오래 숨겨 온 마음을 고백했다. 유이는 아무 말 없이 고개를 "
                          "끄덕였다.")],
          hints=hint(("카이토", CHAR), ("유이", CHAR)),
          check=covers(EV, {"카이토": CHAR, "유이": CHAR})),
    Scene("rescue", "participants",
          target=[("", U, "하나가 강물에 빠졌어!"),
                  ("", C, "카이토는 망설임 없이 강물에 뛰어들어 떠내려가던 하나를 끌어냈다. 하나는 기침을 하며 숨을 "
                          "몰아쉬었다.")],
          hints=hint(("하나", CHAR), ("카이토", CHAR)),
          check=covers(EV, {"하나": CHAR, "카이토": CHAR})),
    # --- a group event --------------------------------------------------------------------------------
    Scene("group attack", "participants",
          target=[("", U, "숲길이 너무 조용해."),
                  ("", C, "그때 산적들이 덤불에서 뛰쳐나와 여행 중이던 하나와 카이토를 에워쌌다.")],
          hints=hint(("하나", CHAR), ("카이토", CHAR)),
          check=covers(EV, {"산적들": GROUP, "하나": CHAR, "카이토": CHAR})),
    # --- goal, knowledge, destroyed about another person ---------------------------------------------
    Scene("goal about another", "participants",
          target=[("", U, "그 편지는 어떻게 할 거야?"),
                  ("", C, "하나는 편지를 가슴에 꼭 안았다. 무슨 일이 있어도 카이토만은 이 편지를 읽게 하지 않겠다고 "
                          "마음먹었다.")],
          hints=hint(("하나", CHAR), ("카이토", CHAR), ("편지", "item")),
          check=covers(("goal",), {"하나": CHAR, "카이토": CHAR})),
    Scene("knows about another", "participants",
          target=[("", U, "유이는 뭔가 알고 있는 것 같아."),
                  ("", C, "유이는 카이토가 사실 이웃 나라의 왕자라는 것을 이미 알고 있었다. 하지만 아무에게도 말하지 "
                          "않았다.")],
          hints=hint(("유이", CHAR), ("카이토", CHAR)),
          check=covers(("knows",), {"유이": CHAR, "카이토": CHAR})),
    Scene("destroyed by another", "participants",
          target=[("", U, "하나의 일기장이 왜 벽난로에 있어?"),
                  ("", C, "카이토는 하나의 일기장을 벽난로에 던져 넣었다. 일기장은 순식간에 불길에 휩싸여 재가 되었다.")],
          hints=hint(("하나", CHAR), ("카이토", CHAR), ("일기장", "item")),
          check=covers(("destroyed", "event"), {"카이토": CHAR})),
    # --- controls: nobody else is involved ------------------------------------------------------------
    Scene("solo walk", "control",
          target=[("", U, "하나는 뭐 해?"), ("", C, "하나는 혼자 강가를 따라 천천히 걸으며 생각에 잠겼다.")],
          hints=hint(("하나", CHAR)), check=no_participants),
    Scene("cooking", "control",
          target=[("", U, "부엌에서 좋은 냄새가 나."), ("", C, "유이는 부엌에서 감자 수프를 끓이고 빵을 구웠다.")],
          hints=hint(("유이", CHAR)), check=no_participants),
    Scene("absent householder", "control",
          target=[("", U, "하나는 어디로 가고 있어?"),
                  ("", C, "하나는 시장에 가는 길에 카이토의 집 앞을 지나갔다. 집의 창문은 모두 닫혀 있었다.")],
          hints=hint(("하나", CHAR), ("카이토", CHAR)), check=no_participants),
    Scene("the word 하나", "control",
          target=[("", U, "상자 안에 뭐가 있어?"),
                  ("", C, "카이토는 낡은 상자를 열었다. 안에는 동전이 하나도 없었다. 카이토는 한숨을 쉬며 상자를 "
                          "닫았다.")],
          hints=hint(("카이토", CHAR)), check=no_participants),
    # --- a secret about a shared event (modeled on the owner report; new synthetic text) --------------
    Scene("secret about a shared event", "secret",
          context=[[("", U, "유이 엄마가 마키 선생님이었지?"),
                    ("", C, "유이는 고개를 끄덕였다. 마키 선생님은 유이의 엄마이자 하나의 옛 담임이었다.")]],
          target=[("", U, "하나가 유이에게 뭔가 속삭이고 있어."),
                  ("", C, '하나가 유이에게 작게 속삭였다. "사실 예전에 마키 선생님 수업에서 배가 아프다고 하고 일찍 '
                          '나왔어. 선생님은 걱정하면서 고개를 끄덕여 주셨지. 진짜 이유는 너무 불안해서였어." 유이는 '
                          '수첩에 적으려다 펜을 멈췄다. "엄마가 볼지도 모르니까 안 적을게."')],
          hints=hint(("하나", CHAR), ("유이", CHAR), ("마키 선생님", CHAR)),
          check=covers(EV, {"하나": CHAR, "마키 선생님": CHAR}), secret_person="마키 선생님"),
    # --- relationship report (no bar) ---------------------------------------------------------------
    Scene("relationship: friends to rivals", "relationship",
          context=[[("", U, "둘은 원래 친했잖아."), ("", C, "하나와 카이토는 어릴 때부터 둘도 없는 친구였다.")]],
          target=[("", U, "기사단장 자리는 하나뿐이래."),
                  ("", C, "하나와 카이토는 같은 기사단장 자리를 두고 겨루게 되었다. 그날 이후 둘은 서로를 경쟁자로 "
                          "대했고, 예전처럼 웃으며 인사하지 않았다.")],
          hints=hint(("하나", CHAR), ("카이토", CHAR)), prior=[relation("하나", "relationship", "카이토", "친구")]),
    Scene("relationship: confession accepted", "relationship",
          context=[[("", U, "유이랑 카이토는 무슨 사이야?"), ("", C, "유이와 카이토는 같은 반 친구였다.")]],
          target=[("", U, "카이토가 유이를 불러냈어."),
                  ("", C, "카이토가 떨리는 목소리로 고백하자 유이는 환하게 웃으며 그의 손을 잡았다. 그날부터 둘은 "
                          "연인이 되었다.")],
          hints=hint(("유이", CHAR), ("카이토", CHAR)), prior=[relation("유이", "relationship", "카이토", "같은 반 친구")]),
    Scene("relationship: reconciliation", "relationship",
          context=[[("", U, "유이 아직 화났어?"), ("", C, "유이는 하나에게 몹시 화가 나 있었다.")]],
          target=[("", U, "하나가 먼저 사과하러 왔어."),
                  ("", C, "하나가 진심으로 사과하자 유이는 한참 망설이다가 하나를 꼭 안아 주었다. 둘은 다시 예전처럼 "
                          "다정한 사이로 돌아갔다.")],
          hints=hint(("하나", CHAR), ("유이", CHAR)), prior=[relation("유이", "feels_toward", "하나", "분노")]),
]


def relationship_report(items: list[dict[str, Any]], scene: Scene) -> dict[str, Any]:
    """What the extractor did with a relationship change, read with the fact fold (no bar)."""
    rel = [a for a in narrated(items) if a["predicate"] in ("relationship", "feels_toward")]
    prior = [{**p, "id": i, "position": 0, "turn": 0} for i, p in enumerate(scene.prior)]
    new = [{**a, "id": 100 + i, "position": 1, "turn": 1} for i, a in enumerate(rel)]
    by_key: dict[tuple, list[dict[str, Any]]] = {}
    for a in prior + new:
        by_key.setdefault(version_key(a), []).append(a)
    facts = [f for history in by_key.values() for f in _versions(history)]
    return {"extracted": [(a["subject"], a["predicate"], a.get("object"), a.get("value")) for a in rel],
            "current": [(f["subject"], f["predicate"], f.get("object"), f.get("value")) for f in facts],
            "prior_superseded": bool(rel) and not any(f["turn"] == 0 for f in facts),
            "history_kept": any(len(f["history"]) > 1 for f in facts)}


def v7_prompt() -> str:
    """The extract-v7 system prompt, formatted with the v7 registry, read from git history."""
    def source(path: str) -> str:
        return subprocess.run(["git", "-C", str(ROOT), "show", f"{V7_COMMIT}:{path}"], check=True,
                              capture_output=True, text=True).stdout
    ns: dict[str, Any] = {}
    exec(compile(source("apps/sidecar/src/nmos_sidecar/predicates.py").replace("from .entities import node\n", ""),
                 "predicates_v7", "exec"), ns)
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
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    system = SYSTEM_PROMPT.format(registry=registry_prompt())
    system_v7 = v7_prompt()

    jobs: list[tuple[str, Any, int, str, str]] = []
    for variant, scenes in (("v8", SCENES), ("v8-phase6", PHASE6_SCENES), ("v8-phase7", PHASE7_SCENES)):
        for scene in scenes:
            for run in range(args.runs):
                listed = scene.listed() if hasattr(scene, "listed") else []
                jobs.append((variant, scene, run, system, build_prompt(scene.ctx(), scene.hints, listed)))
    for scene in (s for s in PHASE6_SCENES if s.category == "control"):  # prompt tokens, one call each
        jobs.append(("v7", scene, 0, system_v7, build_prompt(scene.ctx(), scene.hints)))
        jobs.append(("v8-tokens", scene, 0, system, build_prompt(scene.ctx(), scene.hints)))

    def work(job):
        variant, scene, run, sys_prompt, user = job
        reply = call(args.url, args.model, sys_prompt, user, args.timeout)
        record = {"scene": scene.name, "category": scene.category, "variant": variant, "run": run,
                  "system_fingerprint": fingerprint(sys_prompt), "user": user, **reply}
        if variant.startswith("v8") and variant != "v8-tokens" and not reply.get("error"):
            parsed = parse_json_object(reply["text"]) if reply["text"] else {}
            items = parsed.get("assertions") if isinstance(parsed.get("assertions"), list) else []
            turn_text = "\n".join(x for _, _, x in scene.target)
            record["assertions"] = normalize(items, turn_text, scene.hints)
            if scene.check:
                ok, detail = scene.check(record["assertions"], scene)
                record["check"] = {"pass": ok, "detail": detail}
            if variant == "v8":
                record["unnamed_participants"] = named_in_turn(record["assertions"], scene)
                if scene.secret_person:
                    person = norm(scene.secret_person)
                    record["secret"] = {
                        "in_with": any(norm(p["name"]) == person for a in record["assertions"]
                                       for p in a.get("participants") or []),
                        "in_known_by": any(person in {norm(n) for n in a.get("known_by") or []}
                                           for a in record["assertions"]),
                        "in_hidden_from": any(person in {norm(n) for n in a.get("hidden_from") or []}
                                              for a in record["assertions"])}
                if scene.category == "relationship":
                    record["relationship"] = relationship_report(record["assertions"], scene)
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

    v8, p6, p7 = by_scene("v8"), by_scene("v8-phase6"), by_scene("v8-phase7")

    def per(scenes, category):
        return {n: f"{s['pass']}/{s['runs']}" for n, s in scenes.items() if s["category"] == category}

    runs8 = [r for r in records if r["variant"] == "v8"]
    secret = [r["secret"] for r in runs8 if "secret" in r]
    p6_runs = [r for r in records if r["variant"] == "v8-phase6"]
    controls = [a for r in p6_runs if r["category"] == "control" for a in r.get("assertions", [])
                if a["status"] == "valid" and a["predicate"] != "also_called"]

    def mean_prompt(variant):
        vals = [r["usage"]["prompt_tokens"] for r in records if r["variant"] == variant and r["usage"].get("prompt_tokens")]
        return round(sum(vals) / len(vals), 1) if vals else None

    def mean_completion(variant):
        vals = [r["usage"]["completion_tokens"] for r in records if r["variant"] == variant
                and r["usage"].get("completion_tokens")]
        return round(sum(vals) / len(vals), 1) if vals else None

    with_counts = [len(a.get("participants") or []) for r in records if r["variant"].startswith("v8")
                   for a in r.get("assertions", []) if a["status"] == "valid"]
    return {
        "model": args.model, "url": args.url, "runs": args.runs, "calls": len(records), "errors": errors,
        "bars": {
            "participants": per(v8, "participants"),
            "controls_empty_with": per(v8, "control"),
            "unnamed_participants": [(r["scene"], r["run"], r["unnamed_participants"]) for r in runs8
                                     if r.get("unnamed_participants")],
            "secret_in_with": f"{sum(s['in_with'] for s in secret)}/{len(secret)}",
            "secret_in_known_by": f"{sum(s['in_known_by'] for s in secret)}/{len(secret)}",
            "phase7": {k: per(p7, k) for k in ("open", "kept", "broken", "released", "control", "reported",
                                               "major", "minor")},
            "phase6": {k: per(p6, k) for k in ("end", "damaged", "whereabouts", "loss")},
            "phase6_destroyed_outside_end_scenes": [(r["scene"], r["run"], a["subject"]) for r in p6_runs
                                                    if r["category"] in ("control", "damaged", "whereabouts", "loss")
                                                    for a in r.get("assertions", []) if a["predicate"] == "destroyed"],
            "phase5_control_mislabel": {"assertions": len(controls),
                                        "non_actual": sum(a["modality"] != "actual" for a in controls)},
        },
        "report": {
            "secret_in_hidden_from": f"{sum(s['in_hidden_from'] for s in secret)}/{len(secret)}",
            "relationship": {r["scene"] + f"#{r['run']}": r["relationship"] for r in runs8 if "relationship" in r},
            "participants_per_valid_assertion": round(sum(with_counts) / len(with_counts), 3) if with_counts else None,
            "phase6_scenes_with_participants": sum(bool(a.get("participants")) for r in p6_runs
                                                   for a in r.get("assertions", [])),
        },
        "prompt_tokens_mean_controls": {"v7": mean_prompt("v7"), "v8": mean_prompt("v8-tokens")},
        "completion_tokens_mean_controls": {"v7": mean_completion("v7"), "v8": mean_completion("v8-tokens")},
        "scenes": {**{f"v8 {k}": v for k, v in v8.items()}, **{f"phase6 {k}": v for k, v in p6.items()},
                   **{f"phase7 {k}": v for k, v in p7.items()}},
    }


if __name__ == "__main__":
    main()
