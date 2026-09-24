"""Deterministic RP memory evaluation (Track A, A5): packet-level checks over scripted host actions.

Every case is synthetic test data, not host evidence. The extractor and embedder are deterministic
stubs, so a result depends only on reconciliation, invalidation, retrieval and packet compilation, not
on a model. Measured on the packet the model would receive, never on a generated answer:

- gold: text that must reach the model (in the packet, or in the recent window for `recent`);
- stale: text that must never reach it (edited, deleted, rerolled or other-branch content, or a
  superseded fact line);
- irrelevant: a packet for a query nothing in the chat relates to should be empty.

Modes: `recent` (no memory: only the last RECENT messages), `lexical` (raw recall only), `hybrid`
(lexical + vectors), `full` (hybrid + facts from the stub extractor).

    uv run python ../../tools/eval_memory.py        # prints the table in docs/perf/eval-baseline.md
"""

from __future__ import annotations

import math
import re
import uuid
import zlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import psycopg
from psycopg.rows import dict_row

from nmos_sidecar.extraction import process_extract
from nmos_sidecar.vectors import process_embed
from nmos_sidecar.worker import run_once
from simchat import SimChat

RECENT = 6  # messages the host prompt still holds (in_context_ids); older ones need memory
MODES = ("recent", "lexical", "hybrid", "full")

# --- deterministic stand-ins ---------------------------------------------------------------------

RULES: list[tuple[re.Pattern[str], Callable[[re.Match[str]], dict[str, Any]]]] = [
    (re.compile(r"(?P<who>\w+) (?:is in|moved to) the (?P<where>\w+)\."),
     lambda m: {"subject": m["who"], "subject_type": "character", "predicate": "located_in",
                "object": m["where"], "object_type": "place"}),
    # Phase 6 (Q2): an item's place; a holder and a place stated in one turn.
    (re.compile(r"(?P<who>\w+) has the (?P<item>\w+) in the (?P<where>\w+)\."),
     lambda m: {"subject": m["who"], "subject_type": "character", "predicate": "possesses",
                "object": m["item"], "object_type": "item"}),
    (re.compile(r"\w+ has the (?P<item>\w+) in the (?P<where>\w+)\."),
     lambda m: {"subject": m["item"], "subject_type": "item", "predicate": "located_in",
                "object": m["where"], "object_type": "place"}),
    (re.compile(r"(?:[Tt]he|\w+ puts the) (?P<item>\w+) (?:is )?on the (?P<where>\w+)\."),
     lambda m: {"subject": m["item"], "subject_type": "item", "predicate": "located_in",
                "object": m["where"], "object_type": "place"}),
    # Phase 6 (Q3): an item's end. Damage ("The Y cracked.") has no rule, as the prompt asks.
    (re.compile(r"\w+ (?P<how>burns|eats) the (?P<item>\w+)\."),
     lambda m: {"subject": m["item"], "subject_type": "item", "predicate": "destroyed",
                "value": {"burns": "burned", "eats": "eaten"}[m["how"]]}),
    (re.compile(r"(?P<who>\w+) (?:has|takes|gets) the (?P<item>\w+)\."),
     lambda m: {"subject": m["who"], "subject_type": "character", "predicate": "possesses",
                "object": m["item"], "object_type": "item"}),
    (re.compile(r"(?P<who>\w+) keeps a secret from (?P<other>\w+): (?P<what>[^.]+)\."),
     lambda m: {"subject": m["who"], "subject_type": "character", "predicate": "knows", "value": m["what"],
                "knowledge": "limited", "hidden_from": [m["other"]]}),
    # Phase 5 (ADR 0013): negation, non-actual modality, a character's claim.
    (re.compile(r"(?P<who>\w+) (?:lost|does not have) the (?P<item>\w+)\."),
     lambda m: {"subject": m["who"], "subject_type": "character", "predicate": "possesses",
                "object": m["item"], "object_type": "item", "polarity": "negative"}),
    (re.compile(r"(?P<who>\w+) (?:did not enter|is not in) the (?P<where>\w+)\."),
     lambda m: {"subject": m["who"], "subject_type": "character", "predicate": "located_in",
                "object": m["where"], "object_type": "place", "polarity": "negative"}),
    (re.compile(r"If (?P<who>\w+) goes to the (?P<where>\w+),"),
     lambda m: {"subject": m["who"], "subject_type": "character", "predicate": "located_in",
                "object": m["where"], "object_type": "place", "modality": "hypothetical"}),
    (re.compile(r"(?P<who>\w+) dreamed (?:she|he) was in the (?P<where>\w+)\."),
     lambda m: {"subject": m["who"], "subject_type": "character", "predicate": "located_in",
                "object": m["where"], "object_type": "place", "modality": "dreamed"}),
    (re.compile(r"(?P<who>\w+) is a (?P<what>\w+)\."),
     lambda m: {"subject": m["who"], "subject_type": "character", "predicate": "identity", "value": m["what"]}),
    (re.compile(r'(?P<who>\w+) says: "I am a (?P<what>\w+)\."'),
     lambda m: {"subject": m["who"], "subject_type": "character", "predicate": "identity", "value": m["what"],
                "source": "character_claim", "asserted_by": m["who"]}),
]


def stub_extractor(system: str, user: str) -> tuple[dict, str]:
    target = user.split("TARGET", 1)[1]
    items = [{"modality": "actual", "source": "narration", **build(m), "epistemic": "stated", "confidence": 0.9,
              "evidence": m.group(0)}
             for pattern, build in RULES for m in pattern.finditer(target)]
    return {"assertions": items}, "{}"


CONCEPTS = [("열쇠", "key", "은빛"), ("등대", "lighthouse"), ("숨기", "hid", "감추", "숨겼")]


WORD_BUCKETS = 64


class StubEmbedder:
    """Concept-bag vectors plus weak hashed words: paraphrases that share a concept are close, texts
    without a shared concept or word are not (a constant component would make them all identical)."""

    def embed(self, texts, timeout_s):
        out = []
        for t in texts:
            words = [0.0] * WORD_BUCKETS
            for w in re.findall(r"\w+", t.lower()):
                words[zlib.crc32(w.encode()) % WORD_BUCKETS] += 0.3
            v = [1.0 if any(w in t.lower() for w in group) else 0.0 for group in CONCEPTS] + words
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / n for x in v])
        return out


# --- cases -----------------------------------------------------------------------------------------

Step = Callable[[dict[str, SimChat]], None]


@dataclass
class Case:
    name: str
    category: str
    steps: list[Step]  # each step is one host state; the plugin syncs after it
    query: str
    chat: str = "main"  # which chat the query is asked in
    gold: list[str] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)
    irrelevant: bool = False


def filler(chat: SimChat, n: int = 4) -> None:
    for i in range(n):
        chat.user(f"Idle chatter {uuid.uuid4().hex[:4]} about clouds {i}.")
        chat.reply(f"Idle reply about the weather {i}.")


def turn(user: str, reply: str = "Noted.") -> Step:
    def step(chats: dict[str, SimChat]) -> None:
        chats["main"].user(user)
        chats["main"].reply(reply)
    return step


def pad(n: int = 4) -> Step:
    return lambda chats: filler(chats["main"], n)


def act(fn: Callable[[SimChat], Any]) -> Step:
    return lambda chats: fn(chats["main"])


def branch_at(index: int) -> Step:
    def step(chats: dict[str, SimChat]) -> None:
        chats["branch"] = chats["main"].branch(index)
    return step


CASES: list[Case] = [
    Case("current state after moves", "current state",
         [turn("Hinata is in the chapel."), pad(), turn("Hinata moved to the harbor."), pad()],
         "Where is Hinata now?", gold=["Hinata located in harbor"], stale=["Hinata located in chapel"]),
    Case("history of a move", "historical state",
         [turn("Hinata is in the chapel."), pad(), turn("Hinata moved to the harbor."), pad()],
         "Was Hinata in the chapel before?", gold=["chapel"]),
    Case("item changes hands", "current state",
         [turn("Yujin has the map."), pad(2), turn("Hana takes the map."), pad(2), turn("Kaito gets the map."), pad()],
         "Who has the map now?", gold=["Kaito possesses map"], stale=["Yujin possesses map", "Hana possesses map"]),
    Case("edited message", "edit invalidation",
         [turn("Mina is in the tower."), pad(), act(lambda c: c.edit(1, "Mina is in the garden.")), pad(1)],
         "Where is Mina?", gold=["Mina located in garden"], stale=["tower"]),
    Case("deleted turn", "delete invalidation",
         [turn("The vault password is violet-seven."), pad(), act(lambda c: (c.delete(1), c.delete(1))), pad(1)],
         "What was the vault password?", stale=["violet-seven"]),
    Case("rerolled reply", "reroll invalidation",
         [turn("What does Ren carry?", "Ren has the sword."), act(lambda c: c.reroll("Ren has the shield.")), pad()],
         "What does Ren carry?", gold=["Ren possesses shield"], stale=["sword"]),
    Case("swipe back", "swipe invalidation",
         [turn("What does Ren carry?", "Ren has the sword."), act(lambda c: c.reroll("Ren has the shield.")),
          act(lambda c: c.swipe(0)), pad()],
         "What does Ren carry?", gold=["Ren possesses sword"], stale=["shield"]),
    Case("branch does not see the origin's later story", "branch isolation",
         [turn("Hinata is in the chapel."), pad(), branch_at(9),
          act(lambda c: (c.user("Hinata moved to the desert."), c.reply("Noted."))), pad(),
          lambda chats: filler(chats["branch"])],
         "Where is Hinata?", chat="branch", gold=["Hinata located in chapel"], stale=["desert"]),
    Case("exact quote", "exact quote",
         [turn("The vault password is violet-seven."), pad()],
         "What was the vault password?", gold=["violet-seven"]),
    Case("Korean paraphrase", "paraphrase recall",
         [turn("하나는 은빛 열쇠를 등대 지하에 숨겼다.", "그 비밀은 아무도 모른다."), pad()],
         "혹시 그 반짝이는 은빛 물건은 어디 숨겼지?", gold=["등대 지하에 숨겼다"]),
    Case("secret kept from someone", "soft knowledge",
         [turn("Hana keeps a secret from Kaito: the letter is forged."), pad()],
         "Kaito, what do you know about the letter?", gold=['hidden_from="Kaito"', "the letter is forged"]),
    Case("lost item", "negation",
         [turn("Hana has the map."), pad(2), turn("Hana lost the map."), pad()],
         "Who has the map now?", gold=['negated="true">Hana possesses map'],
         stale=['turn="1">Hana possesses map</Fact>']),
    Case("negated entry", "negation",
         [turn("Alice did not enter the hall."), pad()],
         "Did Alice go into the hall?", gold=['negated="true">Alice located in hall']),
    Case("negation of another place", "negation",
         [turn("Hinata is in the chapel."), pad(2), turn("Hinata is not in the harbor."), pad()],
         "Where is Hinata?", gold=['turn="1">Hinata located in chapel</Fact>']),
    Case("denial by a non-holder", "negation",
         [turn("Hana has the map."), pad(2), turn("Kaito does not have the map."), pad()],
         "Who has the map?", gold=['turn="1">Hana possesses map</Fact>']),
    Case("hypothetical and dream", "modality",
         [turn("Hinata is in the chapel."), pad(2), turn("If Hinata goes to the harbor, she will see the ship."),
          turn("Hinata dreamed she was in the desert."), pad()],
         "Where is Hinata?", gold=["Hinata located in chapel</Fact>"],
         stale=["Hinata located in harbor", "Hinata located in desert"]),
    Case("lie in dialogue", "source",
         [turn("Ren is a squire."), pad(2), turn('Ren says: "I am a knight."'), pad()],
         "What is Ren?", gold=["Ren identity: squire</Fact>", '<Claim by="Ren"'],
         stale=["Ren identity: knight</Fact>"]),
    Case("put down", "item whereabouts",
         [turn("Hana has the map."), pad(2), turn("Hana puts the map on the table."), pad()],
         "Where is the map now?", gold=["map located in table"], stale=["Hana possesses map"]),
    Case("picked up", "item whereabouts",
         [turn("The map is on the table."), pad(2), turn("Kaito takes the map."), pad()],
         "Where is the map now?", gold=["Kaito possesses map"], stale=["map located in table"]),
    Case("holder and place in one turn", "item whereabouts",
         [turn("Hana has the map in the library."), pad()],
         "Where is the map?", gold=["Hana possesses map", "map located in library"]),
    Case("a character's place is not an item's", "item whereabouts",
         [turn("Hana is in the library."), turn("Hana takes the map."), pad()],
         "Where is Hana, and does she have the map?", gold=["Hana located in library", "Hana possesses map"]),
    Case("destroyed", "item end",
         [turn("Hana has the letter."), pad(2), turn("Hana burns the letter."), pad()],
         "Where is the letter now?", gold=["letter destroyed: burned"], stale=["Hana possesses letter"]),
    Case("eaten", "item end",
         [turn("Ren has the apple."), pad(2), turn("Ren eats the apple."), pad()],
         "Does Ren still have the apple?", gold=["apple destroyed: eaten"], stale=["Ren possesses apple"]),
    Case("damaged, not destroyed", "item end",
         [turn("Ren has the sword."), pad(2), turn("The sword cracked."), pad()],
         "Who has the sword?", gold=["Ren possesses sword"]),
    Case("edit removes the end", "item end",
         [turn("Hana has the letter."), pad(2), turn("Hana burns the letter."),
          act(lambda c: c.edit(7, "Hana reads the letter.")), pad()],
         "Where is the letter now?", gold=["Hana possesses letter"], stale=["destroyed"]),
    Case("unrelated question", "irrelevant-memory suppression",
         [turn("Hinata is in the chapel."), pad()],
         "Tell me a joke about bananas.", irrelevant=True),
]


# --- runner ----------------------------------------------------------------------------------------

@dataclass
class Result:
    case: str
    category: str
    mode: str
    gold_hit: bool | None  # None: the case has no gold text
    stale_hit: list[str]
    irrelevant_leak: bool | None
    tokens: int
    lexical_mode: str | None


def _sync(client, chat: SimChat) -> None:
    manifest = chat.manifest()
    out = client.post("/v1/sync/reconcile", json=manifest).json()
    if out["status"] == "needs_bodies":
        res = client.post("/v1/sync/bodies", json={"chat_id": chat.id, "bodies": chat.bodies(out["needed_bodies"]),
                                                   "then_reconcile": manifest}).json()
        assert res["ok"], res
        out = res["reconcile"]
    assert out["status"] in ("applied", "noop"), out


def _drain(url: str, mode: str) -> None:
    from conftest import active_generation

    with psycopg.connect(url, row_factory=dict_row, autocommit=True) as conn:
        jobs = {}
        if mode in ("hybrid", "full"):
            gen = active_generation(conn, "embed")
            jobs["embed"] = (gen.key, lambda c, job, g=gen: process_embed(c, job, StubEmbedder(), g))
        if mode == "full":
            gen = active_generation(conn, "extract")
            jobs["extract"] = (gen.key, lambda c, job, g=gen: process_extract(c, job, stub_extractor, g,
                                                                               g.spec["context_turns"]))
        while jobs and run_once(conn, jobs):
            pass


def settings_for(mode: str) -> dict[str, Any]:
    out: dict[str, Any] = {"extract_backfill": 1000, "embed_backfill": 1000}
    if mode in ("hybrid", "full"):
        out.update(embed_url="http://stub-embed/v1", embed_model="stub-embed")
    if mode == "full":
        out.update(llm_url="http://stub-llm/v1", llm_model="stub")
    return out


def run_case(case: Case, mode: str, client, url: str) -> Result:
    chats = {"main": SimChat()}
    chats["main"].reply("Welcome to the story.")
    for step in case.steps:
        step(chats)
        for chat in chats.values():
            _sync(client, chat)
    chat = chats[case.chat]
    chat.user(case.query)
    _sync(client, chat)
    _drain(url, mode)
    recent = chat.messages[-RECENT:]
    if mode == "recent":
        seen = "\n".join(m.get("data", "") for m in recent[:-1])  # the question itself is not memory
        tokens, lexical_mode = 0, None
    else:
        out = client.post("/v1/retrieve", json={"chat_id": chat.id, "query": case.query,
                                                 "in_context_ids": [m["chatId"] for m in recent],
                                                 "budget_tokens": 600}).json()
        seen = out["packet"]["text"]
        tokens = out["packet"]["token_estimate"]
        lexical_mode = client.get(f"/v1/trace/{out['trace_id']}").json()["latency_ms"]["lexical_mode"]
    return Result(
        case=case.name, category=case.category, mode=mode,
        gold_hit=all(g in seen for g in case.gold) if case.gold else None,
        stale_hit=[s for s in case.stale if s in seen],
        irrelevant_leak=bool(seen.strip()) if case.irrelevant and mode != "recent" else None,
        tokens=tokens, lexical_mode=lexical_mode,
    )


def run_mode(mode: str, make_client: Callable[..., Any], url: str) -> list[Result]:
    """All cases in one migrated database (each case has its own chats)."""
    embedder = StubEmbedder() if mode in ("hybrid", "full") else None
    with make_client(url, embedder=embedder, **settings_for(mode)) as client:
        return [run_case(case, mode, client, url) for case in CASES]


def summary(results: list[Result]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for mode in MODES:
        rs = [r for r in results if r.mode == mode]
        gold = [r for r in rs if r.gold_hit is not None]
        irr = [r for r in rs if r.irrelevant_leak is not None]
        out[mode] = {
            "gold": f"{sum(r.gold_hit for r in gold)}/{len(gold)}",
            "stale": sum(bool(r.stale_hit) for r in rs),
            "irrelevant_leaks": f"{sum(r.irrelevant_leak for r in irr)}/{len(irr)}" if irr else "—",
            "tokens_mean": round(sum(r.tokens for r in rs) / max(1, len(rs))),
        }
    return out
