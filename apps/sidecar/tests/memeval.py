"""Deterministic RP memory evaluation (Track A, A5): packet-level checks over scripted host actions.

Every case is synthetic test data, not host evidence. The extractor and embedder are deterministic
stubs, so a result depends only on reconciliation, invalidation, retrieval and packet compilation, not
on a model. Measured on the packet the model would receive, never on a generated answer:

- gold: text that must reach the model (in the packet, or in the recent window for `recent`);
- stale: text that must never reach it (edited, deleted, rerolled or other-branch content, or a
  superseded fact line);
- irrelevant: a packet for a query nothing in the chat relates to should be empty.

Modes: `recent` (no memory: only the last RECENT messages), `lexical` (raw recall only), `hybrid`
(lexical + vectors), `full` (hybrid + facts from the stub extractor), `full-v0` (`full` compiled by
packet-v0, the packet compiler before Phase 9).

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
# `full-v0` is `full` with the packet compiler before Phase 9 (ADR 0027), kept for the comparison.
MODES = ("recent", "lexical", "hybrid", "full-v0", "full")

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
    # Phase 7: a promise said by its maker, one reported by someone else, a broken one, and events.
    (re.compile(r'(?P<who>\w+) says to (?P<to>\w+): "I promise to (?P<what>[^."]+)\."'),
     lambda m: {"subject": m["who"], "subject_type": "character", "predicate": "promised", "object": m["to"],
                "object_type": "character", "value": m["what"], "source": "character_claim", "asserted_by": m["who"]}),
    (re.compile(r'(?P<by>\w+) says: "(?P<who>\w+) promised (?P<to>\w+) to (?P<what>[^."]+)\."'),
     lambda m: {"subject": m["who"], "subject_type": "character", "predicate": "promised", "object": m["to"],
                "object_type": "character", "value": m["what"], "source": "character_claim", "asserted_by": m["by"]}),
    (re.compile(r"(?P<who>\w+) breaks the promise to (?P<to>\w+) to (?P<what>[^.]+)\."),
     lambda m: {"subject": m["who"], "subject_type": "character", "predicate": "promised", "object": m["to"],
                "object_type": "character", "value": m["what"], "polarity": "negative"}),
    (re.compile(r"(?P<who>\w+) kept the promise to (?P<what>[^.]+)\."),
     lambda m: {"subject": m["who"], "subject_type": "character", "predicate": "fulfilled", "value": m["what"]}),
    (re.compile(r"(?P<who>\w+) did chore (?P<n>\d+)\."),
     lambda m: {"subject": m["who"], "subject_type": "character", "predicate": "event", "value": f"chore {m['n']}",
                "salience": "minor"}),
    (re.compile(r"(?P<who>\w+) betrayed (?P<whom>\w+)\."),
     lambda m: {"subject": m["who"], "subject_type": "character", "predicate": "event",
                "value": f"betrayed {m['whom']}", "salience": "major",
                "with": [{"name": m["whom"], "type": "character"}]}),
    # ADR 0026/0028: speech level between two characters, and facts known by several.
    (re.compile(r"(?P<a>\w+) and (?P<b>\w+) agree to speak informally\."),
     lambda m: {"subject": m["a"], "subject_type": "character", "predicate": "addresses", "object": m["b"],
                "object_type": "character", "value": "informal speech"}),
    (re.compile(r"(?P<a>\w+) and (?P<b>\w+) agree to speak informally\."),
     lambda m: {"subject": m["b"], "subject_type": "character", "predicate": "addresses", "object": m["a"],
                "object_type": "character", "value": "informal speech"}),
    (re.compile(r"(?P<a>\w+) goes back to formal speech with (?P<b>\w+)\."),
     lambda m: {"subject": m["a"], "subject_type": "character", "predicate": "addresses", "object": m["b"],
                "object_type": "character", "value": "formal speech"}),
    (re.compile(r"(?P<who>\w+) knows, with (?P<a>\w+) and (?P<b>\w+), that (?P<what>[^.]+)\."),
     lambda m: {"subject": m["who"], "subject_type": "character", "predicate": "knows", "value": m["what"],
                "knowledge": "limited", "known_by": [m["a"], m["b"]]}),
    # Phase 9: long Korean traits and claims, to fill the packet budget the way real facts do.
    (re.compile(r"(?P<who>[가-힣]+)의 특징: (?P<what>[^.]+)\."),
     lambda m: {"subject": m["who"], "subject_type": "character", "predicate": "has_trait", "value": m["what"]}),
    (re.compile(r"(?P<who>[가-힣]+)의 주장: (?P<what>[^.]+)\."),
     lambda m: {"subject": m["who"], "subject_type": "character", "predicate": "has_trait", "value": m["what"],
                "source": "character_claim", "asserted_by": m["who"]}),
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


# Ten long traits of 하나 and two of her claims: as on real chats, fact lines alone fill a 600-token budget.
TRAITS: list[Step] = [turn(f"하나의 특징: {t}.") for t in (
    "비 오는 밤마다 등대 꼭대기에 올라가 바다를 오래 바라보는 버릇이 있다",
    "어릴 적 잃어버린 동생의 이름을 수첩 첫 장에 적어 두고 매일 한 번씩 읽는다",
    "거짓말을 할 때마다 왼손 약지에 낀 은반지를 무의식적으로 돌리는 습관이 있다",
    "항구 마을 사람들 사이에서는 폭풍을 미리 알아보는 사람으로 알려져 있다",
    "낯선 사람 앞에서는 존댓말을 쓰지만 화가 나면 곧바로 반말로 바뀐다",
    "검술보다 활을 더 잘 다루며 오른쪽 어깨에 오래된 화살 상처가 남아 있다",
    "매일 아침 해가 뜨기 전에 등대의 램프를 닦고 기름을 채워 넣는다",
    "단 음식을 싫어한다고 말하지만 몰래 꿀과자를 주머니에 넣고 다닌다",
    "아버지가 남긴 낡은 해도를 누구에게도 보여 주지 않고 침대 밑에 숨겨 두었다",
    "밤에 잠들지 못하면 부둣가를 따라 끝까지 걸어갔다가 돌아오는 버릇이 있다")] + [
    turn(f"하나의 주장: {t}.") for t in (
        "자신은 한 번도 등대 밖으로 나가 본 적이 없는 평범한 등대지기일 뿐이다",
        "바다 건너 왕국의 기사단에서 일한 적은 결코 없다고 여러 번 말했다")]


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
    Case("use after end", "conflict",
         [turn("Hana has the letter."), pad(2), turn("Hana burns the letter."), pad(2), turn("Hana has the letter."),
          pad()],
         "Where is the letter now?",
         gold=['disputed="true">Hana possesses letter; but turn ', "letter destroyed: burned</Fact>",
               "contradicts itself"],
         stale=['<Fact kind="destroyed"']),
    Case("promise recalled", "open thread",
         [turn('Hana says to Kaito: "I promise to meet you at the lighthouse."'),
          *[turn(f"Hana did chore {i}.") for i in range(12)], pad()],
         "Hana, long time no see.",
         gold=['<Thread kind="promise" by="Hana" to="Kaito"', "meet you at the lighthouse</Thread>",
               "A Thread is a promise"]),
    Case("reported promise", "open thread",
         [turn('Ren says: "Hana promised Kaito to return the book."'), pad()],
         "Hana, what about the book?", gold=['<Claim by="Ren" kind="promised"'], stale=["<Thread"]),
    Case("broken promise", "open thread",
         [turn('Hana says to Kaito: "I promise to meet you at the lighthouse."'), pad(2),
          turn("Hana breaks the promise to Kaito to meet you at the lighthouse."), pad()],
         "Hana, what about Kaito?", stale=["<Thread", "meet you at the lighthouse</Fact>"]),
    Case("kept promise", "open thread",
         [turn('Hana says to Kaito: "I promise to meet you at the lighthouse."'), pad(2),
          turn("Hana kept the promise to meet you at the lighthouse."), pad()],
         "Hana, what about Kaito?", stale=["<Thread", "lighthouse</Fact>", "lighthouse</Claim>"]),
    Case("edit removes the break", "open thread",
         [turn('Hana says to Kaito: "I promise to meet you at the lighthouse."'), pad(2),
          turn("Hana breaks the promise to Kaito to meet you at the lighthouse."),
          act(lambda c: c.edit(7, "Hana waits.")), pad()],
         "Hana, what about Kaito?", gold=['<Thread kind="promise" by="Hana"']),
    Case("delete removes the promise", "open thread",
         [turn('Hana says to Kaito: "I promise to meet you at the lighthouse."'), pad(2),
          act(lambda c: c.delete(1)), pad()],
         "Hana, what about Kaito?", stale=["<Thread", "lighthouse"]),
    Case("events leave room", "event salience",
         [turn("Hana is a knight."), *[turn(f"Hana did chore {i}.") for i in range(12)], pad()],
         "Hana?", gold=["Hana identity: knight</Fact>"]),
    Case("major event first", "event salience",
         [turn("Hana betrayed Kaito."), *[turn(f"Hana did chore {i}.") for i in range(12)], pad()],
         "Hana?", gold=["Hana event: betrayed Kaito</Fact>"], stale=["Hana event: chore"]),
    Case("addressed participant", "event participants",
         [turn("Hana betrayed Kaito."), *[turn(f"Hana did chore {i}.") for i in range(12)], pad()],
         "Kaito, long time no see.", gold=["Hana event: betrayed Kaito</Fact>"]),
    Case("speech level in a crowded scene", "standing facts",
         [turn("Hana and Ren agree to speak informally."),
          *[turn(f"Hana knows, with Mina and Kaito, that detail {i} of the harbor matters.") for i in range(10)], pad()],
         "Hana, Mina and Kaito come in together.", gold=["Hana addresses Ren: informal speech</Fact>"]),
    Case("speech level changed back", "standing facts",
         [turn("Hana and Ren agree to speak informally."), pad(2), turn("Hana goes back to formal speech with Ren."),
          pad()],
         "Hana, how do you talk to Ren?", gold=["Hana addresses Ren: formal speech</Fact>"],
         stale=["Hana addresses Ren: informal speech"]),
    Case("quote under a full budget", "budget pressure",
         [turn("하나가 주위를 살피더니 속삭였다. 금고 비밀번호는 보라일곱이야."), *TRAITS, pad()],
         "하나야, 금고 비밀번호가 뭐였지?", gold=["보라일곱", "하나 has trait:"]),
    Case("one line of a long message", "budget pressure",
         [turn("하나는 창가에 앉아 오래 말이 없었다. 바람이 커튼을 흔들었다. 찻잔은 이미 식어 있었다. "
               "한참 뒤에야 하나가 입을 열었다. 금고 비밀번호는 보라일곱이야. 그러고는 다시 창밖만 바라보았다. "
               "멀리서 종소리가 울렸다. 둘 다 그 소리를 세지 않았다."), *TRAITS, pad()],
         "하나야, 금고 비밀번호가 뭐였지?", gold=["보라일곱", "하나 has trait:"]),
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

    mode = kind(mode)
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


def kind(mode: str) -> str:
    """The recall setup of a mode: `full-v0` gathers like `full` and differs only in the packet compiler."""
    return "full" if mode.startswith("full") else mode


def settings_for(mode: str) -> dict[str, Any]:
    out: dict[str, Any] = {"extract_backfill": 1000, "embed_backfill": 1000,
                           "packet_policy": "packet-v0" if mode == "full-v0" else "packet-v1"}
    mode = kind(mode)
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
    embedder = StubEmbedder() if kind(mode) in ("hybrid", "full") else None
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
