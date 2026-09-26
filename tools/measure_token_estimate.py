"""The packet token estimate against real tokenizers (K26, ADR 0032). Read-only; synthetic text only.

Builds samples from the committed real-model fixtures (`fixtures/model/**/runs.jsonl`): fact lines
rendered from the recorded assertions as the packet renders them, grouped into packets of eight;
excerpt lines of two sentences of a scene's reply; prose (a reply, up to 480 characters); and mixed
packets (six facts and one excerpt). Each sample is counted by Ollama (`prompt_eval_count`, minus a
one-character baseline) and compared with each policy's estimate. Estimate / actual below 1 means the
estimate under-counts: the packet could be larger than the reserve.

    cd apps/sidecar && uv run python ../../tools/measure_token_estimate.py [--ollama http://127.0.0.1:11434]
        [--models qwen3-embedding:0.6b,gemma4:31b-cloud,deepseek-v4.1-flash:cloud] [--out report.json]

Embedding models are counted with /api/embed, the others with /api/generate (one token generated).
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import urllib.request
from pathlib import Path
from typing import Any

from nmos_sidecar.facts import fact_line
from nmos_sidecar.packet import (NON_ASCII, PACKET_CLOSE, PACKET_NOTE, PACKET_OPEN, Excerpt, estimate_tokens,
                                 excerpt_line, sentences)

ROOT = Path(__file__).resolve().parents[1]
MODELS = "qwen3-embedding:0.6b,gemma4:31b-cloud,deepseek-v4.1-flash:cloud"
PER_SET = 16


def fixture_text() -> tuple[list[str], list[str]]:
    """(replies, fact lines) from the recorded runs, deduplicated, in a stable order."""
    replies: dict[str, None] = {}
    facts: dict[str, None] = {}
    for path in sorted(glob.glob(str(ROOT / "fixtures/model/**/runs.jsonl"), recursive=True)):
        for raw in open(path, encoding="utf-8"):
            run = json.loads(raw)
            target = re.search(r"TARGET turn \d+:\n(.*)", run.get("user") or "", re.S)
            for line in (target.group(1).splitlines() if target else []):
                if line.startswith("CHARACTER: ") and len(line) > 60:
                    replies[line.removeprefix("CHARACTER: ")[:480]] = None
            body = re.search(r"\{.*\}", run.get("text") or "", re.S)
            try:
                data = json.loads(body.group(0)) if body else {}
            except ValueError:
                continue
            for a in data.get("assertions", []) if isinstance(data, dict) else []:
                try:
                    f = {**a, "value": str(a["value"]) if a.get("value") is not None else None,
                         "turn": 3, "position": 3}
                    facts[fact_line(f)] = None
                except (KeyError, TypeError, AttributeError):
                    continue
    return list(replies), list(facts)


def spread(items: list[Any], n: int) -> list[Any]:
    """n items spread over the list, so every fixture set contributes."""
    if len(items) <= n:
        return items
    step = len(items) / n
    return [items[int(i * step)] for i in range(n)]


def samples() -> dict[str, list[str]]:
    replies, facts = fixture_text()
    frame = lambda body: "\n".join([PACKET_OPEN, PACKET_NOTE, *body, PACKET_CLOSE])  # noqa: E731
    excerpts = [excerpt_line(Excerpt(turn=3, speaker="하나", text=" ".join(sentences(r)[:2]), score=0.0,
                                     revision_id="r")) for r in replies]
    groups = [facts[i : i + 8] for i in range(0, len(facts) - 7, 8)]
    return {
        "fact packets (8 lines)": [frame(["  <Facts>", *g, "  </Facts>"]) for g in spread(groups, PER_SET)],
        "excerpt lines": spread(excerpts, PER_SET),
        "prose (≤480 chars)": spread(replies, PER_SET),
        "mixed packets (6 facts + 1 excerpt)": [frame(["  <Facts>", *g[:6], "  </Facts>", e])
                                                for g, e in zip(spread(groups, PER_SET), spread(excerpts, PER_SET))],
    }


def post(url: str, body: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as res:
        return json.load(res)


def counter(ollama: str, model: str):
    embed = "embed" in model

    def raw(text: str) -> int:
        if embed:
            return post(f"{ollama}/api/embed", {"model": model, "input": text})["prompt_eval_count"]
        return post(f"{ollama}/api/generate", {"model": model, "prompt": text, "stream": False, "think": False,
                                               "options": {"num_predict": 1}})["prompt_eval_count"]
    base = raw("a") - 1  # template and special tokens
    return lambda text: raw(text) - base


def korean(text: str) -> int:
    return sum(1 for ch in text if ord(ch) >= 128)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ollama", default="http://127.0.0.1:11434")
    ap.add_argument("--models", default=MODELS)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    sets = samples()
    rates = {"packet-v1": NON_ASCII["packet-v1"], "packet-v2": NON_ASCII["packet-v2"]}
    report: dict[str, Any] = {"samples": {k: len(v) for k, v in sets.items()}, "models": {}}
    for model in args.models.split(","):
        count = counter(args.ollama, model)
        rows: dict[str, Any] = {}
        for name, texts in sets.items():
            actual = [count(t) for t in texts]
            row: dict[str, Any] = {"actual_tokens": sum(actual),
                                   "non_ascii_share": round(sum(map(korean, texts)) / sum(map(len, texts)), 2)}
            for policy, rate in rates.items():
                est = [estimate_tokens(t, rate) for t in texts]
                ratios = [e / a for e, a in zip(est, actual)]
                row[policy] = {"overall": round(sum(est) / sum(actual), 2), "worst_sample": round(min(ratios), 2),
                               "under_counted": sum(r < 1 for r in ratios)}
            rows[name] = row
            print(json.dumps({"model": model, "set": name, **row}, ensure_ascii=False))
        report["models"][model] = rows
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
