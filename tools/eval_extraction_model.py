"""Real-model tier of the Phase 5 evaluation (docs/phases/PHASE-5.md, "Real-model tier").

Runs the sidecar's own extraction prompt and validation (`extract-v5`: SYSTEM_PROMPT, build_prompt,
normalize) on short Korean scenes written for this evaluation, several times each, against one
OpenAI-compatible endpoint, and checks the Phase 5 acceptance bars. The scenes are synthetic test
data, not a user's chat. Every prompt, raw reply, token count and check result is recorded.

    cd apps/sidecar && uv run python ../../tools/eval_extraction_model.py \\
        --url http://127.0.0.1:11434/v1 --model deepseek-v4.1-flash:cloud --runs 3 \\
        --out ../../fixtures/model/phase5/2026-09-24-deepseek-v4.1-flash
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from nmos_sidecar.extraction import SYSTEM_PROMPT, build_prompt, normalize
from nmos_sidecar.facts import _versions, version_key
from nmos_sidecar.generations import fingerprint
from nmos_sidecar.llm import parse_json_object
from nmos_sidecar.predicates import registry_prompt

ROOT = Path(__file__).resolve().parents[1]
V4_COMMIT = "d557496^1"  # main just before Phase 5 step 2 (extract-v4 prompt and registry)

Line = tuple[str, str, str]  # (speaker, role, text); speaker "" = no name


def norm(text: str | None) -> str:
    return " ".join(str(text or "").casefold().split())


def said(a: dict[str, Any], *words: str) -> bool:
    """Whether any word occurs in the assertion's subject, object or value."""
    blob = norm(" ".join(str(a.get(k) or "") for k in ("subject", "object", "value")))
    return any(norm(w) in blob for w in words)


def valid(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [a for a in items if a["status"] == "valid" and a["predicate"] != "also_called"]


def state_forming(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Assertions that would form or change current state (ADR 0013): actual narration, positive."""
    return [a for a in valid(items) if a["modality"] == "actual" and a["source"] == "narration"
            and a["polarity"] == "positive"]


@dataclass
class Scene:
    name: str
    category: str  # negation | false_state | alias | false_merge | reuse | control
    target: list[Line]
    context: list[list[Line]] = field(default_factory=list)  # earlier turns, oldest first
    hints: list[dict[str, str]] | None = None
    prior: list[dict[str, Any]] = field(default_factory=list)  # narrated facts before the target turn
    check: Callable[[list[dict[str, Any]], "Scene"], tuple[bool, str]] | None = None

    def ctx(self) -> dict[str, Any]:
        rows = []
        for t, turn in enumerate(self.context):
            rows += [{"turn": t, "metadata": {"name": s or None, "role": r}, "content": x} for s, r, x in turn]
        target = len(self.context)
        members = [{"turn": target, "metadata": {"name": s or None, "role": r}, "content": x}
                   for s, r, x in self.target]
        return {"context": rows, "members": members, "target": {"turn": target}}


def forbid(pred: Callable[[dict[str, Any]], bool], what: str):
    def check(items, scene):
        bad = [a for a in state_forming(items) if pred(a)]
        return (not bad, f"{what}: {[(a['subject'], a['predicate'], a.get('object') or a.get('value')) for a in bad]}"
                if bad else "ok")
    return check


def ends_prior(item_word: str, holder: str):
    """The prior holding is current no longer: read prior + extracted exactly as facts are read."""
    def check(items, scene):
        prior = [{**p, "position": 0, "turn": 0} for p in scene.prior]
        new = [{**a, "position": 1, "turn": 1} for a in valid(items)
               if a["modality"] == "actual" and a["source"] == "narration" and a["predicate"] == "possesses"]
        key = version_key(prior[0])
        history = prior + [a for a in new if version_key(a) == key]
        current = [f for f in _versions(history) if norm(f["subject"]) == norm(holder)]
        ok = bool(current) and current[0]["polarity"] == "negative"
        return ok, f"{item_word}: current={[(f['subject'], f['polarity']) for f in _versions(history)]}"
    return check


def alias_between(*names: str, need: int = 2):
    def check(items, scene):
        links = [a for a in items if a["predicate"] == "also_called"]
        # What the resolver links (ADR 0012, amended 2026-09-24): narration, or the speaker's own name.
        good = [a for a in links if a["status"] == "valid" and a["modality"] == "actual"
                and (a["source"] == "narration" or norm(a["asserted_by"]) == norm(a["subject"]))
                and sum(said(a, n) for n in names) >= need]
        return bool(good), f"also_called: {[(a['subject'], a['value'], a['status'], a['source']) for a in links]}"
    return check


def not_named(holder: str, hinted: str):
    def check(items, scene):
        bad = [a for a in valid(items) if norm(a["subject"]) == norm(holder)
               and norm(a.get("object")) == norm(hinted)]
        objs = [(a["subject"], a["predicate"], a.get("object")) for a in valid(items) if a.get("object")]
        return not bad, f"objects: {objs}"
    return check


def reuses(hinted: str):
    def check(items, scene):
        objs = [a.get("object") for a in valid(items) if a.get("object")]
        return any(norm(o) == norm(hinted) for o in objs), f"objects: {objs}"
    return check


U, C = "user", "char"
POSSESS = {"subject_type": "character", "predicate": "possesses", "object_type": "item", "value": None,
           "polarity": "positive", "modality": "actual", "source": "narration"}

SCENES: list[Scene] = [
    # --- negation and loss ------------------------------------------------------------------------
    Scene("lost map", "negation",
          context=[[("", U, "하나야, 그 지도 아직 가지고 있어?"),
                    ("", C, '하나는 가방에서 해안 지도를 꺼내 흔들어 보였다. "당연하지."')]],
          target=[("", U, "절벽 길을 조심해서 내려가자."),
                  ("", C, "절벽 길을 내려가던 하나가 미끄러지며 손에 쥐고 있던 해안 지도를 놓쳤다. 지도는 바람에 "
                          "날려 바다로 떨어졌고, 파도 속으로 사라졌다. 하나는 빈손을 멍하니 내려다보았다.")],
          hints=[{"name": "해안 지도", "type": "item"}, {"name": "하나", "type": "character"}],
          prior=[{**POSSESS, "subject": "하나", "object": "해안 지도"}], check=ends_prior("해안 지도", "하나")),
    Scene("broken sword", "negation",
          context=[[("", U, "카이토, 준비됐어?"), ("", C, "카이토는 허리에 찬 낡은 검의 손잡이를 쥐었다.")]],
          target=[("", U, "다리 위에서 산적들이 덮쳐 온다!"),
                  ("", C, "카이토는 낡은 검을 휘둘러 막아 냈지만, 세 번째 일격에 검날이 부러졌다. 부러진 검은 손에서 "
                          "미끄러져 강물 속으로 사라졌다. 이제 카이토에게는 무기가 없었다.")],
          hints=[{"name": "낡은 검", "type": "item"}, {"name": "카이토", "type": "character"}],
          prior=[{**POSSESS, "subject": "카이토", "object": "낡은 검"}], check=ends_prior("낡은 검", "카이토")),
    Scene("did not go", "false_state",
          target=[("", U, "유이는 어젯밤 축제에 갔어?"),
                  ("", C, "유이는 어젯밤 축제에 가지 않았다. 그녀는 밤새 기숙사 방에서 시험 공부를 했다.")],
          check=forbid(lambda a: said(a, "유이") and said(a, "축제") and a["predicate"] == "located_in",
                       "festival as a place she was")),
    # --- plans and conditions ---------------------------------------------------------------------
    Scene("plan to meet", "false_state",
          target=[("", U, "내일 비가 그치면 우리 등대에 가 보자."),
                  ("", C, '하나는 창밖의 빗줄기를 보며 고개를 끄덕였다. "좋아. 비가 그치면 내일 아침에 등대 앞에서 '
                          '만나."')],
          check=forbid(lambda a: a["predicate"] == "located_in" and said(a, "등대"), "at the lighthouse")),
    Scene("condition", "false_state",
          target=[("", U, "만약 카이토가 그 편지를 읽으면 어떡하지?"),
                  ("", C, '하나는 편지를 서랍 깊숙이 넣고 잠갔다. "카이토가 읽으면 모든 게 끝이야. 절대 보여 주면 '
                          '안 돼."')],
          check=forbid(lambda a: norm(a["subject"]) == "카이토" and said(a, "편지"), "Kaito and the letter")),
    # --- dreams and imagination -------------------------------------------------------------------
    Scene("dream", "false_state",
          target=[("", U, "하나, 괜찮아? 식은땀을 흘리고 있어."),
                  ("", C, "하나는 꿈속에서 불타는 성당 한가운데 서 있었다. 비명을 지르며 눈을 뜨자, 익숙한 기숙사 "
                          "천장이 보였다.")],
          check=forbid(lambda a: a["predicate"] == "located_in" and said(a, "성당"), "in the chapel")),
    Scene("daydream", "false_state",
          target=[("", U, "유이, 수업 중에 뭘 그렇게 멍하니 봐?"),
                  ("", C, "유이는 턱을 괴고 창밖을 보며 자신이 왕관을 쓴 공주가 되어 왕좌에 앉아 있는 모습을 "
                          "상상했다. 선생님이 부르는 소리에 그제야 정신을 차렸다.")],
          check=forbid(lambda a: norm(a["subject"]) == "유이" and said(a, "공주", "왕좌", "왕관"), "princess")),
    # --- claims in dialogue -----------------------------------------------------------------------
    Scene("boast", "false_state",
          context=[[("", U, "기사단은 어때?"), ("", C, "카이토는 기사단에 들어온 지 사흘 된 견습 기사다.")]],
          target=[("", U, "너 기사단에서 무슨 일 해?"),
                  ("", C, '카이토가 가슴을 펴며 말했다. "나는 왕국 최고의 기사다! 용도 혼자 쓰러뜨렸지." 옆에 있던 '
                          '선배 기사들이 킥킥 웃었다.')],
          check=forbid(lambda a: norm(a["subject"]) == "카이토" and said(a, "최고", "용"), "boast as fact")),
    Scene("lie", "false_state",
          target=[("", U, "어젯밤에 어디 있었어?"),
                  ("", C, '하나가 태연하게 말했다. "어젯밤엔 밤새 도서관에 있었어." 하지만 그녀의 신발에는 젖은 '
                          '모래가 잔뜩 묻어 있었다.')],
          check=forbid(lambda a: a["predicate"] == "located_in" and said(a, "도서관"), "in the library")),
    # --- stated aliases ---------------------------------------------------------------------------
    Scene("self-introduction", "alias",
          target=[("", U, "전학생이 왔다던데?"),
                  ("", C, '새로 온 전학생은 칠판에 \'미나토 하루카\'라고 이름을 쓰고는 웃었다. "다들 하루라고 불러 '
                          '줘."')],
          check=alias_between("미나토 하루카", "하루카", "하루")),
    Scene("two scripts", "alias",
          target=[("", U, "영어 수업은 어땠어?"),
                  ("", C, "하나(Hana)는 영어 수업 시간에 이름표에 'Hana'라고 적었다. 선생님이 발음을 칭찬했다.")],
          check=alias_between("하나", "hana")),
    # --- hints: a different item of the same kind must keep its own name -------------------------
    Scene("second map", "false_merge",
          target=[("", U, "서랍에 뭐가 있어?"),
                  ("", C, "카이토는 서랍에서 낡은 별자리 지도를 꺼냈다. 해안 지도와는 전혀 다른, 밤하늘이 그려진 "
                          "지도였다. 그는 그것을 코트 주머니에 넣었다.")],
          hints=[{"name": "해안 지도", "type": "item"}, {"name": "카이토", "type": "character"},
                 {"name": "하나", "type": "character"}],
          check=not_named("카이토", "해안 지도")),
    Scene("second key", "false_merge",
          target=[("", U, "분수대 바닥에 뭔가 반짝이는데?"),
                  ("", C, "유이는 분수대 바닥에서 녹슨 청동 열쇠를 주웠다. 은빛 열쇠와는 모양이 전혀 달랐다. 그녀는 "
                          "열쇠를 손수건에 싸서 챙겼다.")],
          hints=[{"name": "은빛 열쇠", "type": "item"}, {"name": "유이", "type": "character"}],
          check=not_named("유이", "은빛 열쇠")),
    Scene("same map again", "reuse",
          target=[("", U, "동굴 위치 기억나?"),
                  ("", C, "하나는 가방에서 지도를 꺼내 책상 위에 펼쳤다. 해안선을 따라 손가락을 움직이며 동굴 위치를 "
                          "짚었다.")],
          hints=[{"name": "해안 지도", "type": "item"}, {"name": "하나", "type": "character"}],
          check=reuses("해안 지도")),
    # --- controls: plain actual events ------------------------------------------------------------
    Scene("library", "control",
          target=[("", U, "도서관에 가 보자."),
                  ("", C, "하나는 도서관 문을 열고 들어갔다. 카이토가 창가 자리에서 두꺼운 역사책을 읽고 있었다.")]),
    Scene("key handed over", "control",
          target=[("", U, "열쇠는 누가 가지고 있어?"),
                  ("", C, "유이는 카이토에게 은빛 열쇠를 건넸다. 카이토는 열쇠를 받아 주머니에 넣었다.")]),
    Scene("sprained ankle", "control",
          target=[("", U, "왜 절뚝거려?"),
                  ("", C, "하나는 계단을 뛰어 내려가다 넘어져 오른쪽 발목을 삐었다. 보건실 선생님이 붕대를 감아 "
                          "주었다.")]),
    Scene("promotion", "control",
          target=[("", U, "오늘 기사단에 무슨 일 있었어?"),
                  ("", C, "카이토는 기사단의 부단장으로 임명되었다. 단원들이 그를 둘러싸고 박수를 쳤다.")]),
]

FORTY = [{"name": f"{w} {i}", "type": t} for i, (w, t) in enumerate(
    [("등장인물", "character"), ("장소", "place"), ("물건", "item"), ("단체", "group")] * 10)]


def v4_prompt() -> str:
    """The extract-v4 system prompt, formatted with the v4 registry, read from git history."""
    def source(path: str) -> str:
        return subprocess.run(["git", "-C", str(ROOT), "show", f"{V4_COMMIT}:{path}"], check=True,
                              capture_output=True, text=True).stdout
    ns: dict[str, Any] = {}
    exec(compile(source("apps/sidecar/src/nmos_sidecar/predicates.py"), "predicates_v4", "exec"), ns)
    tree = ast.parse(source("apps/sidecar/src/nmos_sidecar/extraction.py"))
    prompt = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                  and any(getattr(t, "id", None) == "SYSTEM_PROMPT" for t in n.targets))
    return prompt.format(registry=ns["registry_prompt"]())


def call(url: str, model: str, system: str, user: str, timeout: float) -> dict[str, Any]:
    body = {"model": model, "temperature": 0, "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    for attempt in range(3):
        try:
            started = time.perf_counter()
            res = httpx.post(f"{url.rstrip('/')}/chat/completions", json=body, timeout=timeout)
            res.raise_for_status()
            data = res.json()
            return {"text": data["choices"][0]["message"]["content"] or "", "usage": data.get("usage") or {},
                    "seconds": round(time.perf_counter() - started, 1), "attempts": attempt + 1}
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            error = str(exc)
    return {"text": "", "usage": {}, "error": error, "attempts": 3}


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
    system_v4 = v4_prompt()

    jobs: list[tuple[str, Scene, int, str, str]] = []  # (variant, scene, run, system, user)
    for scene in SCENES:
        for run in range(args.runs):
            jobs.append(("v5", scene, run, system, build_prompt(scene.ctx(), scene.hints)))
    for scene in (s for s in SCENES if s.category == "control"):  # prompt-token comparison, one call each
        jobs.append(("v5-40-hints", scene, 0, system, build_prompt(scene.ctx(), FORTY)))
        jobs.append(("v4", scene, 0, system_v4, build_prompt(scene.ctx(), None)))

    def work(job):
        variant, scene, run, sys_prompt, user = job
        reply = call(args.url, args.model, sys_prompt, user, args.timeout)
        record = {"scene": scene.name, "category": scene.category, "variant": variant, "run": run,
                  "system_fingerprint": fingerprint(sys_prompt), "user": user, **reply}
        if variant == "v5" and not reply.get("error"):
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
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    summary = summarize(records, args)
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def summarize(records: list[dict[str, Any]], args) -> dict[str, Any]:
    v5 = [r for r in records if r["variant"] == "v5"]
    errors = [f"{r['scene']}#{r['run']}: {r['error']}" for r in records if r.get("error")]
    by_scene: dict[str, dict[str, Any]] = {}
    for r in v5:
        s = by_scene.setdefault(r["scene"], {"category": r["category"], "pass": 0, "runs": 0, "details": []})
        s["runs"] += 1
        if "check" in r:
            s["pass"] += r["check"]["pass"]
            s["details"].append(r["check"]["detail"])
    controls = [a for r in v5 if r["category"] == "control" for a in r.get("assertions", [])
                if a["status"] == "valid" and a["predicate"] != "also_called"]
    mislabeled = [a for a in controls if a["modality"] != "actual"]
    false_state = {n: s["runs"] - s["pass"] for n, s in by_scene.items() if s["category"] == "false_state"}

    def tokens(variant: str) -> float | None:
        vals = [r["usage"].get("prompt_tokens") for r in records if r["variant"] == variant and r["usage"]]
        vals = [v for v in vals if v is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    completion = [r["usage"].get("completion_tokens") for r in v5 if r["usage"].get("completion_tokens")]
    claims = [a for r in v5 if r["category"] == "false_state" for a in r.get("assertions", [])
              if a["status"] == "valid" and a["source"] == "character_claim"]
    shown = [a for a in claims if a["modality"] in ("actual", "unknown")]
    return {
        "model": args.model, "url": args.url, "runs": args.runs, "calls": len(records), "errors": errors,
        "bars": {
            "no_false_state": {"violations": sum(false_state.values()), "per_scene": false_state},
            "control_mislabel": {"assertions": len(controls), "non_actual": len(mislabeled),
                                 "ratio": round(len(mislabeled) / len(controls), 3) if controls else None,
                                 "examples": [(a["subject"], a["predicate"], a.get("object") or a.get("value"),
                                               a["modality"]) for a in mislabeled[:10]]},
            "negation": {n: f"{s['pass']}/{s['runs']}" for n, s in by_scene.items() if s["category"] == "negation"},
            "false_merge": {n: f"{s['pass']}/{s['runs']}" for n, s in by_scene.items()
                            if s["category"] == "false_merge"},
        },
        "report": {
            "alias": {n: f"{s['pass']}/{s['runs']}" for n, s in by_scene.items() if s["category"] == "alias"},
            "reuse": {n: f"{s['pass']}/{s['runs']}" for n, s in by_scene.items() if s["category"] == "reuse"},
            "claims_in_false_state_scenes": {"total": len(claims), "rendered_as_claim": len(shown)},
        },
        "prompt_tokens_mean_controls": {"v4": tokens("v4"), "v5": round(sum(
            r["usage"]["prompt_tokens"] for r in v5 if r["category"] == "control" and r["usage"].get("prompt_tokens")
        ) / max(1, sum(1 for r in v5 if r["category"] == "control" and r["usage"].get("prompt_tokens"))), 1),
            "v5_with_40_hints": tokens("v5-40-hints")},
        "completion_tokens_mean_v5": round(sum(completion) / len(completion), 1) if completion else None,
        "scenes": by_scene,
    }


if __name__ == "__main__":
    sys.exit(main())
