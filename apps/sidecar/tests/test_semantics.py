"""Phase 5, ADR 0013 (and the alias rule of ADR 0012): polarity, modality, source, `also_called`."""

from __future__ import annotations

import shutil
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from conftest import active_generation, make_client
from nmos_sidecar import extraction
from nmos_sidecar.migrate import apply_migrations, migrations_dir
from nmos_sidecar.predicates import alias_evidenced, registry_prompt, semantics
from simchat import SimChat
from test_extraction import drain
from test_generations import LLM
from test_sidecar_integration import sync


# --- validation (pure) ---------------------------------------------------------------------------

def test_polarity_is_negative_only_when_stated():
    assert semantics({"polarity": "negative"})[0] == "negative"
    assert [semantics(i)[0] for i in ({}, {"polarity": "NEG"}, {"polarity": None})] == ["positive"] * 3


def test_modality_outside_the_coarse_set_is_unknown():
    for value in ("actual", "hypothetical", "dreamed", "unknown"):
        assert semantics({"modality": value})[1] == value
    # Missing or unrecognised modality never defaults to actual (ADR 0013, item 1).
    assert [semantics(i)[1] for i in ({}, {"modality": "claimed"}, {"modality": "observed"})] == ["unknown"] * 3


def test_source_follows_the_speaker():
    assert semantics({"source": "narration"})[2:5] == ("narration", None, None)
    assert semantics({})[2:5] == ("narration", None, None)
    assert semantics({"asserted_by": "카이토"})[2:5] == ("character_claim", "카이토", None)
    assert semantics({"source": "character_claim", "asserted_by": " 유이 "})[2:5] == ("character_claim", "유이", None)
    # A claim nobody made is not a claim: pending, with the reason.
    assert semantics({"source": "character_claim"})[2:5] == ("character_claim", None, "character_claim without asserted_by")
    # Narration has no speaker, even if the model names one.
    assert semantics({"source": "narration", "asserted_by": "하나"})[2:5] == ("narration", None, None)


def test_alias_needs_both_names_in_the_turn():
    item = {"predicate": "also_called", "subject": "하나", "value": "Hana"}
    assert alias_evidenced(item, "USER: 안녕, 하나(Hana)!")
    assert not alias_evidenced(item, "USER: 안녕, 하나!")
    assert not alias_evidenced({**item, "value": ""}, "하나(Hana)")
    assert alias_evidenced({**item, "subject": "HANA", "value": "하나"}, "하나 (hana)")


# --- extraction stores the fields ----------------------------------------------------------------

def semantic_complete(system: str, user: str) -> tuple[dict, str]:
    target = user.split("TARGET", 1)[1]
    items = []
    if "lost the map" in target:
        items.append({"subject": "Hana", "subject_type": "character", "predicate": "possesses", "object": "map",
                      "object_type": "item", "polarity": "negative", "modality": "actual", "source": "narration"})
    if "dreamed" in target:
        items.append({"subject": "Hana", "subject_type": "character", "predicate": "located_in", "object": "harbor",
                      "object_type": "place", "modality": "dreamed", "source": "narration"})
    if "I am a knight" in target:
        items.append({"subject": "Kaito", "subject_type": "character", "predicate": "identity", "value": "knight",
                      "modality": "actual", "source": "character_claim", "asserted_by": "Kaito"})
    if "also known as" in target:
        items.append({"subject": "Hana", "subject_type": "character", "predicate": "also_called", "value": "하나",
                      "modality": "actual"})
        items.append({"subject": "Hana", "subject_type": "character", "predicate": "also_called", "value": "Hanako",
                      "modality": "actual"})
    return {"assertions": items}, "{}"


def test_extraction_stores_polarity_modality_source_and_checks_aliases(migrated, db):
    chat = SimChat()
    chat.user("Hana lost the map.")
    chat.reply("It is gone.")
    chat.user("Hana dreamed of the harbor.")
    chat.reply("Waves.")
    chat.user('Kaito says: "I am a knight."')
    chat.reply("Nobody believes him.")
    chat.user("Hana, also known as 하나, waves.")
    chat.reply("She smiles.")
    chat.user("next")
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        drain(migrated, semantic_complete)
    assert active_generation(db, "extract").spec["compiler"] == "extract-v5"
    rows = db.execute("SELECT predicate, value, polarity, modality, source, asserted_by, status, reason"
                      " FROM assertion ORDER BY id").fetchall()
    # The worker takes the newest turn first, so compare regardless of insertion order.
    got = sorted((r["predicate"], r["polarity"], r["modality"], r["source"], r["asserted_by"], r["status"]) for r in rows)
    assert got == sorted([
        ("possesses", "negative", "actual", "narration", None, "valid"),
        ("located_in", "positive", "dreamed", "narration", None, "valid"),
        ("identity", "positive", "actual", "character_claim", "Kaito", "valid"),
        ("also_called", "positive", "actual", "narration", None, "valid"),
        ("also_called", "positive", "actual", "narration", None, "pending"),
    ])
    assert [r["reason"] for r in rows if r["status"] == "pending"] == ["alias not stated in the turn"]


def test_existing_assertions_read_as_legacy_narration(database_url, tmp_path):
    before = tmp_path / "before"
    before.mkdir()
    for path in sorted(migrations_dir().glob("[0-9]*.sql")):
        if path.name < "0014":
            shutil.copy(path, before / path.name)
    apply_migrations(database_url, Path(before))
    with psycopg.connect(database_url, row_factory=dict_row, autocommit=True) as conn:
        conn.execute("INSERT INTO conversation (id, host, host_chat_ref) VALUES (gen_random_uuid(), 'h', 'c')")
        conv = conn.execute("SELECT id FROM conversation").fetchone()["id"]
        conn.execute("INSERT INTO source_object (id, conversation_id, host_logical_id) VALUES (gen_random_uuid(), %s, 'm')",
                     (conv,))
        obj = conn.execute("SELECT id FROM source_object").fetchone()["id"]
        conn.execute("INSERT INTO source_revision (id, source_object_id, revision_hash, content, metadata, lifecycle)"
                     " VALUES (gen_random_uuid(), %s, 'h', 'x', '{}', 'accepted')", (obj,))
        rev = conn.execute("SELECT id FROM source_revision").fetchone()["id"]
        conn.execute("INSERT INTO extraction (id, source_revision_id, window_hash, compiler_version, model, raw)"
                     " VALUES (gen_random_uuid(), %s, 'w', 'extract-v4', 'm', '{}')", (rev,))
        ext = conn.execute("SELECT id FROM extraction").fetchone()["id"]
        conn.execute("INSERT INTO assertion (extraction_id, source_revision_id, subject, predicate, status)"
                     " VALUES (%s, %s, 's', 'identity', 'valid')", (ext, rev))
    apply_migrations(database_url)
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        row = conn.execute("SELECT polarity, modality, source, asserted_by FROM assertion").fetchone()
        hints = conn.execute("SELECT hints FROM extraction").fetchone()["hints"]
    assert dict(row) == {"polarity": "positive", "modality": "actual", "source": None, "asserted_by": None}
    assert hints is None


def test_prompt_asks_for_the_new_fields():
    prompt = extraction.SYSTEM_PROMPT.format(registry=registry_prompt())
    for word in ('"polarity"', '"modality"', '"source"', '"asserted_by"', "hypothetical", "dreamed",
                 "character_claim", "also_called"):
        assert word in prompt
    assert "Skip speculation" not in prompt
