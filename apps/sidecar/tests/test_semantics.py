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
    assert active_generation(db, "extract").spec["compiler"] == "extract-v8"
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


# --- reading (ADR 0013) --------------------------------------------------------------------------

def row(pos: int, subject: str, predicate: str, obj: str | None = None, value: str | None = None, **kw):
    return {"id": pos, "position": pos, "turn": pos, "host_logical_id": f"m{pos}", "subject": subject,
            "predicate": predicate, "object": obj, "value": value, "polarity": "positive", "modality": "actual",
            "source": "narration", "asserted_by": None, "epistemic": "stated", **kw}


def current(history):
    from nmos_sidecar.facts import _versions
    return [(f["subject"], f["object"] or f["value"], f["polarity"]) for f in _versions(history)]


def test_negation_ends_only_the_relation_it_denies():
    home, station = row(1, "하나", "located_in", "집"), row(2, "하나", "located_in", "역", polarity="negative")
    assert current([home, station]) == [("하나", "집", "positive"), ("하나", "역", "negative")]
    assert current([home, row(2, "하나", "located_in", "집", polarity="negative")]) == [("하나", "집", "negative")]
    # A later positive statement of the denied relation replaces the negation.
    assert current([home, station, row(3, "하나", "located_in", "역")]) == [("하나", "역", "positive")]


def test_item_negation_needs_the_holder():
    held = row(1, "하나", "possesses", "지도")
    assert current([held, row(2, "하나", "possesses", "지도", polarity="negative")]) == [("하나", "지도", "negative")]
    assert current([held, row(2, "카이토", "possesses", "지도", polarity="negative")]) == [
        ("하나", "지도", "positive"), ("카이토", "지도", "negative")]


def test_negation_without_a_current_version_is_a_negative_fact():
    assert current([row(1, "Alice", "located_in", "hall", polarity="negative")]) == [("Alice", "hall", "negative")]


def test_packet_note_explains_marks_only_when_used():
    from nmos_sidecar.packet import PACKET_NOTE, compile_packet
    plain, _, _ = compile_packet([], 600, facts=['    <Fact kind="located_in" turn="1">A located in B</Fact>'])
    assert PACKET_NOTE in plain and "negated" not in plain.split("<Facts>")[0]
    marked, _, _ = compile_packet([], 600, facts=[
        '    <Fact kind="located_in" turn="1" negated="true">A located in B</Fact>',
        '    <Claim by="C" kind="identity" turn="2">C identity: knight</Claim>'])
    note = marked.split("<Facts>")[0]
    assert 'negated="true" marks' in note and "A Claim is what that character said" in note


def claim_complete(system: str, user: str) -> tuple[dict, str]:
    target = user.split("TARGET", 1)[1]
    items = []
    if "squire" in target:
        items.append({"subject": "Ren", "subject_type": "character", "predicate": "identity", "value": "squire",
                      "modality": "actual", "source": "narration"})
    if "knight" in target:
        items.append({"subject": "Ren", "subject_type": "character", "predicate": "identity", "value": "knight",
                      "modality": "actual", "source": "character_claim", "asserted_by": "Ren"})
    if "best swordsman" in target:
        items.append({"subject": "Ren", "subject_type": "character", "predicate": "identity",
                      "value": "best swordsman", "modality": "unknown", "source": "character_claim",
                      "asserted_by": "Ren"})
    if "will be a king" in target:
        items.append({"subject": "Ren", "subject_type": "character", "predicate": "identity", "value": "king",
                      "modality": "hypothetical", "source": "character_claim", "asserted_by": "Ren"})
    if "someday" in target:
        items.append({"subject": "Ren", "subject_type": "character", "predicate": "identity", "value": "captain",
                      "modality": "hypothetical"})
    if "legacy" in target:
        items.append({"subject": "Mina", "subject_type": "character", "predicate": "identity", "value": "healer",
                      "modality": "actual"})
    return {"assertions": items}, "{}"


def test_claims_attach_and_non_actual_stays_out(migrated, db):
    from test_extraction import facts
    chat = SimChat()
    chat.user("Ren is a squire.")
    chat.reply("He polishes armor.")
    chat.user('Ren: "I am a knight."')
    chat.reply("Sure.")
    chat.user("Ren will be a captain someday.")
    chat.reply("Maybe.")
    chat.user('Ren: "I am the best swordsman."')
    chat.reply("Hm.")
    chat.user('Ren: "I will be a king."')
    chat.reply("Sure.")
    chat.user("next")
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        drain(migrated, claim_complete)
        got = facts(c, chat)
        assert [(f["value"], f["source"]) for f in got] == [("squire", "narration")]
        # A claim whose truth the model marks unknown is still a claim (owner decision 2026-09-24): it
        # replaces Ren's earlier claim on the same key. A claim about a plan or a dream is not one.
        assert [(cl["by"], cl["value"]) for cl in got[0]["claims"]] == [("Ren", "best swordsman")]
        cid = next(x["id"] for x in c.get("/v1/conversations").json() if x["host_chat_ref"] == chat.id)
        page = c.get(f"/inspector/c/{cid}?lang=en").text
    assert "knight" in page and "captain" in page and "hypothetical" in page


def test_legacy_rows_read_as_narration(migrated, db):
    """Rows without a source (extract-v4 and older) keep their meaning: narration, never a claim."""
    from test_extraction import facts
    chat = SimChat()
    chat.user("A legacy line.")
    chat.reply("ok")
    chat.user("next")
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        drain(migrated, claim_complete)
        db.execute("UPDATE assertion SET source = NULL")
        assert [(f["value"], f["source"]) for f in facts(c, chat)] == [("healer", None)]
