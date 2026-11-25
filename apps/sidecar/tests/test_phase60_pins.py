"""PHASE-60 step 2 (A1, A3): permanent pins for what Phase 60 must not move.

No later slice may change the expected literals in this module.
"""

from __future__ import annotations

from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from conftest import make_client
from memeval import _sync, settings_for
from nmos_sidecar import audit, canonfacts, extraction, packet, reveals, summaries, vectors
from nmos_sidecar.config import Settings
from nmos_sidecar.retrieval import RecallOptions
from test_packet_fill import secrets_chat
from test_packet_ledger import extract

BASE = dict(
    database_url="postgresql://x",
    llm_url="http://llm.test/v1",
    llm_model="model-a",
    embed_url="http://embed.test/v1",
    embed_model="embed-a",
    llm_json_mode=True,
    extract_turns=3,
    extract_hints=40,
    embed_max_chunks=8,
    summaries=True,
    canon_facts=True,
)

# Computed at 1b16ef6 for BASE. Literal strings, never recomputed.
PINNED = {
    "extract-v15": "extract-8ed39e6a2cf25ffae903b29d7ac9acd9",
    "extract-v16": "extract-029fac9f22f705a5130c70505c98ba49",
    "extract-v17": "extract-c98f66fc178127c0e3126c8503e4b8e9",
    "extract-v18": "extract-15d6e23accadb12ba64df5040859fc22",
    "default": "extract-029fac9f22f705a5130c70505c98ba49",  # extract_compiler="" is extract-v16
    "canon": "canon-5fb6b7fb622106e4949b20ab6e422366",
    "summarize": "summarize-9ff98c40c22744e5ec947542b77f9125",
    "reveal": "reveal-9b682161681128f8a06f7db566d54899",
    "embed": "embed-281e4c64319dfb23143ecedc3e2602a3",
}

PINNED_EXTRACT_SPEC_FIELDS = {
    "extract-v15": [
        "compiler", "context_chars", "context_turns", "endpoint", "hints", "json_mode",
        "kind", "model", "normalizer", "predicates", "prompt", "target_chars", "temperature", "unit",
    ],
    "extract-v16": [
        "aliases", "compiler", "confirm", "context_chars", "context_turns", "endpoint", "hints", "json_mode",
        "kind", "model", "normalizer", "predicates", "prompt", "target_chars", "temperature", "unit",
    ],
    "extract-v17": [
        "aliases", "compiler", "confirm", "context_chars", "context_turns", "endpoint", "hints", "json_mode",
        "kind", "model", "normalizer", "predicates", "prompt", "speakers", "target_chars", "temperature", "unit",
    ],
    "extract-v18": [
        "aliases", "compiler", "confirm", "context_chars", "context_turns", "endpoint", "hints", "json_mode",
        "kind", "model", "normalizer", "predicates", "prompt", "target_chars", "temperature", "unit",
    ],
}


def test_pinned_generation_keys_spec_fields_and_defaults():
    """A1: extractor keys (v15..v18), canon/summarize/reveal/embed keys, spec field sets, and code defaults."""
    base = Settings(**BASE)
    for compiler in ("extract-v15", "extract-v16", "extract-v17", "extract-v18"):
        gen = extraction.extractor(Settings(**BASE, extract_compiler=compiler))
        assert gen.key == PINNED[compiler], compiler
        assert sorted(gen.spec) == PINNED_EXTRACT_SPEC_FIELDS[compiler], compiler

    assert extraction.extractor(Settings(**BASE, extract_compiler="")).key == PINNED["default"]
    assert canonfacts.generation(base).key == PINNED["canon"]
    assert summaries.summarizer(base).key == PINNED["summarize"]
    assert reveals.generation(base).key == PINNED["reveal"]
    assert vectors.projection(base).key == PINNED["embed"]

    assert packet.DEFAULT_POLICY == "packet-v19"
    assert extraction.DEFAULT_COMPILER == "extract-v16"


# Literal membership of every *_POLICIES set in packet.py at 1b16ef6 (before packet-v20).
# PERMANENT: no v19-or-older policy may ever be added to or removed from any set.
PINNED_PRE_V20_POLICIES: dict[str, frozenset[str]] = {
    "PRIVATE_POLICIES": frozenset({
        "packet-v3", "packet-v4", "packet-v5", "packet-v6", "packet-v7", "packet-v8", "packet-v9",
        "packet-v10", "packet-v11", "packet-v12", "packet-v13", "packet-v14", "packet-v15",
        "packet-v16", "packet-v17", "packet-v18", "packet-v19",
    }),
    "FOLD_POLICIES": frozenset({
        "packet-v4", "packet-v5", "packet-v6", "packet-v7", "packet-v8", "packet-v9",
        "packet-v10", "packet-v11", "packet-v12", "packet-v13", "packet-v14", "packet-v15",
        "packet-v16", "packet-v17", "packet-v18", "packet-v19",
    }),
    "ABOUT_POLICIES": frozenset({
        "packet-v4", "packet-v5", "packet-v6", "packet-v7", "packet-v8", "packet-v9",
        "packet-v10", "packet-v11", "packet-v12", "packet-v13", "packet-v14", "packet-v15",
        "packet-v16", "packet-v17", "packet-v18", "packet-v19",
    }),
    "BEFORE_POLICIES": frozenset({
        "packet-v5", "packet-v6", "packet-v7", "packet-v8", "packet-v9",
        "packet-v10", "packet-v11", "packet-v12", "packet-v13", "packet-v14", "packet-v15",
        "packet-v16", "packet-v17", "packet-v18", "packet-v19",
    }),
    "CAUSE_POLICIES": frozenset({
        "packet-v6", "packet-v7", "packet-v8", "packet-v9",
        "packet-v10", "packet-v11", "packet-v12", "packet-v13", "packet-v14", "packet-v15",
        "packet-v16", "packet-v17", "packet-v18", "packet-v19",
    }),
    "TURN_POLICIES": frozenset({
        "packet-v7", "packet-v8", "packet-v9",
        "packet-v10", "packet-v11", "packet-v12", "packet-v13", "packet-v14", "packet-v15",
        "packet-v16", "packet-v17", "packet-v18", "packet-v19",
    }),
    "STORY_POLICIES": frozenset({
        "packet-v8", "packet-v9",
        "packet-v10", "packet-v11", "packet-v12", "packet-v13", "packet-v14", "packet-v15",
        "packet-v16", "packet-v17", "packet-v18", "packet-v19",
    }),
    "CAST_POLICIES": frozenset({
        "packet-v8", "packet-v9",
        "packet-v10", "packet-v11", "packet-v12", "packet-v13", "packet-v14", "packet-v15",
        "packet-v16", "packet-v17", "packet-v18", "packet-v19",
    }),
    "FILL_POLICIES": frozenset({
        "packet-v9", "packet-v10", "packet-v11", "packet-v12", "packet-v13", "packet-v14",
        "packet-v15", "packet-v16", "packet-v17", "packet-v18", "packet-v19",
    }),
    "GROW_POLICIES": frozenset({
        "packet-v10", "packet-v11", "packet-v12", "packet-v13", "packet-v14",
        "packet-v15", "packet-v16", "packet-v17", "packet-v18", "packet-v19",
    }),
    "SPAN_POLICIES": frozenset({
        "packet-v11", "packet-v12", "packet-v13", "packet-v14",
        "packet-v15", "packet-v16", "packet-v17", "packet-v18", "packet-v19",
    }),
    "CHANGE_POLICIES": frozenset({
        "packet-v12", "packet-v13", "packet-v14", "packet-v15",
        "packet-v16", "packet-v17", "packet-v18", "packet-v19",
    }),
    "QUOTE_POLICIES": frozenset({
        "packet-v13", "packet-v14", "packet-v15", "packet-v16", "packet-v17", "packet-v18", "packet-v19",
    }),
    "UNEXTRACTED_POLICIES": frozenset({
        "packet-v13", "packet-v14", "packet-v15", "packet-v16", "packet-v17", "packet-v18", "packet-v19",
    }),
    "LABEL_POLICIES": frozenset({
        "packet-v14", "packet-v15", "packet-v16", "packet-v17", "packet-v18", "packet-v19",
    }),
    "REST_POLICIES": frozenset({
        "packet-v14", "packet-v15", "packet-v16", "packet-v17", "packet-v18", "packet-v19",
    }),
    "ANCHOR_POLICIES": frozenset({
        "packet-v15", "packet-v16", "packet-v17", "packet-v18", "packet-v19",
    }),
    "NAMED_POLICIES": frozenset({
        "packet-v16", "packet-v17", "packet-v18", "packet-v19",
    }),
    "STATE_HISTORY_POLICIES": frozenset({
        "packet-v17", "packet-v18", "packet-v19",
    }),
    "PERSONA_QUESTION_POLICIES": frozenset({
        "packet-v18", "packet-v19",
    }),
    "STATUS_CHANGE_POLICIES": frozenset({
        "packet-v18", "packet-v19",
    }),
    "SOURCE_CLOCK_POLICIES": frozenset({
        "packet-v18", "packet-v19",
    }),
    "KEYWORD_PARTICLE_POLICIES": frozenset({
        "packet-v18", "packet-v19",
    }),
    "RELATED_FILL_POLICIES": frozenset({
        "packet-v19",
    }),
}


def test_v20_is_in_every_set_v19_is_in():
    """PERMANENT: every packet policy collection holding packet-v19 also holds packet-v20."""
    assert "packet-v20" in packet.POLICIES
    assert "packet-v20" in packet._V8
    assert packet.NON_ASCII["packet-v20"] == packet.NON_ASCII["packet-v19"]
    for name, policies in vars(packet).items():
        if name.endswith("_POLICIES") and "packet-v19" in policies:
            assert "packet-v20" in policies, name


def test_v19_and_older_are_untouched():
    """PERMANENT: members of every *_POLICIES set other than packet-v20 and packet-v21 stay exactly as at 1b16ef6."""
    for name in PINNED_PRE_V20_POLICIES:
        assert hasattr(packet, name), name
    for name, policies in vars(packet).items():
        if name.endswith("_POLICIES"):
            expected = PINNED_PRE_V20_POLICIES.get(name, frozenset())
            assert (policies - {"packet-v20", "packet-v21"}) == expected, name


def test_v20_compiles_like_v19(migrated):
    """Holds for a chat with none of Phase 60's triggers (no gone status, no return gap, no closed thread, no
    when_happened/told rows, no pins, no carry link, messages of 40 characters or more); later slices narrow the chat,
    never the comparison."""
    settings = {k: v for k, v in settings_for("full").items() if not k.startswith("embed_")} | {"embed_backfill": 0}
    queries = (
        "Kaito, what keys does Hana currently hold and what about those forged letters?",
        "What do you think the weather will be like tomorrow morning along the coast?",
        "What did Hana say earlier when she talked about the forged letters in the room?",
    )
    budgets = (2000, 8000)

    def run(policy: str) -> dict[tuple[str, int], str]:
        out: dict[tuple[str, int], str] = {}
        with make_client(migrated, **(settings | {"packet_policy": policy})) as client:
            chat = secrets_chat(client, migrated)
            for query in queries:
                chat.user(query)
                _sync(client, chat)
                extract(migrated)
                for budget in budgets:
                    res = client.post(
                        "/v1/retrieve",
                        json={
                            "chat_id": chat.id,
                            "query": query,
                            "previous_ai": "Hana smiled at Kaito.",
                            "in_context_ids": [m["chatId"] for m in chat.messages[-4:]],
                            "budget_tokens": budget,
                        },
                    )
                    assert res.status_code == 200, res.text
                    body = res.json()
                    assert client.get(f"/v1/trace/{body['trace_id']}").json()["policy"] == policy
                    out[(query, budget)] = body["packet"]["text"]
        return out

    v19, v20 = run("packet-v19"), run("packet-v20")
    assert all(v19.values())
    assert v20 == v19


def test_a_v19_trace_replays_the_same_under_v19_and_v20(migrated):
    """A3: a recorded packet-v19 trace replays unchanged with policy=None and identically with policy='packet-v20'."""
    settings = {k: v for k, v in settings_for("full").items() if not k.startswith("embed_")} | {"embed_backfill": 0}
    query = "Kaito, what keys does Hana currently hold and what about those forged letters?"
    with make_client(migrated, **(settings | {"packet_policy": "packet-v19"})) as client:
        chat = secrets_chat(client, migrated)
        chat.user(query)
        _sync(client, chat)
        res = client.post(
            "/v1/retrieve",
            json={
                "chat_id": chat.id,
                "query": query,
                "previous_ai": "Hana smiled at Kaito.",
                "in_context_ids": [m["chatId"] for m in chat.messages[-4:]],
                "budget_tokens": 2000,
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        recorded_text = body["packet"]["text"]
        trace_id = UUID(body["trace_id"])
        assert recorded_text

    options = RecallOptions()
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        same = audit.replay(conn, trace_id, options, policy=None)
        as_v20 = audit.replay(conn, trace_id, options, policy="packet-v20")
    assert same["status"] == "ok" and same["reproduced"] is True and same["text"] == recorded_text
    assert as_v20["status"] == "ok" and as_v20["policy"] == "packet-v20" and as_v20["text"] == recorded_text
