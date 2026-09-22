#!/usr/bin/env python3
"""Generate a synthetic PocketRisu chat export (risuChat v2) for the S14 large-chat scenario.

Import it through PocketRisu's chat import. PocketRisu assigns a new chat id on import and
normalizeChat() fills any missing message chatId, so the file deliberately omits chatIds.

The output is an S14 *input*, not host evidence. Evidence is what the spike records after import.
Standard library only.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

WORDS = (
    "lantern harbor archive winter oath letter garden bridge ember signal market tower river "
    "ledger compass orchard shrine violin cellar festival railway storm quartz meadow"
).split()


def sentence(rng: random.Random, n: int) -> str:
    return " ".join(rng.choice(WORDS) for _ in range(n)).capitalize() + "."


def build(count: int, seed: int) -> dict[str, object]:
    rng = random.Random(seed)
    messages = []
    for i in range(count):
        role = "user" if i % 2 == 0 else "char"
        body = " ".join(sentence(rng, rng.randint(6, 16)) for _ in range(rng.randint(1, 4)))
        messages.append({"role": role, "data": f"[synthetic turn {i}] {body}", "time": 1_700_000_000_000 + i * 1000})
    return {
        "type": "risuChat",
        "ver": 2,
        "data": {
            "message": messages,
            "note": "",
            "name": f"NMOS S14 synthetic {count}",
            "localLore": [],
            "fmIndex": -1,
        },
        "folders": [],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--messages", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=14)
    parser.add_argument("--output", default="nmos-s14-synthetic-chat.json")
    args = parser.parse_args()
    target = Path(args.output)
    target.write_text(json.dumps(build(args.messages, args.seed), ensure_ascii=False), encoding="utf-8")
    print(f"wrote {target} ({args.messages} messages, {target.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
