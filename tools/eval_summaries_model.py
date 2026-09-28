"""Real-model tier of `summarize-v2` (docs/phases/PHASE-12.md step 4, ADR 0042): scene summaries and the story so far.

Runs the sidecar's own summary prompts on short Korean scenes written for this evaluation, several times each,
against one OpenAI-compatible endpoint, and checks each reply:

- gold: every group of words names something the scene shows (one word of each group must appear);
- invented: none of these words, which name what the scene does not show, may appear;
- secret: a listed OPEN SECRET's content must not appear, neither by `summaries.leaks` (what the packet will
  enforce) nor by the listed words (a paraphrase the check does not catch);
- cap: the reply fits the stored cap without being cut.

The scenes are synthetic test data, not a user's chat. Every prompt, raw reply and check result is recorded.

    cd apps/sidecar && uv run python ../../tools/eval_summaries_model.py \\
        --url http://127.0.0.1:11434/v1 --model gemma4:31b-cloud --runs 3 --workers 2 \\
        --out ../../fixtures/model/summaries/2026-09-28-gemma4-31b
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_extraction_model import call, norm  # noqa: E402

from nmos_sidecar import summaries  # noqa: E402
from nmos_sidecar.generations import fingerprint  # noqa: E402
from nmos_sidecar.llm import parse_json_object  # noqa: E402

U, C = "user", "char"


@dataclass
class Scene:
    name: str
    category: str  # scene | secret | ooc | quiet | story
    turns: list[list[tuple[str, str, str]]] = field(default_factory=list)  # (speaker, role, text) per turn
    scenes: list[str] = field(default_factory=list)  # story: scene summaries in order
    secrets: list[dict[str, Any]] = field(default_factory=list)
    gold: list[list[str]] = field(default_factory=list)
    invented: list[str] = field(default_factory=list)
    secret_words: list[str] = field(default_factory=list)

    def prompt(self) -> tuple[str, str]:
        if self.category == "story":
            return summaries.STORY_PROMPT, summaries.story_prompt(
                [{"first_turn": 8 * i, "last_turn": 8 * i + 7, "text": t} for i, t in enumerate(self.scenes)])
        rows = [{"turn": t, "metadata": {"name": s or None, "role": r}, "content": x}
                for t, turn in enumerate(self.turns) for s, r, x in turn]
        w = summaries.Window(0, 0, len(self.turns) - 1, (), "")
        return summaries.SCENE_PROMPT, summaries.scene_prompt(rows, w, self.secrets)


def secret(holders: list[str], kept_from: list[str], text: str) -> dict[str, Any]:
    return {"text": text, "turn": 0, "position": 0, "holders": holders, "open": kept_from}


def check(scene: Scene, text: str, raw_len: int) -> tuple[bool, str]:
    body = norm(text)
    missing = [g for g in scene.gold if not any(norm(w) in body for w in g)]
    invented = [w for w in scene.invented if norm(w) in body]
    leaked = [s["text"] for s in summaries.leaks(text, scene.secrets)] + [w for w in scene.secret_words if norm(w) in body]
    cap = summaries.STORY_CHARS if scene.category == "story" else summaries.SCENE_CHARS
    notes = []
    if missing:
        notes.append(f"missing {missing}")
    if invented:
        notes.append(f"invented {invented}")
    if leaked:
        notes.append(f"secret {leaked}")
    if raw_len > cap:
        notes.append(f"over cap {raw_len}>{cap}")
    return not notes, "; ".join(notes) or "ok"


HANA, KAITO, YUI, LEON = "하나", "카이토", "유이", "레온"
LETTER = secret([HANA], [KAITO], "하나 knows: 서랍 속 편지는 하나가 위조한 것이다")
KISS = secret(["하나", "카이토"], ["소라"], "하나 event: 소라가 잠든 사이 카이토와 입을 맞췄다")

SCENES: list[Scene] = [
    Scene("market and the lighthouse", "scene", [
        [(HANA, U, "카이토, 시장 가자. 등대 문 열쇠를 새로 맞춰야 해."), (KAITO, C, "좋아. 은빛으로 하자.")],
        [(HANA, U, "대장간 아저씨한테 은빛 열쇠 하나 부탁했어."), (KAITO, C, "카이토가 돌길에서 미끄러져 무릎을 다쳤다.")],
        [(HANA, U, "괜찮아? 붕대 감아 줄게."), (KAITO, C, "카이토는 괜찮다며 웃었다.")],
        [(HANA, U, "열쇠 받았어. 이제 등대로 가자."), (KAITO, C, "둘은 해 질 무렵 등대로 향했다.")]],
        gold=[["열쇠"], ["등대"], ["무릎", "다쳤", "다친", "미끄러"]], invented=["고백", "키스", "싸웠", "죽"]),
    Scene("a forged letter kept from Kaito", "secret", [
        [(HANA, U, "카이토, 빵 반죽 같이 하자."), (KAITO, C, "카이토가 밀가루를 꺼냈다.")],
        [(HANA, U, "나 잠깐 물 좀 떠 올게."), (KAITO, C, "카이토가 우물로 나간 사이, 하나는 자기가 위조한 편지를 다시 읽고 서랍 깊숙이 넣었다.")],
        [(HANA, U, "왔어? 이제 굽자."), (KAITO, C, "둘은 빵을 오븐에 넣고 기다렸다.")],
        [(HANA, U, "잘 구워졌다!"), (KAITO, C, "카이토가 갓 구운 빵을 반으로 갈랐다.")]],
        secrets=[LETTER], gold=[["빵"]], invented=["고백", "싸웠"], secret_words=["위조", "편지"]),
    Scene("the secret is the scene", "secret", [
        [(KAITO, U, "소라 자?"), (HANA, C, "하나가 소라의 이불을 덮어 주고 고개를 끄덕였다.")],
        [(KAITO, U, "그럼… 잠깐 이리 와."), (HANA, C, "소라가 잠든 사이, 하나와 카이토는 부엌에서 입을 맞췄다.")],
        [(KAITO, U, "소라한테는 비밀이야."), (HANA, C, "하나는 대답 대신 카이토의 손을 꼭 잡았다.")],
        [(KAITO, U, "내일 아침은 수프 할게."), (HANA, C, "하나는 수프에 넣을 병을 꺼내 두었다.")]],
        secrets=[KISS], gold=[["수프"]], invented=["싸웠", "죽"], secret_words=["입을 맞", "입맞춤", "키스", "뽀뽀"]),
    Scene("a secret listed but not touched", "secret", [
        [(HANA, U, "오늘은 레온이랑 활 연습하기로 했어."), (LEON, C, "레온이 과녁을 세웠다.")],
        [(HANA, U, "세 발 연속 명중!"), (LEON, C, "레온은 하나에게 새 화살깃을 선물했다.")],
        [(HANA, U, "고마워. 내일도 하자."), (LEON, C, "레온은 내일 새벽에 다시 오겠다고 약속했다.")]],
        secrets=[LETTER], gold=[["활", "화살", "과녁"], ["약속", "다시 오", "내일"]], invented=["고백", "키스"],
        secret_words=["위조", "편지"]),
    Scene("an out-of-character note", "ooc", [
        [(HANA, U, "유이, 도서관에서 지도 찾았어?"), (YUI, C, "유이가 낡은 해도를 펼쳤다.")],
        [(HANA, U, "(OOC: 다음 장면은 전투로 부탁해요)"), (YUI, C, "(OOC: 알겠습니다!) 유이는 해도에 표시된 섬을 가리켰다.")],
        [(HANA, U, "저 섬으로 가자."), (YUI, C, "유이는 내일 배를 빌리자고 했다.")]],
        gold=[["해도", "지도"], ["섬"]], invented=["OOC", "전투로 부탁", "알겠습니다"]),
    Scene("a quiet afternoon", "quiet", [
        [(HANA, U, "차 마실래?"), (KAITO, C, "카이토가 찻잔 두 개를 꺼냈다.")],
        [(HANA, U, "오늘 바람이 차네."), (KAITO, C, "둘은 창밖의 비를 보며 말없이 차를 마셨다.")],
        [(HANA, U, "비 그치면 산책 가자."), (KAITO, C, "카이토는 고개를 끄덕였다.")]],
        gold=[["차"]], invented=["고백", "키스", "싸웠", "죽", "편지", "약속을 어"]),
    Scene("the story so far", "story", scenes=[
        "하나와 카이토는 시장에서 등대 문에 맞는 은빛 열쇠를 맞췄고, 카이토는 돌길에서 무릎을 다쳤다.",
        "등대에서 둘은 유이를 만났고, 유이는 낡은 해도에 표시된 섬 이야기를 했다.",
        "유이는 다음 날 배를 빌려 셋이 섬으로 가자고 했고, 하나는 새벽에 부두에서 만나기로 약속했다."],
        gold=[["열쇠"], ["해도", "지도"], ["섬"], ["약속", "부두", "새벽"]], invented=["키스", "죽", "싸웠", "배신"]),
    Scene("the story keeps the order", "story", scenes=[
        "레온은 과수원을 태우겠다고 하나를 위협했다.",
        "하나는 마을 사람들과 밤새 과수원을 지켰다.",
        "레온은 새벽에 마을을 떠났고, 과수원은 무사했다."],
        gold=[["과수원"], ["떠났", "떠나"], ["무사", "지켰", "지켜"]], invented=["불탔", "불에 탔", "죽"]),
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
    scenes = [s for s in SCENES if not args.only or s.name in args.only.split(",")]
    jobs = [(scene, run) for scene in scenes for run in range(args.runs)]

    def work(job):
        scene, run = job
        system, user = scene.prompt()
        reply = call(args.url, args.model, system, user, args.timeout)
        record = {"scene": scene.name, "category": scene.category, "run": run, "prompt": user,
                  "reply": reply.get("text"), "usage": reply.get("usage"), "seconds": reply.get("seconds"),
                  "error": reply.get("error")}
        if not reply.get("error"):
            parsed = parse_json_object(reply["text"]) or {}
            raw = parsed.get("summary") if isinstance(parsed.get("summary"), str) else ""
            text = summaries.reply_text(parsed, summaries.STORY_CHARS if scene.category == "story"
                                        else summaries.SCENE_CHARS) if raw else ""
            ok, note = check(scene, text, len(" ".join(raw.split()))) if raw else (False, "no summary")
            record.update({"summary": text, "pass": ok, "note": note,
                           "leak_score": [round(summaries.leak_score(s, text), 2) for s in scene.secrets]})
        return record

    with ThreadPoolExecutor(args.workers) as pool:
        records = list(pool.map(work, jobs))
    with (out / "runs.jsonl").open("w") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    summary = {"model": args.model, "url": args.url, "runs": args.runs, "version": summaries.VERSION,
               "prompt_fingerprint": fingerprint(summaries.SCENE_PROMPT + summaries.STORY_PROMPT),
               "errors": [f"{r['scene']}#{r['run']}: {r['error']}" for r in records if r.get("error")], "scenes": {}}
    for r in records:
        s = summary["scenes"].setdefault(f"{r['category']} | {r['scene']}", {"pass": 0, "runs": 0, "notes": []})
        s["runs"] += 1
        s["pass"] += 1 if r.get("pass") else 0
        s["notes"].append(r.get("note") or r.get("error"))
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    for key, s in summary["scenes"].items():
        print(f"{s['pass']}/{s['runs']}  {key}  {[n for n in s['notes'] if n != 'ok']}")
    if summary["errors"]:
        print("errors:", summary["errors"])


if __name__ == "__main__":
    main()
