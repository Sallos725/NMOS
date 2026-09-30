"""extract-v14 (PHASE-19, ADR 0054): context messages cut at 1,000 characters, synthetic prompt examples, and an
assertion of a turn extraction parked when its quote is not in the target turn."""

from __future__ import annotations

import psycopg
from psycopg.rows import dict_row

from conftest import make_client
from nmos_sidecar import canonfacts, extraction
from nmos_sidecar.config import Settings
from nmos_sidecar.extraction import normalize, revealed
from nmos_sidecar.predicates import REGISTRY, registry_prompt
from simchat import SimChat
from test_canon_facts import Model, canon_texts, push, story
from test_canon_facts import drain as drain_canon
from test_extraction import FACT, drain
from test_generations import LLM
from test_sidecar_integration import sync

SETTINGS = Settings(database_url="", llm_url="http://x/v1", llm_model="y", canon_facts=True, extract_turns=3,
                    extract_hints=40, llm_json_mode=True)
# The generations' specs under extract-v13 for SETTINGS (before PHASE-19).
V13_EXTRACT = {"kind": "extract", "endpoint": "http://x/v1", "model": "y", "compiler": "extract-v13",
               "prompt": "a0de52e41b72df2c", "predicates": "a6511d2d7b4e2fca", "normalizer": "clean-v3",
               "json_mode": True, "temperature": 0, "unit": "turn", "context_turns": 3, "target_chars": 6000,
               "context_chars": 2000, "hints": 40}
V13_CANON = {"kind": "canon", "endpoint": "http://x/v1", "model": "y", "version": "canon-v1",
             "prompt": "c084747d55328ce7", "predicates": "920807f41b347b88", "normalizer": "clean-v3",
             "json_mode": True, "temperature": 0, "part_chars": 6000, "max_parts": 4}

TURN = "하나가 카이토에게 등대 열쇠를 건네주었다. 카이토는 고개를 끄덕였다."
CONTEXT = "유이는 어젯밤 항구의 창고에서 낡은 지도를 찾아냈다."


def item(evidence: str | None, predicate: str = "event", **extra) -> dict:
    return {"subject": "하나", "subject_type": "character", "predicate": predicate, "value": "열쇠를 건넴",
            "epistemic": "stated", "confidence": 0.9, "evidence": evidence, "modality": "actual", "source": "narration",
            "knowledge": "public", **extra}


def test_a_context_message_is_cut_at_1000_characters_and_the_target_is_not():
    assert extraction.CONTEXT_CHARS == 1000 and extraction.TARGET_CHARS == 6000
    old, new = "가" * 1500, "나" * 1500
    ctx = {"target": {"turn": 5}, "context": [{"turn": 4, "metadata": {"role": "char"}, "content": old}],
           "members": [{"turn": 5, "metadata": {"role": "char"}, "content": new}]}
    prompt = extraction.build_prompt(ctx)
    assert "가" * 1000 in prompt and "가" * 1001 not in prompt
    assert "나" * 1500 in prompt
    assert extraction.coverage_of(ctx)["context_truncated"] == 1


def test_the_prompt_examples_use_only_synthetic_names():
    prompt = extraction.SYSTEM_PROMPT.format(registry=registry_prompt())
    assert "e.g. \"노엘에게만 우산을 빌려줘서\"" in prompt
    assert "\"반말, '타쿠미'라고 부름\", \"존댓말(해요체), '타쿠미 씨'라고\n  부름\"" in prompt
    assert "calls them 'Takumi'" in REGISTRY["addresses"].description
    assert "calls them 'Takumi'" in canonfacts.PROMPT.format(registry=registry_prompt(canonfacts.PREDICATES))


def test_a_quote_found_in_the_target_turn_keeps_the_assertion_valid():
    [row] = normalize([item("하나가 카이토에게 등대 열쇠를 건네주었다")], TURN, check_evidence=True)
    assert (row["status"], row["reason"]) == ("valid", None)


def test_a_quote_found_only_in_a_context_turn_parks_the_assertion():
    [row] = normalize([item(CONTEXT)], TURN, check_evidence=True)
    assert (row["status"], row["reason"]) == ("pending", "evidence not in the turn")
    assert row["evidence"] == CONTEXT  # stored as it came, for audit


def test_a_short_quote_and_a_row_without_a_quote_are_unchanged():
    short = "창고에서 지도를"  # under EVIDENCE_MIN_CHARS: trigram containment would pass or fail by accident
    assert len(short) < extraction.EVIDENCE_MIN_CHARS
    rows = normalize([item(short), item(None), item("")], TURN, check_evidence=True)
    assert [(r["status"], r["reason"]) for r in rows] == [("valid", None)] * 3


def test_without_the_check_a_quote_not_in_the_turn_is_unchanged():
    [row] = normalize([item(CONTEXT)], TURN)
    assert (row["status"], row["reason"]) == ("valid", None)


def test_a_row_already_parked_keeps_its_own_reason():
    [row] = normalize([item(CONTEXT, predicate="resolved")], TURN, check_evidence=True)
    assert (row["status"], row["reason"]) == ("pending", "resolved without an outcome")


def test_a_reveal_behaves_as_before():
    listed = [{"text": "루카 goal: 등대 열쇠를 숨기기", "holders": ["루카"], "kept_from": ["카이토"], "turn": 2}]
    answer = {"secrets": [{"secret": "S1", "found_out_by": ["카이토"], "evidence": "카이토에게 등대 열쇠를 건네주었다"}]}
    items = revealed(answer, listed, TURN)
    assert [(r["status"], r["predicate"]) for r in normalize(items, TURN, check_evidence=True)] == [("valid", "learned")]
    answer["secrets"][0]["evidence"] = CONTEXT  # evidence outside the turn: no reveal, as before
    assert revealed(answer, listed, TURN) == []


def test_the_turn_worker_parks_a_quote_from_a_context_turn(migrated):
    def complete(system: str, user: str):
        # A model that restates a CONTEXT fact as the TARGET turn's, quoting the context.
        items = [{"subject": m["who"], "subject_type": "character", "predicate": "located_in", "object": m["where"],
                  "object_type": "place", "epistemic": "stated", "confidence": 0.9, "evidence": m.group(0),
                  "modality": "actual"} for m in FACT.finditer(user)]
        return {"assertions": items}, "{}"

    with make_client(migrated, **LLM) as c:
        chat = SimChat()
        chat.reply("Welcome to the village.")
        chat.user("I walk to the chapel.")
        chat.reply("Akari is in the old chapel.")
        chat.user("I wait by the door.")
        chat.reply("The wind blows through the square.")
        chat.user("I keep waiting.")
        sync(c, chat)
        drain(migrated, complete)
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        rows = conn.execute("SELECT am.turn, a.status, a.reason FROM assertion a JOIN extraction e ON e.id = a.extraction_id"
                            " JOIN active_membership am ON am.source_revision_id = e.source_revision_id"
                            " AND am.turn_hash = e.window_hash ORDER BY am.turn").fetchall()
    # Turn 1 states it; turn 2's extraction quotes turn 1 from its CONTEXT.
    assert [(r["turn"], r["status"], r["reason"]) for r in rows] == [
        (1, "valid", None), (2, "pending", "evidence not in the turn")]


def test_a_canon_read_does_not_apply_the_check(migrated):
    class Elsewhere(Model):
        def __call__(self, system: str, user: str):
            parsed, raw = super().__call__(system, user)
            if "CANON" in system:  # every canon fact quotes words its text does not hold
                parsed["assertions"] = [{**a, "evidence": "a quote that is found nowhere at all"}
                                        for a in parsed["assertions"]]
            return parsed, raw

    chat, model = story(), Elsewhere()
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        push(c, chat, canon_texts())
        drain_canon(migrated, model)
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        rows = conn.execute("SELECT a.status FROM assertion a JOIN extraction e ON e.id = a.extraction_id"
                            " WHERE e.extractor_key LIKE 'canon-%' AND a.predicate = 'identity'").fetchall()
    assert rows and all(r["status"] == "valid" for r in rows)


def test_the_extractor_generation_changes_and_canon_only_by_its_predicates():
    ex = extraction.extractor(SETTINGS).spec
    assert extraction.COMPILER_VERSION == "extract-v14"
    changed = {k for k in V13_EXTRACT if ex[k] != V13_EXTRACT[k]}
    assert changed == {"compiler", "prompt", "predicates", "context_chars"} and ex["context_chars"] == 1000
    canon = canonfacts.generation(SETTINGS).spec
    assert {k for k in V13_CANON if canon[k] != V13_CANON[k]} == {"predicates"}  # the addresses description (Q2)
