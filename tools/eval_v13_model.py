"""Real-model tier of `extract-v13` (docs/phases/PHASE-11.md, ADR 0039): open business, its end, stated causes.

Runs the sidecar's own extraction prompt and validation on short Korean scenes written for this evaluation, several
times each, against one OpenAI-compatible endpoint:

- opens: a lasting goal, a question or mystery, a threat, a debt → a thread of that kind opens (read by
  `threads.fold`);
- wish: a passing wish or the next small step of what someone is doing → no goal;
- resolve: a listed OPEN THREAD ends in the target turn → a `resolved` that ends it with the right outcome;
- control: a listed thread is worked on or talked about, not ended → nothing ends it;
- cause: a feeling whose cause the turn states → `because` is set; one whose cause it does not state → it is not.

The scenes are synthetic test data, not a user's chat. Every prompt, raw reply and check result is recorded.

    cd apps/sidecar && uv run python ../../tools/eval_v13_model.py \\
        --url http://127.0.0.1:11434/v1 --model gemma4:31b-cloud --runs 3 --workers 2 \\
        --out ../../fixtures/model/v13/2026-09-28-gemma4-31b
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_extraction_model import Line, call, norm  # noqa: E402

from nmos_sidecar.entities import resolve  # noqa: E402
from nmos_sidecar.extraction import SYSTEM_PROMPT, build_prompt, normalize  # noqa: E402
from nmos_sidecar.generations import fingerprint  # noqa: E402
from nmos_sidecar.llm import parse_json_object  # noqa: E402
from nmos_sidecar.predicates import registry_prompt  # noqa: E402
from nmos_sidecar.threads import KINDS, fold  # noqa: E402

U, C = "user", "char"
PREDICATE = {kind: predicate for predicate, kind in KINDS.items()}


def valid(items):
    return [a for a in items if a["status"] == "valid"]


def brief(items) -> str:
    return str([(a["subject"], a["predicate"], a.get("object"), a.get("value"), a.get("outcome"), a.get("because"))
                for a in valid(items) if a["predicate"] not in ("also_called",)])


def thread_row(t: dict[str, Any]) -> dict[str, Any]:
    """A listed thread as extraction stored its opening (turn 0)."""
    return {"id": 0, "position": 0, "turn": 0, "subject": t["by"], "subject_type": "character",
            "predicate": PREDICATE[t["kind"]], "object": t.get("to"), "object_type": "character" if t.get("to") else None,
            "value": t["text"], "polarity": "positive", "modality": "actual", "source": "narration",
            "asserted_by": None, "status": "valid"}


def folded(items, scene):
    rows = [thread_row(t) for t in scene.threads]
    rows += [{**a, "id": 100 + i, "position": 1, "turn": 1} for i, a in enumerate(valid(items))
             if a["predicate"] != "also_called"]
    threads, unmatched, _ = fold(rows, resolve(uuid.uuid4(), rows))
    return threads, unmatched


def opens(kind: str):
    def check(items, scene):
        threads, _ = folded(items, scene)
        return any(t["kind"] == kind and t["status"] == "open" and t["turn"] == 1 for t in threads), brief(items)
    return check


def no_goal(items, scene):
    return not any(a["predicate"] == "goal" for a in valid(items)), brief(items)


def ends(outcomes: tuple[str, ...]):
    def check(items, scene):
        threads, unmatched = folded(items, scene)
        first = [t for t in threads if t["turn"] == 0]
        return bool(first) and first[0]["status"] in outcomes, f"{brief(items)} unmatched={len(unmatched)}"
    return check


def still_open(items, scene):
    threads, _ = folded(items, scene)
    first = [t for t in threads if t["turn"] == 0]
    return bool(first) and first[0]["status"] == "open", brief(items)


def cause(stated: bool):
    def check(items, scene):
        feelings = [a for a in valid(items) if a["predicate"] in ("feels_toward", "has_status", "relationship", "event")]
        if stated:
            return any(a.get("because") for a in feelings), brief(items)
        return bool(feelings) and not any(a.get("because") for a in feelings if a["predicate"] == "feels_toward"), brief(items)
    return check


@dataclass
class Scene:
    name: str
    category: str  # opens | wish | resolve | control | cause
    target: list[Line]
    context: list[list[Line]] = field(default_factory=list)
    hints: list[dict[str, str]] | None = None
    threads: list[dict[str, Any]] = field(default_factory=list)  # OPEN THREADS listed (turn 0)
    check: Callable[[list[dict[str, Any]], "Scene"], tuple[bool, str]] | None = None

    def ctx(self) -> dict[str, Any]:
        rows = []
        for t, turn in enumerate(self.context, start=5):
            rows += [{"turn": t, "metadata": {"name": s or None, "role": r}, "content": x} for s, r, x in turn]
        target = 5 + len(self.context)
        members = [{"turn": target, "metadata": {"name": s or None, "role": r}, "content": x} for s, r, x in self.target]
        return {"context": rows, "members": members, "target": {"turn": target}}


def hint(*pairs: tuple[str, str]) -> list[dict[str, str]]:
    return [{"name": n, "type": t} for n, t in pairs]


CAST = hint(("하나", "character"), ("카이토", "character"), ("유이", "character"), ("레온", "character"))
SCARF = {"kind": "goal", "by": "하나", "text": "카이토의 생일 선물로 목도리 떠 주기", "turn": 0}
BELL = {"kind": "question", "by": "유이", "text": "한밤중에 누가 종을 울렸는지", "turn": 0}
FIRE = {"kind": "threat", "by": "하나", "text": "레온이 과수원에 불을 지르겠다고 한 것", "turn": 0}
COINS = {"kind": "debt", "by": "카이토", "to": "하나", "text": "빌린 은화 세 닢", "turn": 0}

SCENES: list[Scene] = [
    # --- opens -------------------------------------------------------------------------------------------
    Scene("goal: a lasting aim", "opens", hints=CAST, check=opens("goal"),
          target=[("", U, "하나는 요즘 왜 그렇게 요리책을 봐?"),
                  ("", C, '하나는 수줍게 웃었다. "카이토가 점심을 자주 거르잖아. 앞으로 목요일마다 도시락을 싸 주기로 '
                          '마음먹었어." 하나는 요리책에 표시를 하나 더 붙였다.')]),
    Scene("question: a mystery", "opens", hints=CAST, check=opens("question"),
          target=[("", U, "어젯밤에 종소리 들었어?"),
                  ("", C, '유이는 고개를 끄덕였다. "자정에 종이 세 번 울렸어. 그런데 종탑 열쇠는 신부님만 갖고 계시잖아. '
                          '대체 누가 울린 걸까?" 유이는 꼭 알아내겠다며 수첩에 적었다.')]),
    Scene("threat: a threat made", "opens", hints=CAST, check=opens("threat"),
          target=[("", U, "레온이 과수원 앞에서 하나를 막아섰다."),
                  ("", C, '"이번 달 안에 땅을 넘기지 않으면, 네 과수원에 불을 질러 버리겠다." 레온은 차갑게 말하고 '
                          '돌아섰다. 하나는 떨리는 손으로 울타리를 붙잡았다.')]),
    Scene("debt: money borrowed", "opens", hints=CAST, check=opens("debt"),
          target=[("", U, "카이토가 난처한 얼굴로 하나를 찾아왔다."),
                  ("", C, '"하나야, 은화 세 닢만 빌려줄 수 있어? 다음 장날에 꼭 갚을게." 하나는 지갑에서 은화 세 닢을 꺼내 '
                          '카이토의 손에 쥐여 주었다.')]),
    # --- wish: no goal -----------------------------------------------------------------------------------
    Scene("wish: hungry", "wish", hints=CAST, check=no_goal,
          target=[("", U, "배고프다. 뭐 먹을까?"),
                  ("", C, '하나는 기지개를 켜며 말했다. "아, 나도 뭔가 달달한 게 먹고 싶다." 두 사람은 부엌으로 향했다.')]),
    Scene("wish: next step", "wish", hints=CAST, check=no_goal,
          target=[("", U, "빨래 다 개면 좀 쉬자."),
                  ("", C, "하나는 마지막 수건을 개며 고개를 끄덕였다. 이것만 끝내고 차를 한 잔 마시려던 참이었다.")]),
    # --- resolve -----------------------------------------------------------------------------------------
    Scene("resolve: goal achieved", "resolve", hints=CAST, threads=[SCARF], check=ends(("achieved",)),
          target=[("", U, "카이토의 생일 아침, 하나가 포장한 상자를 내밀었다."),
                  ("", C, '카이토가 상자를 열자 하나가 한 달 내내 뜬 푸른 목도리가 나왔다. "완성했어! 생일 축하해." '
                          '카이토는 목도리를 바로 목에 둘렀고, 하나는 드디어 해냈다며 활짝 웃었다.')]),
    Scene("resolve: question answered", "resolve", hints=CAST, threads=[BELL], check=ends(("answered",)),
          target=[("", U, "종탑 앞에서 유이가 누군가를 붙잡았다."),
                  ("", C, '종지기의 아들이 머리를 긁적였다. "제가 몰래 열쇠를 복사해서 장난으로 울렸어요. 죄송해요." '
                          '유이는 그제야 한밤중의 종소리가 풀렸다며 수첩을 덮었다.')]),
    Scene("resolve: threat averted", "resolve", hints=CAST, threads=[FIRE], check=ends(("averted",)),
          target=[("", U, "경비대가 레온을 끌고 갔다."),
                  ("", C, "레온은 방화 계획이 들통나 경비대에 체포되었다. 과수원은 무사했고, 하나는 긴 한숨을 내쉬었다. "
                          "이제 불을 지르겠다던 협박은 끝이었다.")]),
    Scene("resolve: debt paid", "resolve", hints=CAST, threads=[COINS], check=ends(("paid",)),
          target=[("", U, "장날 저녁, 카이토가 하나를 찾아왔다."),
                  ("", C, '"약속한 은화 세 닢이야. 고마웠어." 카이토는 은화를 하나의 손바닥에 올려놓았다. 빚을 갚고 나니 '
                          '카이토의 얼굴이 한결 가벼워 보였다.')]),
    # --- control -----------------------------------------------------------------------------------------
    Scene("control: goal worked on", "control", hints=CAST, threads=[SCARF], check=still_open,
          target=[("", U, "하나가 밤늦게까지 뜨개질을 한다."),
                  ("", C, "하나는 목도리를 반쯤 떴다가 코를 하나 빠뜨린 걸 발견하고 한숨을 쉬었다. 생일까지는 아직 "
                          "일주일이 남아 있었다.")]),
    Scene("control: debt mentioned", "control", hints=CAST, threads=[COINS], check=still_open,
          target=[("", U, "카이토가 지갑을 뒤적인다."),
                  ("", C, '"아, 하나한테 빌린 은화… 장날까지는 꼭 갚아야 하는데." 카이토는 텅 빈 지갑을 보며 한숨을 쉬었다.')]),
    # --- cause -------------------------------------------------------------------------------------------
    Scene("cause: stated", "cause", hints=CAST, check=cause(True),
          target=[("", U, "유이가 카이토에게 등을 돌렸다."),
                  ("", C, "유이는 카이토에게 단단히 화가 났다. 카이토가 유이와의 약속을 까맣게 잊고 하나와 장터에 갔기 "
                          "때문이었다.")]),
    Scene("cause: not stated", "cause", hints=CAST, check=cause(False),
          target=[("", U, "유이가 카이토를 본다."),
                  ("", C, "유이는 카이토를 향해 싸늘한 눈빛을 보냈다. 한마디도 하지 않은 채 자리를 떠났다.")]),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--out", required=True)
    ap.add_argument("--timeout", type=float, default=180)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--only", help="comma-separated scene names")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    system = SYSTEM_PROMPT.format(registry=registry_prompt())
    scenes = [s for s in SCENES if not args.only or s.name in args.only.split(",")]
    jobs = [(scene, run, build_prompt(scene.ctx(), scene.hints, None, None, scene.threads))
            for scene in scenes for run in range(args.runs)]

    def work(job):
        scene, run, user = job
        reply = call(args.url, args.model, system, user, args.timeout)
        record = {"scene": scene.name, "category": scene.category, "run": run, "prompt": user,
                  "reply": reply.get("text"), "usage": reply.get("usage"), "seconds": reply.get("seconds"),
                  "error": reply.get("error")}
        if not reply.get("error"):
            parsed = parse_json_object(reply["text"]) or {}
            text = "\n".join(x for _, _, x in scene.target)
            items = normalize(parsed.get("assertions") if isinstance(parsed.get("assertions"), list) else [],
                              text, scene.hints)
            ok, note = scene.check(items, scene)
            record.update({"assertions": items, "pass": ok, "note": note})
        return record

    with ThreadPoolExecutor(args.workers) as pool:
        records = list(pool.map(work, jobs))
    with (out / "runs.jsonl").open("w") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    summary = {"model": args.model, "url": args.url, "runs": args.runs, "prompt_fingerprint": fingerprint(SYSTEM_PROMPT),
               "errors": [f"{r['scene']}#{r['run']}: {r['error']}" for r in records if r.get("error")], "scenes": {}}
    for r in records:
        s = summary["scenes"].setdefault(f"{r['category']} | {r['scene']}", {"pass": 0, "runs": 0, "notes": []})
        s["runs"] += 1
        s["pass"] += 1 if r.get("pass") else 0
        s["notes"].append(r.get("note") or r.get("error"))
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    for key, s in summary["scenes"].items():
        print(f"{s['pass']}/{s['runs']}  {key}")
    if summary["errors"]:
        print("errors:", summary["errors"])


if __name__ == "__main__":
    main()
