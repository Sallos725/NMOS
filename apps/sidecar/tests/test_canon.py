"""Canon sources (Phase 14 step 3, ADR 0045): capture as immutable revisions, the canon in force, replays, what a
prompt held, the Inspector, deletion, and that no message pipeline sees canon."""

from __future__ import annotations

from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

from conftest import make_client
from nmos_sidecar import canon
from simchat import SimChat
from test_sidecar_integration import recall, sync

DESC = "하나는 항구 마을 등대지기의 딸이다. 하나의 눈은 푸른색이다."
LORE = "카이토는 견습 기사이고 하나의 소꿉친구다."
NOTE = "지금은 한겨울 밤이다."


def entry(key: str, text: str, **metadata) -> dict:
    return {"key": key, "hash": canon.content_hash(text), "metadata": metadata}


def push(c, chat: SimChat, texts: dict[str, tuple[str, dict]]) -> dict:
    """The plugin's two calls: the manifest, then the texts the sidecar asked for."""
    entries = [entry(k, text, **meta) for k, (text, meta) in texts.items()]
    res = c.post("/v1/sync/canon", json={"chat_id": chat.id, "entries": entries})
    assert res.status_code == 200, res.text
    out = res.json()
    if out["needed"]:
        by_hash = {canon.content_hash(text): text for text, _ in texts.values()}
        res = c.post("/v1/sync/canon", json={"chat_id": chat.id, "entries": entries,
                                             "contents": {h: by_hash[h] for h in out["needed"]}})
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


def test_canon_is_stored_once_and_made_the_canon_in_force(migrated):
    chat = a_chat()
    with make_client(migrated) as c:
        sync(c, chat)
        texts = {"card:desc": (DESC, {"field": "desc"}), "note": (NOTE, {}),
                 "lore:kaito": (LORE, {"scope": "character", "mode": "normal", "keys": ["카이토", "카이"]})}
        first = c.post("/v1/sync/canon", json={"chat_id": chat.id,
                                               "entries": [entry(k, t, **m) for k, (t, m) in texts.items()]}).json()
        assert sorted(first["needed"]) == sorted(canon.content_hash(t) for t, _ in texts.values())
        assert first["in_force"] is None  # nothing changes until every text is there
        out = push(c, chat, texts)
        assert (out["needed"], out["stored"], out["changed"], out["in_force"]) == ([], 3, 3, 3)
        again = push(c, chat, texts)  # the same canon: nothing to send, nothing changed
        assert (again["needed"], again["stored"], again["changed"]) == ([], 0, 0)
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        rows = canon.in_force(conn, conv_id(migrated, chat))
        assert [(r["key"], r["content"], r["versions"]) for r in rows] == [
            ("card:desc", DESC, 1), ("lore:kaito", LORE, 1), ("note", NOTE, 1)]
        assert rows[1]["metadata"] == {"canon": "lore", "scope": "character", "mode": "normal", "keys": ["카이토", "카이"]}


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


def test_an_edit_makes_a_new_version_and_a_removal_ends_one_and_a_replay_sees_the_old_canon(migrated):
    chat = a_chat()
    with make_client(migrated) as c:
        sync(c, chat)
        push(c, chat, {"card:desc": (DESC, {}), "note": (NOTE, {})})
        before = datetime.now(timezone.utc)
        edited = DESC + " 하나는 열여섯 살이다."
        out = push(c, chat, {"card:desc": (edited, {})})  # the note is gone from the host
        assert (out["stored"], out["changed"], out["in_force"]) == (1, 2, 1)
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        cid = conv_id(migrated, chat)
        now = canon.in_force(conn, cid)
        assert [(r["key"], r["content"], r["versions"]) for r in now] == [("card:desc", edited, 2)]
        then = canon.in_force(conn, cid, before)
        assert [(r["key"], r["content"]) for r in then] == [("card:desc", DESC), ("note", NOTE)]
        # The old text is kept, immutable, as history (invariant 1).
        n = conn.execute("SELECT count(*) AS n FROM source_revision sr JOIN source_object so ON so.id = sr.source_object_id"
                         " WHERE so.conversation_id = %s AND so.source_kind = 'canon'", (cid,)).fetchone()["n"]
        assert n == 3


def test_a_request_records_the_canon_its_prompt_held_and_the_inspector_lists_canon(migrated):
    chat = a_chat()
    with make_client(migrated) as c:
        sync(c, chat)
        push(c, chat, {"card:desc": (DESC, {}), "lore:kaito": (LORE, {"scope": "character", "mode": "normal",
                                                                        "keys": ["카이토"]})})
        recall(c, chat, "카이토는 어디 있어?", canon_held=["lore:kaito", "card:desc"])
        recall(c, chat, "카이토는 어디 있어?", canon_held=["card:desc"])
        cid = conv_id(migrated, chat)
        page = c.get(f"/inspector/c/{cid}", params={"lang": "en"}).text
        section = page[page.index('id="s-canon"'):page.index("</details>", page.index('id="s-canon"'))]
        assert "Canon (card, lorebooks, persona, author" in section and "lore:kaito" in section
        assert "2×, last" in section and "1×, last" in section and "character · normal · 1 keys" in section
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        held = canon.held(conn, cid)
        assert {k: v["requests"] for k, v in held.items()} == {"card:desc": 2, "lore:kaito": 1}


def test_canon_reaches_no_message_pipeline_and_goes_with_the_chat(migrated):
    chat = a_chat()
    with make_client(migrated) as c:
        sync(c, chat)
        # A card holding a status block: a state rule must not read canon, on sync or on a rebuild.
        rules = {"rules": [{"id": "r", "kind": "block", "start": "<status>", "end": "</status>",
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
        assert conn.execute("SELECT count(*) AS n FROM canon_state").fetchone()["n"] == 0
        assert conn.execute("SELECT count(*) AS n FROM source_object WHERE source_kind = 'canon'").fetchone()["n"] == 0
