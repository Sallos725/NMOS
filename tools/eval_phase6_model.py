"""Real-model tier of the Phase 6 evaluation (docs/phases/PHASE-6.md, "Real-model tier").

Runs the sidecar's own `extract-v6` prompt and validation on short Korean scenes written for this
evaluation, several times each, against one OpenAI-compatible endpoint, and reads the result together
with the scene's earlier facts exactly as facts are read (`facts._versions`). The scenes are synthetic
test data, not a user's chat. Every prompt, raw reply, token count and check result is recorded.

    cd apps/sidecar && uv run python ../../tools/eval_phase6_model.py \\
        --url http://127.0.0.1:11434/v1 --model deepseek-v4.1-flash:cloud --runs 3 \\
        --out ../../fixtures/model/phase6/2026-09-24-deepseek-v4.1-flash
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
from eval_extraction_model import ROOT, SCENES as PHASE5_SCENES, Line, call, norm  # noqa: E402

from nmos_sidecar.extraction import SYSTEM_PROMPT, build_prompt, normalize  # noqa: E402
from nmos_sidecar.facts import _versions, version_key  # noqa: E402
from nmos_sidecar.generations import fingerprint  # noqa: E402
from nmos_sidecar.llm import parse_json_object  # noqa: E402
from nmos_sidecar.predicates import REGISTRY, registry_prompt, whereabouts  # noqa: E402

V5_COMMIT = "acd0b82"  # Phase 6 step 1: the extract-v5 prompt and registry, just before `destroyed`
U, C = "user", "char"
BASE = {"value": None, "polarity": "positive", "modality": "actual", "source": "narration", "status": "valid"}


def narrated(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [a for a in items if a["status"] == "valid" and a["predicate"] != "also_called"
            and a["modality"] == "actual" and a["source"] == "narration"]


def item_state(items: list[dict[str, Any]], scene: "Scene") -> list[dict[str, Any]]:
    """The item's current whereabouts facts after the target turn: prior facts at turn 0, extracted ones at
    turn 1, read by the fact fold (ADR 0016, ADR 0017)."""
    prior = [{**p, "id": i, "position": 0, "turn": 0} for i, p in enumerate(scene.prior)]
    new = [{**a, "id": 100 + i, "position": 1, "turn": 1} for i, a in enumerate(narrated(items)) if whereabouts(a)]
    rows = [a for a in prior + new if norm(scene.item) in norm(a["object"] if a["predicate"] == "possesses"
                                                                    else a["subject"])]
    by_key: dict[tuple, list[dict[str, Any]]] = {}
    for a in rows:
        by_key.setdefault(version_key(a), []).append(a)
    return [f for history in by_key.values() for f in _versions(history)]


def describe(facts: list[dict[str, Any]]) -> list[tuple]:
    return [(f["subject"], f["predicate"], f.get("object") or f.get("value"), f["polarity"],
             "disputed" if f.get("disputed_by") else "") for f in facts]


def positive(facts, predicate: str) -> list[dict[str, Any]]:
    return [f for f in facts if f["predicate"] == predicate and f["polarity"] == "positive"]


def ended(items, scene):
    """Destroyed: no current holder or place, and a current `destroyed`."""
    facts = item_state(items, scene)
    ok = bool(positive(facts, "destroyed")) and not positive(facts, "possesses") and not positive(facts, "located_in")
    return ok, f"current={describe(facts)}"


def intact(items, scene):
    """Damaged, not destroyed: no `destroyed` for the item, and the prior holder stays."""
    facts = item_state(items, scene)
    holder = [f for f in positive(facts, "possesses") if norm(f["subject"]) == norm(scene.prior[0]["subject"])]
    ok = not any(f["predicate"] == "destroyed" for f in facts) and bool(holder)
    return ok, f"current={describe(facts)}"


def at_place(place: str, not_held_by: str):
    def check(items, scene):
        facts = item_state(items, scene)
        ok = (any(said_place(f, place) for f in positive(facts, "located_in"))
              and not any(norm(f["subject"]) == norm(not_held_by) for f in positive(facts, "possesses")))
        return ok, f"current={describe(facts)}"
    return check


def held_by(holder: str, not_at: str):
    def check(items, scene):
        facts = item_state(items, scene)
        ok = (any(norm(f["subject"]) == norm(holder) for f in positive(facts, "possesses"))
              and not any(said_place(f, not_at) for f in positive(facts, "located_in")))
        return ok, f"current={describe(facts)}"
    return check


def lost(items, scene):
    """A loss is a negation, not an end: the holder ends and nothing says the item is destroyed."""
    facts = item_state(items, scene)
    ok = not positive(facts, "possesses") and not any(f["predicate"] == "destroyed" for f in facts)
    return ok, f"current={describe(facts)}"


def said_place(f: dict[str, Any], place: str) -> bool:
    return norm(place) in norm(f.get("object"))


@dataclass
class Scene:
    name: str
    category: str  # end | damaged | whereabouts | loss | control
    item: str
    target: list[Line]
    context: list[list[Line]] = field(default_factory=list)
    hints: list[dict[str, str]] | None = None
    prior: list[dict[str, Any]] = field(default_factory=list)
    check: Callable[[list[dict[str, Any]], "Scene"], tuple[bool, str]] | None = None

    def ctx(self) -> dict[str, Any]:
        rows = []
        for t, turn in enumerate(self.context):
            rows += [{"turn": t, "metadata": {"name": s or None, "role": r}, "content": x} for s, r, x in turn]
        target = len(self.context)
        members = [{"turn": target, "metadata": {"name": s or None, "role": r}, "content": x}
                   for s, r, x in self.target]
        return {"context": rows, "members": members, "target": {"turn": target}}


def holds(who: str, item: str) -> dict[str, Any]:
    return {**BASE, "subject": who, "subject_type": "character", "predicate": "possesses", "object": item,
            "object_type": "item"}


def lies_at(item: str, place: str) -> dict[str, Any]:
    return {**BASE, "subject": item, "subject_type": "item", "predicate": "located_in", "object": place,
            "object_type": "place"}


def hint(*pairs: tuple[str, str]) -> list[dict[str, str]]:
    return [{"name": n, "type": t} for n, t in pairs]


SCENES: list[Scene] = [
    # --- the item stops existing ----------------------------------------------------------------------
    Scene("burned letter", "end", "편지",
          context=[[("", U, "그 편지 아직 있어?"), ("", C, "하나는 품에서 봉인된 편지를 꺼내 보였다.")]],
          target=[("", U, "아무도 못 보게 해야 해."),
                  ("", C, "하나는 편지를 촛불에 가져다 댔다. 불길이 종이를 삼켰고, 편지는 순식간에 한 줌의 재가 "
                          "되어 바닥에 흩어졌다.")],
          hints=hint(("편지", "item"), ("하나", "character")), prior=[holds("하나", "편지")], check=ended),
    Scene("eaten apple", "end", "사과",
          context=[[("", U, "배고프다."), ("", C, "유이는 가방에서 빨간 사과를 하나 꺼냈다.")]],
          target=[("", U, "그거 먹어도 돼."),
                  ("", C, "유이는 사과를 와삭 베어 물었다. 몇 입 만에 사과를 다 먹어 치우고 손가락에 묻은 즙을 "
                          "핥았다.")],
          hints=hint(("사과", "item"), ("유이", "character")), prior=[holds("유이", "사과")], check=ended),
    Scene("drunk potion", "end", "치유 물약",
          context=[[("", U, "물약 남았어?"), ("", C, "카이토는 허리춤의 치유 물약을 확인했다. 마지막 한 병이었다.")]],
          target=[("", U, "지금 마셔! 피가 너무 많이 나."),
                  ("", C, "카이토는 치유 물약의 마개를 이로 뽑고 단숨에 들이켰다. 상처가 서서히 아물기 시작했다.")],
          hints=hint(("치유 물약", "item"), ("카이토", "character")), prior=[holds("카이토", "치유 물약")],
          check=ended),
    Scene("last match", "end", "성냥",
          context=[[("", U, "불 피울 수 있어?"), ("", C, "하나는 주머니에서 성냥을 꺼냈다. 딱 한 개비 남아 있었다.")]],
          target=[("", U, "조심해서 켜."),
                  ("", C, "하나는 마지막 성냥을 그어 모닥불에 불을 붙였다. 다 탄 성냥개비를 불 속에 던졌다. 이제 "
                          "성냥은 하나도 없었다.")],
          hints=hint(("성냥", "item"), ("하나", "character")), prior=[holds("하나", "성냥")], check=ended),
    # --- damaged but intact (must not end) --------------------------------------------------------
    Scene("cracked sword", "damaged", "낡은 검",
          context=[[("", U, "준비됐어?"), ("", C, "카이토는 허리에 찬 낡은 검의 손잡이를 쥐었다.")]],
          target=[("", U, "막아!"),
                  ("", C, "카이토는 낡은 검으로 도끼를 받아 냈다. 검날에 길게 금이 갔지만, 그는 여전히 검을 굳게 "
                          "쥐고 다음 공격에 대비했다.")],
          hints=hint(("낡은 검", "item"), ("카이토", "character")), prior=[holds("카이토", "낡은 검")],
          check=intact),
    Scene("torn cloak", "damaged", "망토",
          context=[[("", U, "춥지 않아?"), ("", C, "유이는 두꺼운 망토를 여몄다.")]],
          target=[("", U, "가시덤불 조심해."),
                  ("", C, "유이의 망토 자락이 가시덤불에 걸려 찢어졌다. 유이는 찢어진 망토를 다시 여미고 걸음을 "
                          "재촉했다.")],
          hints=hint(("망토", "item"), ("유이", "character")), prior=[holds("유이", "망토")], check=intact),
    # --- whereabouts ------------------------------------------------------------------------------
    Scene("put down", "whereabouts", "지도",
          context=[[("", U, "지도 좀 보자."), ("", C, "하나는 지도를 손에 들고 있었다.")]],
          target=[("", U, "잠깐 쉬었다 가자."),
                  ("", C, "하나는 지도를 부엌 탁자 위에 내려놓고 방을 나갔다.")],
          hints=hint(("지도", "item"), ("하나", "character"), ("부엌 탁자", "place")),
          prior=[holds("하나", "지도")], check=at_place("탁자", "하나")),
    Scene("picked up", "whereabouts", "열쇠",
          context=[[("", U, "저기 뭐가 있어?"), ("", C, "분수대 가장자리에 열쇠가 놓여 있었다.")]],
          target=[("", U, "주워 봐."),
                  ("", C, "카이토는 분수대에서 열쇠를 집어 들고 주머니에 넣었다.")],
          hints=hint(("열쇠", "item"), ("카이토", "character"), ("분수대", "place")),
          prior=[lies_at("열쇠", "분수대")], check=held_by("카이토", "분수대")),
    # --- a loss is not an end ---------------------------------------------------------------------
    Scene("lost map", "loss", "해안 지도",
          context=PHASE5_SCENES[0].context, target=PHASE5_SCENES[0].target, hints=PHASE5_SCENES[0].hints,
          prior=[holds("하나", "해안 지도")], check=lost),
] + [Scene(s.name, "control", "", target=s.target, context=s.context, hints=s.hints)
     for s in PHASE5_SCENES if s.category == "control"]


def v5_prompt() -> str:
    """The extract-v5 system prompt, formatted with the v5 registry, read from git history."""
    def source(path: str) -> str:
        return subprocess.run(["git", "-C", str(ROOT), "show", f"{V5_COMMIT}:{path}"], check=True,
                              capture_output=True, text=True).stdout
    ns: dict[str, Any] = {}
    exec(compile(source("apps/sidecar/src/nmos_sidecar/predicates.py"), "predicates_v5", "exec"), ns)
    tree = ast.parse(source("apps/sidecar/src/nmos_sidecar/extraction.py"))
    prompt = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                  and any(getattr(t, "id", None) == "SYSTEM_PROMPT" for t in n.targets))
    return prompt.format(registry=ns["registry_prompt"]())


def multi_valued_turn(items: list[dict[str, Any]]) -> list[tuple]:
    """Single-valued keys (and whereabouts slots) with two different positive values in one turn."""
    groups: dict[tuple, set] = {}
    for a in narrated(items):
        if a["polarity"] != "positive":
            continue
        if whereabouts(a):
            key = version_key(a) + (a["predicate"],)
        elif REGISTRY[a["predicate"]].cardinality == "single":
            key = version_key(a)
        else:
            continue
        groups.setdefault(key, set()).add((norm(a["subject"]), norm(a.get("object")), norm(a.get("value"))))
    return [(k, sorted(v)) for k, v in groups.items() if len(v) > 1]


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
    system_v5 = v5_prompt()

    jobs: list[tuple[str, Scene, int, str, str]] = []
    for scene in SCENES:
        for run in range(args.runs):
            jobs.append(("v6", scene, run, system, build_prompt(scene.ctx(), scene.hints)))
    for scene in (s for s in SCENES if s.category == "control"):  # prompt-token comparison, one call each
        jobs.append(("v5", scene, 0, system_v5, build_prompt(scene.ctx(), scene.hints)))

    def work(job):
        variant, scene, run, sys_prompt, user = job
        reply = call(args.url, args.model, sys_prompt, user, args.timeout)
        record = {"scene": scene.name, "category": scene.category, "variant": variant, "run": run,
                  "system_fingerprint": fingerprint(sys_prompt), "user": user, **reply}
        if variant == "v6" and not reply.get("error"):
            parsed = parse_json_object(reply["text"]) if reply["text"] else {}
            items = parsed.get("assertions") if isinstance(parsed.get("assertions"), list) else []
            turn_text = "\n".join(x for _, _, x in scene.target)
            record["assertions"] = normalize(items, turn_text, scene.hints)
            record["multi_valued"] = multi_valued_turn(record["assertions"])
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
    v6 = [r for r in records if r["variant"] == "v6"]
    errors = [f"{r['scene']}#{r['run']}: {r['error']}" for r in records if r.get("error")]
    by_scene: dict[str, dict[str, Any]] = {}
    for r in v6:
        s = by_scene.setdefault(r["scene"], {"category": r["category"], "pass": 0, "runs": 0, "details": []})
        s["runs"] += 1
        if "check" in r:
            s["pass"] += r["check"]["pass"]
            s["details"].append(r["check"]["detail"])
    controls = [a for r in v6 if r["category"] == "control" for a in r.get("assertions", [])
                if a["status"] == "valid" and a["predicate"] != "also_called"]
    destroyed_anywhere_else = [(r["scene"], r["run"], a["subject"], a.get("value")) for r in v6
                               if r["category"] in ("control", "damaged", "whereabouts", "loss")
                               for a in r.get("assertions", []) if a["predicate"] == "destroyed"]

    def mean_prompt(variant: str) -> float | None:
        vals = [r["usage"]["prompt_tokens"] for r in records if r["variant"] == variant
                and r["category"] == "control" and r["usage"].get("prompt_tokens")]
        return round(sum(vals) / len(vals), 1) if vals else None

    completion = [r["usage"]["completion_tokens"] for r in v6 if r["usage"].get("completion_tokens")]

    def per(category: str) -> dict[str, str]:
        return {n: f"{s['pass']}/{s['runs']}" for n, s in by_scene.items() if s["category"] == category}

    return {
        "model": args.model, "url": args.url, "runs": args.runs, "calls": len(records), "errors": errors,
        "bars": {
            "end": per("end"),
            "damaged_intact": per("damaged"),
            "whereabouts": per("whereabouts"),
            "loss_not_end": per("loss"),
            "destroyed_outside_end_scenes": destroyed_anywhere_else,
            "control_mislabel": {"assertions": len(controls),
                                 "non_actual": sum(a["modality"] != "actual" for a in controls)},
        },
        "report": {
            "multi_valued_turns": {"runs": len(v6), "runs_with_any": sum(bool(r.get("multi_valued")) for r in v6),
                                   "examples": [(r["scene"], r["run"], r["multi_valued"]) for r in v6
                                                if r.get("multi_valued")][:20]},
        },
        "prompt_tokens_mean_controls": {"v5": mean_prompt("v5"), "v6": mean_prompt("v6")},
        "completion_tokens_mean_v6": round(sum(completion) / len(completion), 1) if completion else None,
        "scenes": by_scene,
    }


if __name__ == "__main__":
    sys.exit(main())
