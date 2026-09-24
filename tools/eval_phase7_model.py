"""Real-model tier of the Phase 7 evaluation (docs/phases/PHASE-7.md, "Real-model tier").

Runs the sidecar's own `extract-v7` prompt and validation on short Korean scenes written for this
evaluation, several times each, against one OpenAI-compatible endpoint. Promise scenes are read with
the scene's earlier promise exactly as threads are read (`threads.fold`); event scenes check the
salience label. The Phase 5 and Phase 6 scenes are re-run with `extract-v7` for their bars. The scenes
are synthetic test data, not a user's chat. Every prompt, raw reply, token count and check result is
recorded.

    cd apps/sidecar && uv run python ../../tools/eval_phase7_model.py \\
        --url http://127.0.0.1:11434/v1 --model deepseek-v4.1-flash:cloud --runs 3 \\
        --out ../../fixtures/model/phase7/2026-09-24-deepseek-v4.1-flash
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_extraction_model import ROOT, Line, call, norm  # noqa: E402
from eval_phase6_model import SCENES as PHASE6_SCENES, narrated  # noqa: E402

from nmos_sidecar.entities import resolve  # noqa: E402
from nmos_sidecar.extraction import SYSTEM_PROMPT, build_prompt, normalize  # noqa: E402
from nmos_sidecar.generations import fingerprint  # noqa: E402
from nmos_sidecar.llm import parse_json_object  # noqa: E402
from nmos_sidecar.predicates import registry_prompt  # noqa: E402
from nmos_sidecar.threads import fold, resolves  # noqa: E402

V6_COMMIT = "4630c4b"  # v0.1.0-beta.13: the extract-v6 prompt and registry
U, C = "user", "char"
USER = "{{user}}"


def promise_row(by: str, to: str, text: str) -> dict[str, Any]:
    """An earlier promise as extraction stores one said in dialogue (turn 0)."""
    return {"id": 0, "position": 0, "turn": 0, "subject": by, "subject_type": "character", "predicate": "promised",
            "object": to, "object_type": "character", "value": text, "polarity": "positive", "modality": "actual",
            "source": "character_claim", "asserted_by": by, "status": "valid"}


def threads_after(items: list[dict[str, Any]], scene: "Scene") -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Threads and unmatched resolutions after the target turn: the scene's earlier promise at turn 0, the
    extracted assertions at turn 1, read by the thread fold (ADR 0019)."""
    prior = [promise_row(**p) for p in scene.promises]
    new = [{**a, "id": 100 + i, "position": 1, "turn": 1} for i, a in enumerate(items)
           if a["status"] == "valid" and a["predicate"] != "also_called"]
    rows = prior + new
    threads, unmatched, _ = fold(rows, resolve(uuid.uuid4(), rows))
    return threads, unmatched


def brief(threads, unmatched) -> str:
    return (f"threads={[(t['by'], t.get('to'), t['text'], t['status']) for t in threads]} "
            f"unmatched={[(u['subject'], u['predicate'], u['polarity'], u.get('value')) for u in unmatched]}")


def opened(maker: str):
    """A new open thread by `maker` (Q2)."""
    def check(items, scene):
        threads, unmatched = threads_after(items, scene)
        ok = any(t["status"] == "open" and norm(maker) in norm(t["by"]) for t in threads)
        return ok, brief(threads, unmatched)
    return check


def closed(status: str):
    """The scene's earlier promise ends with `status` (Q3)."""
    def check(items, scene):
        threads, unmatched = threads_after(items, scene)
        first = [t for t in threads if t["turn"] == 0]
        return bool(first) and first[0]["status"] == status, brief(threads, unmatched)
    return check


def untouched(items, scene):
    """Control: the earlier promise stays open and the turn states no resolution at all."""
    threads, unmatched = threads_after(items, scene)
    stated = [a for a in items if a["status"] == "valid" and resolves(a)]
    first = [t for t in threads if t["turn"] == 0]
    ok = bool(first) and first[0]["status"] == "open" and not stated
    return ok, brief(threads, unmatched) + f" resolutions={[(a['subject'], a['predicate'], a['value']) for a in stated]}"


def no_thread(items, scene):
    """A promise someone else reports opens nothing."""
    threads, unmatched = threads_after(items, scene)
    return not threads, brief(threads, unmatched)


def events_of(items) -> list[dict[str, Any]]:
    return [a for a in narrated(items) if a["predicate"] == "event"]


def salience_is(label: str):
    """Major scenes: some event labeled major. Minor scenes: events, none labeled major."""
    def check(items, scene):
        events = events_of(items)
        labels = [a.get("salience") for a in events]
        ok = (label in labels) if label == "major" else (bool(events) and "major" not in labels)
        return ok, f"events={[(a['subject'], a['value'], a.get('salience')) for a in events]}"
    return check


@dataclass
class Scene:
    name: str
    category: str  # open | kept | broken | released | control | reported | major | minor
    target: list[Line]
    context: list[list[Line]] = field(default_factory=list)
    hints: list[dict[str, str]] | None = None
    promises: list[dict[str, str]] = field(default_factory=list)  # earlier open promises (turn 0)
    check: Callable[[list[dict[str, Any]], "Scene"], tuple[bool, str]] | None = None

    def ctx(self) -> dict[str, Any]:
        rows = []
        for t, turn in enumerate(self.context):
            rows += [{"turn": t, "metadata": {"name": s or None, "role": r}, "content": x} for s, r, x in turn]
        target = len(self.context)
        members = [{"turn": target, "metadata": {"name": s or None, "role": r}, "content": x}
                   for s, r, x in self.target]
        return {"context": rows, "members": members, "target": {"turn": target}}

    def listed(self) -> list[dict[str, Any]]:
        """OPEN PROMISES as the worker shows them."""
        return [{"by": p["by"], "to": p["to"], "text": p["text"], "turn": 0} for p in self.promises]


def hint(*pairs: tuple[str, str]) -> list[dict[str, str]]:
    return [{"name": n, "type": t} for n, t in pairs]


LIGHTHOUSE = {"by": "하나", "to": USER, "text": "비가 그치면 내일 아침 등대 앞에서 만나기로 함"}
HOMETOWN = {"by": "카이토", "to": "유이", "text": "유이를 고향 마을까지 데려다주기"}
SECRET = {"by": "하나", "to": USER, "text": "그 비밀을 아무에게도 말하지 않기"}
RETURN = {"by": "카이토", "to": "유이", "text": "해가 지기 전에 돌아오기"}
LETTER = {"by": "유이", "to": "하나", "text": "하나의 편지를 대신 전해 주기"}
DAILY = {"by": USER, "to": "하나", "text": "매일 밤 편지 쓰기"}

SCENES: list[Scene] = [
    # --- a promise is made (Q2) ---------------------------------------------------------------------
    Scene("promise in dialogue", "open",
          target=[("", U, "내일 비가 그치면 우리 등대에 가 보자."),
                  ("", C, '하나는 창밖의 빗줄기를 보며 새끼손가락을 내밀었다. "좋아, 약속할게. 비가 그치면 내일 '
                          '아침에 등대 앞에서 만나."')],
          hints=hint(("하나", "character"), ("등대", "place")), check=opened("하나")),
    Scene("promise in narration", "open",
          target=[("", U, "유이는 무서워하고 있어."),
                  ("", C, "카이토는 유이의 손을 꼭 잡고, 무슨 일이 있어도 그녀를 고향 마을까지 무사히 데려다주겠다고 "
                          "맹세했다.")],
          hints=hint(("카이토", "character"), ("유이", "character")), check=opened("카이토")),
    Scene("conditional promise", "open",
          target=[("", U, "저도 기사가 될 수 있을까요?"),
                  ("", C, '카이토는 검을 들어 보였다. "내일 시험을 통과하면, 이 검을 너에게 주겠다. 약속하지."')],
          hints=hint(("카이토", "character")), check=opened("카이토")),
    # --- kept (Q3) --------------------------------------------------------------------------------
    Scene("kept: lighthouse", "kept", promises=[LIGHTHOUSE],
          context=[[("", U, "비가 그쳤다!"), ("", C, "하나는 창문을 열고 맑게 갠 하늘을 올려다보았다.")]],
          target=[("", U, "나는 아침 일찍 등대로 향한다."),
                  ("", C, '등대 앞에는 하나가 먼저 와서 기다리고 있었다. "약속대로 왔네." 하나가 환하게 웃으며 손을 '
                          '흔들었다.')],
          hints=hint(("하나", "character"), ("등대", "place")), check=closed("kept")),
    Scene("kept: hometown", "kept", promises=[HOMETOWN],
          context=[[("", U, "마을이 보여?"), ("", C, "언덕 너머로 작은 지붕들이 보이기 시작했다.")]],
          target=[("", U, "유이가 마을 입구에서 멈춰 선다."),
                  ("", C, '카이토는 유이를 마을 입구까지 데려다주었다. "약속한 대로, 고향에 도착했어." 유이는 눈물을 '
                          '글썽이며 고개를 끄덕였다.')],
          hints=hint(("카이토", "character"), ("유이", "character")), check=closed("kept")),
    # --- broken or withdrawn (Q3) -----------------------------------------------------------------
    Scene("broken: secret told", "broken", promises=[SECRET],
          context=[[("", U, "카이토가 왔어."), ("", C, "카이토가 문을 열고 들어왔다.")]],
          target=[("", U, "하나, 설마 그 얘기 하려는 건 아니지?"),
                  ("", C, "하나는 잠시 망설이다가, 결국 카이토에게 그 비밀을 모두 털어놓았다. 아무에게도 말하지 않겠다던 "
                          "약속은 그렇게 깨졌다.")],
          hints=hint(("하나", "character"), ("카이토", "character")), check=closed("broken")),
    Scene("broken: withdrawn", "broken", promises=[RETURN],
          context=[[("", U, "카이토, 어디 가?"), ("", C, "카이토는 망토를 걸치며 문 쪽으로 걸어갔다.")]],
          target=[("", U, "유이가 기다릴 텐데."),
                  ("", C, '카이토는 유이에게 고개를 숙였다. "미안해, 유이. 해가 지기 전에 돌아온다는 약속은 지킬 수 '
                          '없을 것 같아. 없던 걸로 해 줘."')],
          hints=hint(("카이토", "character"), ("유이", "character")), check=closed("broken")),
    # --- released by the recipient (Q3) -----------------------------------------------------------
    Scene("released: letter", "released", promises=[LETTER],
          target=[("", U, "유이가 편지를 들고 나서려 한다."),
                  ("", C, '하나가 유이를 불러 세웠다. "그 편지, 대신 전해 주지 않아도 돼. 내가 직접 건넬게. 약속은 '
                          '없던 걸로 하자."')],
          hints=hint(("하나", "character"), ("유이", "character")), check=closed("broken")),
    Scene("released: daily letters", "released", promises=[DAILY],
          target=[("", U, "오늘은 편지를 못 썼어. 미안해."),
                  ("", C, '하나는 고개를 저었다. "괜찮아. 이제 매일 밤 편지 쓰겠다는 약속, 안 지켜도 돼. 이렇게 '
                          '곁에 있잖아."')],
          hints=hint(("하나", "character")), check=closed("broken")),
    # --- controls: an open promise is not resolved -------------------------------------------------
    Scene("unrelated: dinner", "control", promises=[LIGHTHOUSE],
          target=[("", U, "배고프다. 뭐 먹을까?"),
                  ("", C, "하나는 여관 식당에서 따뜻한 수프를 두 그릇 주문했다. 창밖에는 여전히 비가 내리고 있었다.")],
          hints=hint(("하나", "character")), check=untouched),
    Scene("unrelated: forge", "control", promises=[HOMETOWN],
          target=[("", U, "검은 괜찮아?"),
                  ("", C, "카이토는 대장간에 들러 무뎌진 검날을 갈았다. 유이는 옆에서 불꽃을 구경했다.")],
          hints=hint(("카이토", "character"), ("유이", "character")), check=untouched),
    Scene("discussed: lighthouse", "control", promises=[LIGHTHOUSE],
          target=[("", U, "등대에서 만나기로 한 거 기억하지?"),
                  ("", C, '하나는 싱긋 웃었다. "당연하지. 비만 그치면 내일 아침이야. 잊을 리가 없잖아."')],
          hints=hint(("하나", "character"), ("등대", "place")), check=untouched),
    Scene("discussed: hometown", "control", promises=[HOMETOWN],
          target=[("", U, "유이가 불안해 보여."),
                  ("", C, '카이토가 유이의 어깨를 두드렸다. "고향까지 데려다준다는 약속, 잊지 않았어. 조금만 더 가면 '
                          '돼."')],
          hints=hint(("카이토", "character"), ("유이", "character")), check=untouched),
    # --- controls: a promise someone else reports -------------------------------------------------
    Scene("reported: rumor", "reported",
          target=[("", U, "무슨 소식 있어?"),
                  ("", C, '유이가 속삭였다. "들었어? 하나가 카이토한테 축제 날 같이 춤추자고 약속했대."')],
          hints=hint(("유이", "character"), ("하나", "character"), ("카이토", "character")), check=no_thread),
    Scene("reported: oath", "reported",
          target=[("", U, "기사단 분위기는 어때?"),
                  ("", C, '카이토가 말했다. "부단장이 왕에게 목숨을 걸고 충성하겠다고 맹세했다더군. 다들 그 이야기뿐이야."')],
          hints=hint(("카이토", "character")), check=no_thread),
    # --- event salience (Q4) ----------------------------------------------------------------------
    Scene("major: confession", "major",
          target=[("", U, "하나, 할 말 있다며?"),
                  ("", C, '하나는 떨리는 목소리로 말했다. "나… 너를 좋아해. 처음 만난 날부터 계속." 하나의 얼굴이 새빨갛게 '
                          '달아올랐다.')],
          hints=hint(("하나", "character")), check=salience_is("major")),
    Scene("major: betrayal", "major",
          target=[("", U, "유이를 지켜 줘!"),
                  ("", C, "카이토는 칼을 거두고 경비병들에게 유이를 넘겨주었다. 그는 처음부터 왕궁의 첩자였다.")],
          hints=hint(("카이토", "character"), ("유이", "character")), check=salience_is("major")),
    Scene("major: secret revealed", "major",
          target=[("", U, "그 목걸이는 뭐야?"),
                  ("", C, "유이는 목걸이의 문장을 보여 주며 자신이 십 년 전 사라진 왕녀라고 밝혔다. 방 안이 조용해졌다.")],
          hints=hint(("유이", "character")), check=salience_is("major")),
    Scene("major: death", "major",
          target=[("", U, "선장님!"),
                  ("", C, "늙은 선장은 마지막 숨을 몰아쉬고 하나의 품에서 눈을 감았다. 폭풍 속에서 그는 끝내 숨을 거두었다.")],
          hints=hint(("하나", "character")), check=salience_is("major")),
    Scene("minor: walk", "minor",
          target=[("", U, "산책하자."),
                  ("", C, "하나와 {{user}}는 강가를 따라 천천히 걸었다. 물새 몇 마리가 물 위를 떠다녔다.")],
          hints=hint(("하나", "character")), check=salience_is("minor")),
    Scene("minor: meal", "minor",
          target=[("", U, "아침 먹었어?"),
                  ("", C, "유이는 빵을 굽고 차를 끓여 식탁에 올렸다. 둘은 창가에 앉아 아침을 먹었다.")],
          hints=hint(("유이", "character")), check=salience_is("minor")),
    Scene("minor: chores", "minor",
          target=[("", U, "오늘 뭐 했어?"),
                  ("", C, "카이토는 마구간을 청소하고 말에게 여물을 주었다. 그리고 부러진 울타리를 고쳤다.")],
          hints=hint(("카이토", "character")), check=salience_is("minor")),
]


def v6_prompt() -> str:
    """The extract-v6 system prompt, formatted with the v6 registry, read from git history."""
    def source(path: str) -> str:
        return subprocess.run(["git", "-C", str(ROOT), "show", f"{V6_COMMIT}:{path}"], check=True,
                              capture_output=True, text=True).stdout
    ns: dict[str, Any] = {}
    exec(compile(source("apps/sidecar/src/nmos_sidecar/predicates.py"), "predicates_v6", "exec"), ns)
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
    system_v6 = v6_prompt()

    jobs: list[tuple[str, Any, int, str, str]] = []  # (variant, scene, run, system, user)
    for scene in SCENES:
        for run in range(args.runs):
            jobs.append(("v7", scene, run, system, build_prompt(scene.ctx(), scene.hints, scene.listed())))
    for scene in PHASE6_SCENES:  # the Phase 5 and Phase 6 bars, with extract-v7
        for run in range(args.runs):
            jobs.append(("v7-phase6", scene, run, system, build_prompt(scene.ctx(), scene.hints)))
    for scene in (s for s in PHASE6_SCENES if s.category == "control"):  # prompt tokens, one call each
        jobs.append(("v6", scene, 0, system_v6, build_prompt(scene.ctx(), scene.hints)))
        jobs.append(("v7-tokens", scene, 0, system, build_prompt(scene.ctx(), scene.hints)))

    def work(job):
        variant, scene, run, sys_prompt, user = job
        reply = call(args.url, args.model, sys_prompt, user, args.timeout)
        record = {"scene": scene.name, "category": scene.category, "variant": variant, "run": run,
                  "system_fingerprint": fingerprint(sys_prompt), "user": user, **reply}
        if variant in ("v7", "v7-phase6") and not reply.get("error"):
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
    errors = [f"{r['scene']}#{r['run']}: {r['error']}" for r in records if r.get("error")]

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

    v7, p6 = by_scene("v7"), by_scene("v7-phase6")

    def per(scenes: dict[str, dict[str, Any]], category: str) -> dict[str, str]:
        return {n: f"{s['pass']}/{s['runs']}" for n, s in scenes.items() if s["category"] == category}

    p6_runs = [r for r in records if r["variant"] == "v7-phase6"]
    controls = [a for r in p6_runs if r["category"] == "control" for a in r.get("assertions", [])
                if a["status"] == "valid" and a["predicate"] != "also_called"]
    destroyed_elsewhere = [(r["scene"], r["run"], a["subject"], a.get("value")) for r in p6_runs
                           if r["category"] in ("control", "damaged", "whereabouts", "loss")
                           for a in r.get("assertions", []) if a["predicate"] == "destroyed"]
    fulfilled_anywhere = [(r["scene"], r["run"], a["subject"], a.get("value")) for r in records
                          if r["variant"] == "v7-phase6" for a in r.get("assertions", [])
                          if a["predicate"] == "fulfilled"]
    labels = [a.get("salience") for r in records if r["variant"] in ("v7", "v7-phase6")
              for a in r.get("assertions", []) if a["predicate"] == "event" and a["status"] == "valid"]

    def mean_prompt(variant: str) -> float | None:
        vals = [r["usage"]["prompt_tokens"] for r in records if r["variant"] == variant and r["usage"].get("prompt_tokens")]
        return round(sum(vals) / len(vals), 1) if vals else None

    completion = [r["usage"]["completion_tokens"] for r in records if r["variant"] == "v7"
                  and r["usage"].get("completion_tokens")]
    return {
        "model": args.model, "url": args.url, "runs": args.runs, "calls": len(records), "errors": errors,
        "bars": {
            "opened": per(v7, "open"), "kept": per(v7, "kept"), "broken": per(v7, "broken"),
            "released": per(v7, "released"), "control_untouched": per(v7, "control"),
            "reported_no_thread": per(v7, "reported"), "salience_major": per(v7, "major"),
            "salience_minor": per(v7, "minor"),
            "phase6_end": per(p6, "end"), "phase6_damaged_intact": per(p6, "damaged"),
            "phase6_whereabouts": per(p6, "whereabouts"), "phase6_loss_not_end": per(p6, "loss"),
            "phase6_destroyed_outside_end_scenes": destroyed_elsewhere,
            "phase5_control_mislabel": {"assertions": len(controls),
                                        "non_actual": sum(a["modality"] != "actual" for a in controls)},
            "fulfilled_in_phase6_scenes": fulfilled_anywhere,
        },
        "report": {"event_salience_labels": {str(k): labels.count(k) for k in sorted(set(labels), key=str)}},
        "prompt_tokens_mean_controls": {"v6": mean_prompt("v6"), "v7": mean_prompt("v7-tokens")},
        "completion_tokens_mean_v7": round(sum(completion) / len(completion), 1) if completion else None,
        "scenes": {**{f"v7 {k}": v for k, v in v7.items()}, **{f"phase6 {k}": v for k, v in p6.items()}},
    }


if __name__ == "__main__":
    main()
