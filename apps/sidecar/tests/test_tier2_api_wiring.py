"""Tier 2 wiring (owner-agreed): the author's note's cross-language secret check (B8), the embedding chunk cap as a panel
setting (E8), the extractor and packet allowlists (G4), the memory map with a carry link (C/15), and the reveal checks'
blind spots (C5, D2). Stub models and embedders only; synthetic names (Luca, Noel, Mia)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from psycopg.types.json import Jsonb

from conftest import active_generation, make_client
from nmos_sidecar import generations, notes, reveals, runtime
from nmos_sidecar.config import EMBED_MAX_CHUNKS, EXTRACT_COMPILERS, Settings
from nmos_sidecar.extraction import ASSERTION_COLUMNS
from nmos_sidecar.ids import uuid7
from nmos_sidecar.packet import DEFAULT_POLICY, POLICIES
from simchat import SimChat
from test_extraction import drain
from test_generations import EMB, LLM
from test_hints import step
from test_reveals import checked, head, served_from_checks
from test_secrets import SecretRecorder, first_import
from test_vectors import FakeEmbedder

# --- config: the extractor and packet allowlists, the chunk cap (G4, E8) ---------------------------------------------


def test_extract_v20_is_a_selectable_extractor_and_a_misspelt_one_is_still_refused():
    assert "extract-v20" in EXTRACT_COMPILERS
    assert Settings(extract_compiler="extract-v20").extract_compiler == "extract-v20"
    for ok in ("", *EXTRACT_COMPILERS):
        Settings(extract_compiler=ok)
    with pytest.raises(ValueError, match="NMOS_EXTRACT_COMPILER must be empty, extract-v15.* or extract-v20"):
        Settings(extract_compiler="extract-v21")


def test_packet_policy_follows_the_packet_compilers_policies():
    """`config.py` holds no policy allowlist: the sidecar takes `packet.POLICIES` (packet-v21 once `packet.py` has it) and
    falls back to the default for anything else, so a setting is never refused at startup."""
    from nmos_sidecar import api

    assert Settings(packet_policy="packet-v21").packet_policy == "packet-v21"
    assert Settings(packet_policy="not-a-policy").packet_policy == "not-a-policy"
    assert DEFAULT_POLICY in POLICIES and api.POLICIES is POLICIES  # the endpoint's `policy` check reads the same set


@pytest.mark.parametrize("value", [EMBED_MAX_CHUNKS[0], 8, 52, EMBED_MAX_CHUNKS[1]])
def test_the_chunk_cap_is_accepted_within_its_bounds(value):
    assert Settings(embed_max_chunks=value).embed_max_chunks == value
    assert runtime.validate_update({"embed_max_chunks": value}) == ({"embed_max_chunks": value}, [])


@pytest.mark.parametrize("value", [0, -1, EMBED_MAX_CHUNKS[1] + 1, 1000])
def test_a_chunk_cap_out_of_bounds_is_refused_by_startup_and_the_panel(value):
    with pytest.raises(ValueError, match="NMOS_EMBED_MAX_CHUNKS must be at (least 1|most 64)"):
        Settings(embed_max_chunks=value)
    clean, errors = runtime.validate_update({"embed_max_chunks": value})
    assert clean == {} and errors == ["embed_max_chunks: must be between 1 and 64"]


@pytest.mark.parametrize("value", ["8", True, 8.5, None])
def test_a_chunk_cap_that_is_not_an_integer_is_refused(value):
    clean, errors = runtime.validate_update({"embed_max_chunks": value})
    if value is None:
        assert clean == {"embed_max_chunks": None} and errors == []  # back to the environment's value
    else:
        assert clean == {} and errors and errors[0].startswith("embed_max_chunks: expected an integer")
    with pytest.raises(ValueError):
        Settings(embed_max_chunks=True)


def test_a_saved_chunk_cap_startup_would_refuse_is_ignored_not_fatal():
    """A restored row or a downgrade: the environment's value applies and the sidecar still starts."""
    base = Settings(embed_max_chunks=8)
    assert runtime.effective(base, {"embed_max_chunks": 0}).embed_max_chunks == 8
    assert runtime.effective(base, {"embed_max_chunks": 65}).embed_max_chunks == 8
    assert runtime.effective(base, {"embed_max_chunks": "12"}).embed_max_chunks == 8
    assert runtime.effective(base, {"embed_max_chunks": 12}).embed_max_chunks == 12


def test_the_panel_reads_and_saves_the_chunk_cap_as_a_new_projection(migrated, db):
    """GET /v1/config shows `embeddings.max_chunks`; PUT `embed_max_chunks` activates a new embedding projection (its
    cap is in the key) and queues the re-embedding, with no model call."""
    with make_client(migrated, embedder=FakeEmbedder(), **EMB) as c:
        chat = SimChat()
        chat.user("Luca walks to the harbour.")
        chat.reply("Noted.")
        from test_sidecar_integration import sync

        sync(c, chat)
        assert c.get("/v1/config").json()["embeddings"]["max_chunks"] == 8
        before = active_generation(db, "embed")
        assert before.spec["max_chunks"] == 8
        res = c.put("/v1/config", json={"embed_max_chunks": 16})
        assert res.status_code == 200, res.text
        assert res.json()["embeddings"]["max_chunks"] == 16 and "embed_max_chunks" in res.json()["overridden"]
        after = active_generation(db, "embed")
        assert after.key != before.key and after.spec["max_chunks"] == 16
        assert db.execute("SELECT count(*) AS n FROM job WHERE kind = 'embed' AND status = 'queued'"
                          " AND payload->>'generation' = %s", (after.key,)).fetchone()["n"] > 0
        for bad in (0, 65, "16", True):
            assert c.put("/v1/config", json={"embed_max_chunks": bad}).status_code == 422
        assert c.get("/v1/config").json()["embeddings"]["max_chunks"] == 16
        assert c.put("/v1/config", json={"embed_max_chunks": None}).json()["embeddings"]["max_chunks"] == 8


# --- the author's note: language and the cross-language secret check (B8) ---------------------------------------------


class Captured:
    """`notes.make` as the endpoint calls it, recorded."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.kwargs: dict[str, Any] | None = None
        real = notes.make

        def make(*args: Any, **kwargs: Any) -> dict[str, Any]:
            self.kwargs = kwargs
            return real(*args, **kwargs)

        monkeypatch.setattr(notes, "make", make)


def fake_note_model(system: str, user: str) -> tuple[dict[str, Any], str, None]:
    if "SECRETS:" in user and "TEXT:" in user:  # the leak check's call
        return {"told": []}, "{}", None
    return {"text": "- Luca and Noel at the lecture hall."}, "{}", None


def _note(c, conv: str, **body: Any):
    notes.clear_cache()
    return c.post(f"/v1/conversations/{conv}/notes", json={"sections": ["chronicle"], **body})


def test_a_language_outside_the_allowlist_is_refused(migrated, db):
    with make_client(migrated, **LLM) as c:
        _, conv = first_import(c, migrated, SecretRecorder(), db)
        for bad in ("ko", "fr", "", 1, None):
            res = _note(c, conv, language=bad)
            assert res.status_code == 422 and "language must be one of chat, en" in res.text, bad


def test_an_english_note_without_secrets_checks_for_leaks_by_embedding_when_an_embedder_is_set(
        migrated, db, monkeypatch):
    monkeypatch.setattr(notes, "model_for", lambda *a, **k: fake_note_model)
    cap = Captured(monkeypatch)
    with make_client(migrated, embedder=FakeEmbedder(), **LLM, **EMB) as c:
        _, conv = first_import(c, migrated, SecretRecorder(), db)
        assert _note(c, conv, language="en").status_code == 200
        check = cap.kwargs["semantic_leaks"]
        assert check is not None and check.__qualname__.startswith("embedding_leak_checker")
        for body in ({"language": "chat"}, {"language": "en", "secrets": True}, {"language": "en", "model": False}, {}):
            assert _note(c, conv, **body).status_code == 200
            assert cap.kwargs["semantic_leaks"] is None, body


def test_an_english_note_without_an_embedder_checks_for_leaks_with_the_notes_model(migrated, db, monkeypatch):
    monkeypatch.setattr(notes, "model_for", lambda *a, **k: fake_note_model)
    cap = Captured(monkeypatch)
    with make_client(migrated, **LLM) as c:
        _, conv = first_import(c, migrated, SecretRecorder(), db)
        assert _note(c, conv, language="en").status_code == 200
        check = cap.kwargs["semantic_leaks"]
        assert check is not None and check.__qualname__.startswith("model_leak_checker")


def test_no_leak_check_without_a_model(migrated, db, monkeypatch):
    monkeypatch.setattr(notes, "model_for", lambda *a, **k: None)  # no model configured for the note
    cap = Captured(monkeypatch)
    with make_client(migrated, embedder=FakeEmbedder(), **LLM, **EMB) as c:
        _, conv = first_import(c, migrated, SecretRecorder(), db)
        assert _note(c, conv, language="en").status_code == 200
        assert cap.kwargs["semantic_leaks"] is None


# --- the trim request's default (aligned with the plugin) -------------------------------------------------------------


def test_a_trim_request_keeps_16_recent_turns_by_default():
    from nmos_sidecar.models import TrimRequest

    assert TrimRequest() == TrimRequest(keep_recent_turns=16, step=16)
    assert TrimRequest(keep_recent_turns=20).step == 20  # an explicit value is kept, its step with it


# --- reveal checks (C5, D2) -------------------------------------------------------------------------------------------


def _turn(db, turn: int) -> dict[str, Any]:
    return db.execute("SELECT am.source_revision_id AS rid, am.turn_hash FROM active_membership am"
                      " JOIN conversation c ON c.head_commit_id = am.commit_id WHERE am.turn = %s AND am.turn_hash IS NOT NULL",
                      (turn,)).fetchone()


def _served_extraction(db, turn: int, key: str) -> UUID:
    t = _turn(db, turn)
    return db.execute("SELECT id FROM extraction WHERE source_revision_id = %s AND window_hash = %s"
                      " AND extractor_key = %s AND discarded_at IS NULL", (t["rid"], t["turn_hash"], key)).fetchone()["id"]


def _newer_extract(db, name: str = "newer") -> generations.Generation:
    gen = generations.make("extract", f"http://{name}-llm/v1", name)
    generations.activate(db, gen)
    db.commit()
    return gen


def _copy_extraction(db, turn: int, src_key: str, gen: generations.Generation,
                     extra: list[dict[str, Any]] = ()) -> UUID:
    """A re-extraction of `turn` by `gen` (a model change, a cap raise) with the rows of `src_key`'s and `extra`."""
    t = _turn(db, turn)
    src = _served_extraction(db, turn, src_key)
    xid = uuid7()
    db.execute("INSERT INTO extraction (id, source_revision_id, window_hash, compiler_version, extractor_key, model,"
               " raw) VALUES (%s, %s, %s, 'test', %s, %s, '{}')", (xid, t["rid"], t["turn_hash"], gen.key, gen.model))
    cols = ", ".join(ASSERTION_COLUMNS)
    db.execute(f"INSERT INTO assertion (extraction_id, source_revision_id, {cols})"
               f" SELECT %s, source_revision_id, {cols} FROM assertion WHERE extraction_id = %s", (xid, src))
    for a in extra:
        keys = list(a)
        db.execute(f"INSERT INTO assertion (extraction_id, source_revision_id, {', '.join(keys)})"
                   f" VALUES (%s, %s, {', '.join(['%s'] * len(keys))})", (xid, t["rid"], *a.values()))
    db.commit()
    return xid


SECRET_B = {"subject": "Luca", "subject_type": "character", "predicate": "goal", "value": "steal the archive key",
            "modality": "actual", "knowledge": "limited", "known_by": ["Luca"], "hidden_from": ["Mia"],
            "status": "valid", "epistemic": "stated", "polarity": "positive", "source": "narration"}


def _in_order(c, migrated, db) -> tuple[SimChat, str, SecretRecorder]:
    """Three turns extracted as they complete: the secret first, so nothing needs a check."""
    model, chat = SecretRecorder(), SimChat()
    for line in ("Luca secretly plans to watch the lecture, hidden from Noel.", "Noel drinks coffee.", "Noel smiles."):
        step(c, migrated, chat, model, line)
    step(c, migrated, chat, model, "next")
    conv = next(x for x in c.get("/v1/conversations").json() if x["host_chat_ref"] == chat.id)["id"]
    return chat, conv, model


def test_turns_served_by_an_earlier_generation_are_checked(migrated, db):
    """C5: `cur` read only the active extractor's extractions, so after a carry-on model change (PHASE-57) the turns the
    earlier generation still serves were never checked, and their secrets never made a later turn look again."""
    with make_client(migrated, **LLM) as c:
        model = SecretRecorder()
        _, conv = first_import(c, migrated, model, db)  # K29: turns 1 and 2 were extracted before turn 0's secret
        ex, rv = active_generation(db, "extract"), active_generation(db, "reveal")
        newer = _newer_extract(db)
        _copy_extraction(db, 0, ex.key, newer)  # only the secret's turn is the new generation's
        assert [r["turn"] for r in reveals.unchecked(db, newer.key, rv.key, conv)] == [1, 2]
        assert reveals.schedule(db, rv.key, newer.key, conv) == 2
        db.commit()
        drain(migrated, model)
        assert reveals.unchecked(db, newer.key, rv.key, conv) == []  # settled
        (reveal,) = served_from_checks(db, newer.key)  # the check of the extraction serving turn 2 is served
        assert reveal["turn"] == 2 and reveal["subject"] == "Noel" and reveal["generation"] == ex.key


def test_a_turn_queued_for_the_active_extractor_is_not_checked(migrated, db):
    """"Extract all history" queues every turn the active extractor has not extracted before it queues the checks:
    such a turn is extracted with what is open by then, so a check of its older extraction would be a wasted call."""
    with make_client(migrated, **LLM) as c:
        _, conv = first_import(c, migrated, SecretRecorder(), db)
        ex, rv = active_generation(db, "extract"), active_generation(db, "reveal")
        newer = _newer_extract(db)
        t1 = _turn(db, 1)
        db.execute("INSERT INTO job (kind, dedupe_key, conversation_id, payload, priority) VALUES ('extract', %s, %s,"
                   " %s, 300)", (f"extract:{t1['rid']}:{t1['turn_hash']}:{newer.key}", conv,
                                 Jsonb({"revision_id": str(t1["rid"]), "window_hash": t1["turn_hash"],
                                        "generation": newer.key})))
        db.commit()
        assert [r["turn"] for r in reveals.unchecked(db, newer.key, rv.key, conv)] == [2]
        db.execute("UPDATE job SET status = 'done' WHERE kind = 'extract' AND dedupe_key LIKE %s", ("%" + newer.key,))
        db.commit()
        assert [r["turn"] for r in reveals.unchecked(db, newer.key, rv.key, conv)] == [1, 2]


def test_a_secret_a_re_extraction_found_makes_the_later_turns_look_again(migrated, db):
    """C5: a turn counted as listed once any extraction of an earlier turn held any secret. Turn 0 held secret A when
    turns 1 and 2 were extracted; its re-extraction (a cap raise, PHASE-62) found secret B too, which no later turn could
    have listed: they look again, once, and settle, B unnamed in their prompts or not."""
    with make_client(migrated, **LLM) as c:
        _, conv, model = _in_order(c, migrated, db)
        ex, rv = active_generation(db, "extract"), active_generation(db, "reveal")
        assert reveals.unchecked(db, ex.key, rv.key, conv) == []
        newer = _newer_extract(db)
        _copy_extraction(db, 0, ex.key, newer, [SECRET_B])
        assert [r["turn"] for r in reveals.unchecked(db, newer.key, rv.key, conv)] == [1, 2]
        assert reveals.schedule(db, rv.key, newer.key, conv) == 2
        db.commit()
        drain(migrated, model)
        assert reveals.unchecked(db, newer.key, rv.key, conv) == []
        assert reveals.schedule(db, rv.key, newer.key, conv) == 0  # pressed again: nothing queued


def test_a_re_extraction_that_found_the_same_secret_queues_nothing(migrated, db):
    """The other side of the per-secret rule: a re-extraction holding the secret the later turns could already list
    (another generation's spelling of the same row) costs no check."""
    with make_client(migrated, **LLM) as c:
        _, conv, _ = _in_order(c, migrated, db)
        ex, rv = active_generation(db, "extract"), active_generation(db, "reveal")
        newer = _newer_extract(db)
        _copy_extraction(db, 0, ex.key, newer)
        assert reveals.unchecked(db, newer.key, rv.key, conv) == []


class Liar(SecretRecorder):
    """A reveal check that always says Noel found S1 out, quoting a line from past the TARGET's cap."""

    def __call__(self, system: str, user: str) -> tuple[dict, str]:
        if system == reveals.PROMPT:
            self.prompts.append(user)
            return {"secrets": [{"secret": "S1", "found_out_by": ["Noel"],
                                 "evidence": "Noel found out: Luca goal: watch the lecture."}]}, "{}"
        return super().__call__(system, user)


def test_a_check_reads_evidence_only_in_the_target_as_the_model_was_shown_it(migrated, db):
    """D2: `process` checked a reveal's quote against the whole turn, the part past the cap (`shown_target`) too, which
    the model never saw. The quote must be in what it was shown, as for a turn extraction (`process_extract`)."""
    with make_client(migrated, **LLM) as c:
        model, chat = SecretRecorder(), SimChat()
        step(c, migrated, chat, model, "Luca secretly plans to watch the lecture, hidden from Noel.")
        padding = " ".join(f"Noel reads page {i} of the long syllabus." for i in range(260))  # past 6,000 characters
        step(c, migrated, chat, model, f"Noel drinks coffee. {padding} Noel found out: Luca goal: watch the lecture.")
        step(c, migrated, chat, model, "next")
        conv = next(x for x in c.get("/v1/conversations").json() if x["host_chat_ref"] == chat.id)["id"]
        ex, rv = active_generation(db, "extract"), active_generation(db, "reveal")
        t1 = _turn(db, 1)
        xid = _served_extraction(db, 1, ex.key)
        db.execute("INSERT INTO job (kind, dedupe_key, conversation_id, payload, priority) VALUES ('reveal', 'cap', %s,"
                   " %s, 300)", (conv, Jsonb({"extraction_id": str(xid), "revision_id": str(t1["rid"]),
                                             "window_hash": t1["turn_hash"], "generation": rv.key})))
        db.commit()
        liar = Liar()
        assert drain(migrated, liar) == 1 and liar.prompts  # the check asked, with S1 listed
        assert "Noel found out" not in liar.prompts[-1].split("TARGET", 1)[1]  # past the cap: never shown
        (made,) = db.execute("SELECT id, hints FROM extraction WHERE window_hash = %s AND discarded_at IS NULL",
                             ("reveal:" + t1["turn_hash"],)).fetchall()
        assert made["hints"]["secrets"]  # it listed the secret ...
        # ... and stored no reveal of it: before, `revealed` read the whole turn and made one, which `normalize` then
        # parked as pending ("evidence not in the turn"); now it is never made, as in a turn extraction
        assert not db.execute("SELECT 1 FROM assertion WHERE extraction_id = %s", (made["id"],)).fetchone()
        assert not served_from_checks(db)


def test_a_check_that_listed_a_reworded_secret_before_a_reveal_was_stored_is_checked_again(migrated, db):
    """C5: `stale` matched a listing to an earlier reveal by exact text only. A listing that words the secret otherwise
    (its turn re-extracted between the two) is matched as the read side's fold matches it, while the reveal was stored
    after the check read its OPEN SECRETS; once checked again, it is settled whatever the fold made of it."""
    with make_client(migrated, **LLM) as c:
        model = SecretRecorder()
        chat, conv = first_import(c, migrated, model, db)
        c.post(f"/v1/conversations/{conv}/extract-history")
        drain(migrated, model)
        step(c, migrated, chat, model, "Noel waves.")  # a later turn, extracted after the reveal
        ex, rv = active_generation(db, "extract"), active_generation(db, "reveal")
        later = max(r["turn"] for r in db.execute(
            "SELECT am.turn FROM active_membership am JOIN conversation c ON c.head_commit_id = am.commit_id"
            " WHERE am.turn_hash IS NOT NULL").fetchall())
        t = _turn(db, later)
        xid = _served_extraction(db, later, ex.key)
        db.execute("INSERT INTO job (kind, dedupe_key, conversation_id, payload, priority) VALUES ('reveal', 'later', %s,"
                   " %s, 300)", (conv, Jsonb({"extraction_id": str(xid), "revision_id": str(t["rid"]),
                                             "window_hash": t["turn_hash"], "generation": rv.key})))
        db.commit()
        drain(migrated, SecretRecorder())
        assert reveals.unchecked(db, ex.key, rv.key, conv) == []
        listed = db.execute("SELECT hints->'secrets'->0 AS s FROM extraction WHERE window_hash LIKE 'reveal:%%'"
                            " AND jsonb_array_length(hints->'secrets') > 0 AND discarded_at IS NULL"
                            " ORDER BY created_at LIMIT 1").fetchone()["s"]
        reworded = {**listed, "text": listed["text"].replace("watch the lecture", "watch the lecture today")}
        assert reworded["text"] != listed["text"]
        stored = db.execute("SELECT max(x.created_at) AS t FROM extraction x JOIN assertion a ON a.extraction_id = x.id"
                            " WHERE a.predicate = 'learned'").fetchone()["t"]
        window = "reveal:" + t["turn_hash"]
        # read before the reveal was stored: stale, by the fold's match
        db.execute("UPDATE extraction SET hints = hints || %s WHERE window_hash = %s AND discarded_at IS NULL",
                   (Jsonb({"secrets": [reworded], "read_at": (stored.replace(year=stored.year - 1)).isoformat()}),
                    window))
        db.commit()
        assert [r["turn"] for r in reveals.unchecked(db, ex.key, rv.key, conv)] == [later]
        # read after it: the fold had it, so the listing is what a check made again would list; not stale
        db.execute("UPDATE extraction SET hints = hints || %s WHERE window_hash = %s AND discarded_at IS NULL",
                   (Jsonb({"read_at": stored.isoformat()}), window))
        db.commit()
        assert reveals.unchecked(db, ex.key, rv.key, conv) == []
        # an unrelated listing (another holder's secret) read before the reveal is no match either
        other = {**listed, "text": "Mia goal: steal the archive key", "kept_from": listed["kept_from"]}
        db.execute("UPDATE extraction SET hints = hints || %s WHERE window_hash = %s AND discarded_at IS NULL",
                   (Jsonb({"secrets": [other], "read_at": (stored.replace(year=stored.year - 1)).isoformat()}),
                    window))
        db.commit()
        assert reveals.unchecked(db, ex.key, rv.key, conv) == []
        assert head(db)  # the chat is intact
