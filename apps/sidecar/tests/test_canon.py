"""Canon sources (Phase 14 step 3, ADR 0045): capture as immutable revisions, manifests and the canon in force, replays,
what a prompt held, the Inspector, deletion, and that no message pipeline sees canon."""

from __future__ import annotations

import json
import time
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from conftest import make_client
from nmos_sidecar import canon
from simchat import SimChat
from test_sidecar_integration import recall, sync

DESC = "하나는 항구 마을 등대지기의 딸이다. 하나의 눈은 푸른색이다."
LORE = "카이토는 견습 기사이고 하나의 소꿉친구다."
NOTE = "지금은 한겨울 밤이다."
VECTOR = Path(__file__).resolve().parents[3] / "fixtures/unit/canon-manifest-v1.json"


def entry(key: str, text: str, **metadata) -> dict:
    return {"key": key, "hash": canon.content_hash(text), "metadata": metadata}


def push(c, chat: SimChat, texts: dict[str, tuple[str, dict]], observed_at: int | None = None) -> dict:
    """The plugin's two calls: the manifest, then the texts the sidecar asked for."""
    entries = [entry(k, text, **meta) for k, (text, meta) in texts.items()]
    body = {"chat_id": chat.id, "entries": entries, **({"observed_at": observed_at} if observed_at else {})}
    out = c.post("/v1/sync/canon", json=body).json()
    if out["needed"]:
        by_hash = {canon.content_hash(text): text for text, _ in texts.values()}
        res = c.post("/v1/sync/canon", json={**body, "contents": {h: by_hash[h] for h in out["needed"]}})
        assert res.status_code == 200, res.text
        out = res.json()
    return out


def a_chat() -> SimChat:
    chat = SimChat("canon-chat")
    chat.user("하나는 등대로 간다.")
    chat.reply("하나가 등대 문을 열었다.")
    chat.user("카이토는 어디 있어?")
    return chat


def conv_id(url: str, chat: SimChat):
    with psycopg.connect(url, row_factory=dict_row) as conn:
        return conn.execute("SELECT id FROM conversation WHERE host_chat_ref = %s", (chat.id,)).fetchone()["id"]


def test_the_manifest_id_is_the_same_in_both_languages():
    doc = json.loads(VECTOR.read_text())
    assert canon.manifest_id(doc["entries"]) == doc["id"]
    assert canon.manifest_id(list(reversed(doc["entries"]))) == doc["id"]  # key order, whatever the host's order
    assert doc["entries"][1]["hash"] == canon.content_hash(doc["texts"]["card:desc"].replace("\r\n", "\n"))


def test_canon_is_stored_once_and_its_manifest_made_the_canon_in_force(migrated):
    chat = a_chat()
    with make_client(migrated) as c:
        sync(c, chat)
        texts = {"card:desc": (DESC, {"field": "desc"}), "note": (NOTE, {}),
                 "lore:kaito": (LORE, {"scope": "character", "mode": "normal", "keys": ["카이토", "카이"]})}
        entries = [entry(k, t, **m) for k, (t, m) in texts.items()]
        first = c.post("/v1/sync/canon", json={"chat_id": chat.id, "entries": entries}).json()
        assert sorted(first["needed"]) == sorted(e["hash"] for e in entries) and not first["applied"]
        out = push(c, chat, texts)
        assert (out["needed"], out["stored"], out["applied"], out["in_force"]) == ([], 3, True, 3)
        assert out["manifest_id"] == canon.manifest_id(entries)
        again = push(c, chat, texts)  # the same canon: nothing to send, nothing changed
        assert (again["needed"], again["stored"], again["applied"]) == ([], 0, False)
        dup = c.post("/v1/sync/canon", json={"chat_id": chat.id, "entries": [entries[0], entries[0]]})
        assert dup.status_code == 422
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        rows = canon.manifest(conn, conv_id(migrated, chat))
        assert [(r["key"], r["content"]) for r in rows] == [("card:desc", DESC), ("lore:kaito", LORE), ("note", NOTE)]
        assert rows[1]["metadata"] == {"scope": "character", "mode": "normal", "keys": ["카이토", "카이"]}


def test_a_text_that_does_not_match_its_hash_is_asked_for_again_and_not_stored(migrated):
    chat = a_chat()
    with make_client(migrated) as c:
        sync(c, chat)
        e = entry("card:desc", DESC)
        out = c.post("/v1/sync/canon", json={"chat_id": chat.id, "entries": [e],
                                             "contents": {e["hash"]: DESC + " 위조"}}).json()
        assert out["needed"] == [e["hash"]] and out["stored"] == 0
        assert c.post("/v1/sync/canon", json={"chat_id": "no-such-chat", "entries": [e]}).status_code == 404
        bad = c.post("/v1/sync/canon", json={"chat_id": chat.id, "entries": [{**e, "key": "card:systemPrompt"}]})
        assert bad.status_code == 422  # instructions are not canon (PHASE-14 Q1)


def test_edits_metadata_and_removals_make_new_manifests_and_an_older_observation_does_not_win(migrated):
    chat = a_chat()
    t0 = int(time.time() * 1000)
    with make_client(migrated) as c:
        sync(c, chat)
        push(c, chat, {"card:desc": (DESC, {}), "lore:kaito": (LORE, {"keys": ["카이토"]}), "note": (NOTE, {})}, t0)
        edited = DESC + " 하나는 열여섯 살이다."
        # the description edited, the entry's keys changed with the same text, the note gone
        out = push(c, chat, {"card:desc": (edited, {}), "lore:kaito": (LORE, {"keys": ["카이토", "카이"]})}, t0 + 2000)
        assert (out["stored"], out["applied"], out["in_force"]) == (1, True, 2)
        # an upload of an older observation finishing late does not bring the old canon back
        late = push(c, chat, {"card:desc": (DESC, {}), "lore:kaito": (LORE, {"keys": ["카이토"]}), "note": (NOTE, {})},
                    t0 + 1000)
        assert (late["applied"], late["stale"]) == (False, True)
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        cid = conv_id(migrated, chat)
        now = canon.manifest(conn, cid)
        assert [(r["key"], r["content"], r["metadata"]) for r in now] == [
            ("card:desc", edited, {}), ("lore:kaito", LORE, {"keys": ["카이토", "카이"]})]
        hist = canon.history(conn, cid)
        assert hist["card:desc"]["versions"] == 2 and hist["lore:kaito"]["versions"] == 2
        # the old texts stay, immutable, as history (invariant 1)
        n = conn.execute("SELECT count(*) AS n FROM source_revision sr JOIN source_object so ON so.id = sr.source_object_id"
                         " WHERE so.conversation_id = %s AND so.source_kind = 'canon'", (cid,)).fetchone()["n"]
        assert n == 4


def test_a_request_records_its_canon_and_replays_with_it_even_when_the_texts_arrive_later(migrated):
    chat = a_chat()
    with make_client(migrated) as c:
        sync(c, chat)
        push(c, chat, {"card:desc": (DESC, {})})
        edited = DESC + " 하나는 열여섯 살이다."
        new_manifest = canon.manifest_id([entry("card:desc", edited)])
        # the plugin sends the request first (its prompt already has the edit), the texts after it
        out = recall(c, chat, "하나는 몇 살이야?", canon_manifest_id=new_manifest, canon_held=["card:desc"])
        push(c, chat, {"card:desc": (edited, {})})
        recall(c, chat, "하나는 몇 살이야?", canon_manifest_id=new_manifest, canon_held=["card:desc"])
        cid = conv_id(migrated, chat)
        page = c.get(f"/inspector/c/{cid}", params={"lang": "en"}).text
        section = page[page.index('id="s-canon"'):page.index("</details>", page.index('id="s-canon"'))]
        assert "Canon (card, lorebooks, persona, author" in section and "2×, last" in section
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        trace = conn.execute("SELECT canon_manifest_id, canon_held FROM retrieval_trace WHERE id = %s",
                             (out["trace_id"],)).fetchone()
        assert (trace["canon_manifest_id"], trace["canon_held"]) == (new_manifest, ["card:desc"])
        assert [r["content"] for r in canon.manifest(conn, cid, trace["canon_manifest_id"])] == [edited]
        assert canon.held(conn, cid)["card:desc"]["requests"] == 2


def test_canon_reaches_no_message_pipeline_and_goes_with_the_chat(migrated):
    chat = a_chat()
    with make_client(migrated) as c:
        sync(c, chat, character_name="Status test")
        # A card holding a status block: a state rule must not read canon, on sync or on a rebuild.
        rules = {"rules": [{"card": "Status test", "id": "r", "kind": "block", "start": "<status>", "end": "</status>",
                            "entity_line": r"\[(?P<entity>[^\]]+)\]"}]}
        assert c.put("/v1/config", json={"parsers": rules}).status_code == 200
        push(c, chat, {"card:desc": ("<status>\n[하나]\n장소: 성당\n</status>", {})})
        out = recall(c, chat, "어디?")
        assert "성당" not in out["packet"]["text"]
        cid = conv_id(migrated, chat)
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            from nmos_sidecar.parsers import compile_rules
            from nmos_sidecar.state import rebuild_state
            rebuild_state(conn, compile_rules(rules))
            assert conn.execute("SELECT count(*) AS n FROM state_observation so JOIN source_revision sr"
                                " ON sr.id = so.source_revision_id JOIN source_object o ON o.id = sr.source_object_id"
                                " WHERE o.source_kind = 'canon'").fetchone()["n"] == 0
            assert conn.execute("SELECT count(*) AS n FROM active_membership am JOIN source_revision sr"
                                " ON sr.id = am.source_revision_id JOIN source_object o ON o.id = sr.source_object_id"
                                " WHERE o.source_kind = 'canon'").fetchone()["n"] == 0
        assert c.post(f"/v1/conversations/{cid}/delete").status_code == 200
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        for table in ("canon_manifest", "canon_applied"):
            assert conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"] == 0
        assert conn.execute("SELECT count(*) AS n FROM source_object WHERE source_kind = 'canon'").fetchone()["n"] == 0


def test_copilot_review_of_154_a_surrogate_a_colliding_message_id_and_a_newer_observation_still_uploading(migrated):
    chat = a_chat()
    chat.messages.append({"role": "char", "data": "카드 설명처럼 보이는 메시지", "chatId": "canon:card:desc"})
    chat.user("다음.")
    t0 = int(time.time() * 1000)
    with make_client(migrated) as c:
        sync(c, chat)
        # a lone surrogate (half an emoji from a browser) hashes as U+FFFD, as the plugin's encoder does
        assert canon.content_hash("a\ud83d") == canon.content_hash("a�")
        lone = entry("note", "a\ufffd")  # what the plugin hashed; the text arrives with the lone surrogate escaped
        raw = json.dumps({"chat_id": chat.id, "entries": [lone], "contents": {lone["hash"]: "a\ud83d"}})  # \ud83d as sent
        res = c.post("/v1/sync/canon", content=raw, headers={"Content-Type": "application/json"})
        assert res.status_code == 200 and res.json()["applied"], res.text
        # a message that happens to carry a canon id is never taken as canon
        collide = entry("card:desc", DESC)
        res = c.post("/v1/sync/canon", json={"chat_id": chat.id, "entries": [collide],
                                             "contents": {collide["hash"]: DESC}})
        assert res.status_code == 422
        # the newer observation is still uploading its texts; an older upload finishing first is stale
        newer = entry("note", NOTE + " 새로")
        waiting = c.post("/v1/sync/canon", json={"chat_id": chat.id, "entries": [newer], "observed_at": t0 + 2000}).json()
        assert waiting["needed"]
        older = push(c, chat, {"note": (NOTE, {})}, t0 + 1000)
        assert (older["applied"], older["stale"]) == (False, True)
        done = push(c, chat, {"note": (NOTE + " 새로", {})}, t0 + 2000)
        assert done["applied"]


def test_a_canon_change_with_no_observation_time_is_stamped_by_the_database(migrated, monkeypatch):
    """canon_observed_at orders canon uploads (a stale one is ignored); with no observation time from the plugin it is
    the database's now(), not the sidecar's clock, which may lag or run ahead of the rows it is compared with."""
    from datetime import datetime as real, timedelta

    class Off(real):
        @classmethod
        def now(cls, tz=None):
            return real.now(tz) - timedelta(hours=1)

    monkeypatch.setattr(canon, "datetime", Off, raising=False)
    chat = SimChat("canon-clock")
    chat.user("Hello.")
    with make_client(migrated) as c:
        sync(c, chat)
        push(c, chat, {"card:desc": ("Hana is a scout.", {})})
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        row = conn.execute("SELECT canon_observed_at, now() AS db FROM conversation").fetchone()
    assert abs((row["db"] - row["canon_observed_at"]).total_seconds()) < 60
