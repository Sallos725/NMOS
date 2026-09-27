"""Real-model tier of `extract-v12` (docs/phases/PHASE-10.md, ADR 0033): secrets.

Runs the sidecar's own extraction prompt and validation on short Korean scenes written for this evaluation,
several times each, against one OpenAI-compatible endpoint:

- kept: something is deliberately kept from a character → `hidden_from` names them;
- absent: a character is simply not there → nobody is `hidden_from`;
- private: a feeling nobody else is shown knowing → no `hidden_from`;
- reveal: a listed OPEN SECRET is found out → a `learned` that ends it (read by `secrets.fold`);
- control: a listed secret is talked about or suspected, not found out → nothing ends it.

The kept, absent and private scenes also run with the `extract-v11` prompt (read from git history) for
comparison. The scenes are synthetic test data, not a user's chat. Every prompt, raw reply and check result is
recorded.

    cd apps/sidecar && uv run python ../../tools/eval_v12_model.py \\
        --url http://127.0.0.1:11434/v1 --model gemma4:31b-cloud --runs 3 \\
        --out ../../fixtures/model/v12/2026-09-27-gemma4-31b
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
import types
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_extraction_model import ROOT, Line, call, norm  # noqa: E402

from nmos_sidecar.entities import resolve  # noqa: E402
from nmos_sidecar.extraction import SYSTEM_PROMPT, build_prompt, normalize, revealed  # noqa: E402
from nmos_sidecar.generations import fingerprint  # noqa: E402
from nmos_sidecar.llm import parse_json_object  # noqa: E402
from nmos_sidecar.predicates import DERIVED, registry_prompt  # noqa: E402
from nmos_sidecar.secrets import fold, secret_text  # noqa: E402

V11_COMMIT = "9b67912"  # main with extract-v11 (and clean-v3), before extract-v12
U, C = "user", "char"
USER = "{{user}}"


def valid(items):
    return [a for a in items if a["status"] == "valid"]


def hidden_names(items) -> set[str]:
    return {norm(n) for a in valid(items) for n in a.get("hidden_from") or ()}


def marks(items) -> str:
    return str([(a["subject"], a["predicate"], a.get("value"), a.get("known_by"), a.get("hidden_from"))
                for a in valid(items) if a.get("knowledge") == "limited"])


def kept_from(name: str):
    def check(items, scene):
        return norm(name) in hidden_names(items), marks(items)
    return check


def nobody_hidden(items, scene):
    return not hidden_names(items), marks(items)


def secret_row(s: dict[str, Any]) -> dict[str, Any]:
    """A listed secret as extraction stored it (turn 0)."""
    return {"id": 0, "position": 0, "turn": 0, "subject": s["subject"], "subject_type": "character",
            "predicate": s["predicate"], "object": None, "value": s["value"], "polarity": "positive",
            "modality": "actual", "source": "narration", "asserted_by": None, "status": "valid",
            "knowledge": "limited", "known_by": s["holders"], "hidden_from": s["kept_from"]}


def after(items, scene):
    rows = [secret_row(s) for s in scene.secrets]
    rows += [{**a, "id": 100 + i, "position": 1, "turn": 1} for i, a in enumerate(valid(items))
             if a["predicate"] != "also_called"]
    secrets, unmatched, _ = fold(rows, resolve(uuid.uuid4(), rows))
    first = [s for s in secrets if s["turn"] == 0]
    learned = [(a["subject"], a.get("value")) for a in valid(items) if a["predicate"] == "learned"]
    return first, f"open={[s['open'] for s in first]} learned={learned} unmatched={[u['value'] for u in unmatched]}"


def found_out(name: str):
    def check(items, scene):
        first, note = after(items, scene)
        return bool(first) and norm(name) not in {norm(n) for n in first[0]["open"]}, note
    return check


def still_secret(items, scene):
    first, note = after(items, scene)
    return bool(first) and first[0]["open"] == first[0]["kept_from"], note


@dataclass
class Scene:
    name: str
    category: str  # kept | absent | private | reveal | control
    target: list[Line]
    context: list[list[Line]] = field(default_factory=list)
    hints: list[dict[str, str]] | None = None
    secrets: list[dict[str, Any]] = field(default_factory=list)  # earlier open secrets (turn 0)
    check: Callable[[list[dict[str, Any]], "Scene"], tuple[bool, str]] | None = None

    def ctx(self) -> dict[str, Any]:
        rows = []  # turns start at 5: a listed secret (turn 0) is from earlier in the story
        for t, turn in enumerate(self.context, start=5):
            rows += [{"turn": t, "metadata": {"name": s or None, "role": r}, "content": x} for s, r, x in turn]
        target = 5 + len(self.context)
        members = [{"turn": target, "metadata": {"name": s or None, "role": r}, "content": x}
                   for s, r, x in self.target]
        return {"context": rows, "members": members, "target": {"turn": target}}

    def listed(self) -> list[dict[str, Any]]:
        """OPEN SECRETS as the worker shows them."""
        return [{"text": secret_text(secret_row(s)), "holders": s["holders"], "kept_from": s["kept_from"], "turn": 0}
                for s in self.secrets]


def hint(*pairs: tuple[str, str]) -> list[dict[str, str]]:
    return [{"name": n, "type": t} for n, t in pairs]


CAST = hint(("하나", "character"), ("카이토", "character"), ("유이", "character"))
PARTY = {"subject": "하나", "predicate": "goal", "value": "카이토 몰래 생일 파티 준비하기",
         "holders": ["하나", USER], "kept_from": ["카이토"]}
LIBRARY = {"subject": "유이", "predicate": "event", "value": "도서관에 있었다고 카이토에게 거짓말하고 하나를 만남",
           "holders": ["유이", "하나"], "kept_from": ["카이토"]}
PRINCESS = {"subject": "하나", "predicate": "identity", "value": "왕국의 공주",
            "holders": ["하나"], "kept_from": ["유이"]}

SCENES: list[Scene] = [
    # --- kept: something deliberately kept from someone -----------------------------------------------
    Scene("surprise kept", "kept", hints=CAST, check=kept_from("카이토"),
          target=[("", U, "하나는 뭘 그렇게 숨겨?"),
                  ("", C, '하나는 주위를 두리번거리더니 목소리를 낮췄다. "카이토한테는 절대 비밀이야. 내일이 카이토 생일이라, '
                          '몰래 깜짝 파티를 준비하고 있거든." 옆방에서 카이토가 책장을 넘기는 소리가 들렸다.')]),
    Scene("lie told", "kept", hints=CAST, check=kept_from("카이토"),
          target=[("", U, "유이, 어제 어디 있었어? 카이토가 찾던데."),
                  ("", C, '유이는 카이토를 흘끗 보고 태연하게 말했다. "도서관에 있었어." 하지만 사실 유이는 어제 하루 종일 '
                          '하나를 만나 몰래 선물을 고르고 있었다. 카이토는 고개를 끄덕였다.')]),
    Scene("hidden identity", "kept", hints=CAST, check=kept_from("유이"),
          target=[("", U, "하나 씨는 어디 출신이에요?"),
                  ("", C, '하나는 웃으며 "그냥 작은 시골 마을이에요."라고 둘러댔다. 유이 앞에서는 자신이 사실 이 왕국의 공주라는 '
                          '것을 끝까지 숨기기로 마음먹고 있었다.')]),
    # --- absent: nobody is hidden_from ----------------------------------------------------------------
    Scene("absent: at the market", "absent", hints=CAST, check=nobody_hidden,
          target=[("", U, "카이토는 시장에 갔으니까, 우리 먼저 빵을 굽자."),
                  ("", C, "하나는 반죽을 치대며 콧노래를 불렀다. 카이토가 시장에 간 사이, 두 사람은 오븐에 빵을 넣고 "
                          "처음으로 성공한 바게트를 꺼냈다.")]),
    Scene("absent: asleep", "absent", hints=CAST, check=nobody_hidden,
          target=[("", U, "유이는 아직 자?"),
                  ("", C, "유이가 곤히 자는 동안 하나는 조용히 방을 정리하고, 창가에 새 화분을 하나 들여놓았다.")]),
    Scene("absent: a talk without her", "absent", hints=CAST, check=nobody_hidden,
          target=[("", U, "하나랑 나는 벤치에 앉아 이야기를 나눴다."),
                  ("", C, "하나는 어릴 적 바닷가 마을에서 살았던 이야기를 해 주었다. 유이는 그 시간에 도서관에서 일을 하고 "
                          "있었다.")]),
    # --- private: a feeling nobody else knows, not hidden from anyone --------------------------------
    Scene("private feeling", "private", hints=CAST, check=nobody_hidden,
          target=[("", U, "카이토가 유이에게 꽃을 건넨다."),
                  ("", C, "하나는 웃으며 박수를 쳤지만, 속으로는 가슴 한구석이 따끔했다. 자신도 모르게 질투가 나는 것이 "
                          "이상했다.")]),
    Scene("private hope", "private", hints=CAST, check=nobody_hidden,
          target=[("", U, "유이는 창밖을 보며 뭔가 생각에 잠겼다."),
                  ("", C, "유이는 언젠가 이 도시를 떠나 바다 건너 학교에 가고 싶다고, 아무에게도 말하지 않은 꿈을 조용히 "
                          "떠올렸다.")]),
    # --- reveal: a listed secret is found out ---------------------------------------------------------
    Scene("reveal: sees the party", "reveal", hints=CAST, secrets=[PARTY], check=found_out("카이토"),
          target=[("", U, "카이토가 예정보다 일찍 돌아왔다."),
                  ("", C, '문을 연 카이토의 눈앞에 풍선과 "생일 축하해" 현수막이 걸린 거실이 펼쳐졌다. "이게 다 뭐야? 설마… '
                          '내 생일 파티?" 하나는 들고 있던 풍선을 놓치고 말았다.')]),
    Scene("reveal: confronted lie", "reveal", hints=CAST, secrets=[LIBRARY], check=found_out("카이토"),
          target=[("", U, "카이토가 유이를 불러 세웠다."),
                  ("", C, '"어제 도서관에 없었잖아. 하나랑 같이 있었지?" 카이토의 말에 유이는 결국 고개를 숙였다. "…응, '
                          '미안해. 하나랑 있었어."')]),
    Scene("reveal: overheard", "reveal", hints=CAST, secrets=[PRINCESS], check=found_out("유이"),
          target=[("", U, "유이가 복도를 지나간다."),
                  ("", C, '복도 모퉁이에서 경비병이 하나에게 무릎을 꿇었다. "공주님, 폐하께서 찾으십니다." 모퉁이 뒤에 서 '
                          '있던 유이는 그 말을 똑똑히 들었다. 하나가 공주였다니.')]),
    # --- control: talked about or suspected, not found out --------------------------------------------
    Scene("control: holders whisper", "control", hints=CAST, secrets=[PARTY], check=still_secret,
          target=[("", U, "카이토가 나간 사이, 하나랑 장식을 점검한다."),
                  ("", C, '"풍선은 이 정도면 됐고, 케이크는 내일 아침에 찾아오자." 하나는 속삭이며 현수막을 다시 상자에 '
                          '숨겼다. "카이토는 아무것도 몰라."')]),
    Scene("control: only suspicious", "control", hints=CAST, secrets=[PARTY], check=still_secret,
          target=[("", U, "카이토가 수상하다는 눈으로 하나를 본다."),
                  ("", C, '"요즘 둘이 뭔가 숨기는 거 있지?" 카이토가 눈을 가늘게 떴다. 하나는 "아무것도 아니야!"라며 손을 '
                          '내저었고, 카이토는 고개를 갸웃하며 방으로 들어갔다.')]),
]


def v11_prompt() -> str:
    """The extract-v11 system prompt, formatted with the v11 registry, read from git history."""
    def source(path: str) -> str:
        return subprocess.run(["git", "-C", str(ROOT), "show", f"{V11_COMMIT}:{path}"], check=True,
                              capture_output=True, text=True).stdout
    module = types.ModuleType("predicates_v11")
    sys.modules[module.__name__] = module  # dataclasses look their module up
    code = source("apps/sidecar/src/nmos_sidecar/predicates.py").replace("from .entities import node",
                                                                          "from nmos_sidecar.entities import node")
    exec(compile(code, "predicates_v11", "exec"), module.__dict__)
    ns = module.__dict__
    tree = ast.parse(source("apps/sidecar/src/nmos_sidecar/extraction.py"))
    prompt = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                  and getattr(n.targets[0], "id", None) == "SYSTEM_PROMPT")
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
    system_v11 = v11_prompt()
    jobs = []
    for scene in SCENES:
        for run in range(args.runs):
            jobs.append(("v12", scene, run, system, build_prompt(scene.ctx(), scene.hints, None, scene.listed())))
            if scene.category in ("kept", "absent", "private"):
                jobs.append(("v11", scene, run, system_v11, build_prompt(scene.ctx(), scene.hints)))

    def work(job):
        variant, scene, run, sys_prompt, user = job
        reply = call(args.url, args.model, sys_prompt, user, args.timeout)
        record = {"scene": scene.name, "category": scene.category, "variant": variant, "run": run, "prompt": user,
                  "reply": reply.get("text"), "usage": reply.get("usage"), "seconds": reply.get("seconds"),
                  "error": reply.get("error")}
        if not reply.get("error"):
            parsed = parse_json_object(reply["text"]) or {}
            text = "\n".join(x for _, _, x in scene.target)
            raw = [a for a in parsed.get("assertions") or [] if not (isinstance(a, dict) and a.get("predicate") in DERIVED)]
            items = normalize(raw + revealed(parsed, scene.listed(), text), text, scene.hints)
            ok, note = scene.check(items, scene)
            record.update({"assertions": items, "pass": ok, "note": note})
        return record

    with ThreadPoolExecutor(args.workers) as pool:
        records = list(pool.map(work, jobs))
    with (out / "runs.jsonl").open("w") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    summary = {"model": args.model, "url": args.url, "runs": args.runs,
               "prompt_fingerprint": fingerprint(SYSTEM_PROMPT), "errors": [
                   f"{r['variant']}:{r['scene']}#{r['run']}: {r['error']}" for r in records if r.get("error")],
               "scenes": {}}
    for r in records:
        key = f"{r['variant']} | {r['category']} | {r['scene']}"
        s = summary["scenes"].setdefault(key, {"pass": 0, "runs": 0, "notes": []})
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
