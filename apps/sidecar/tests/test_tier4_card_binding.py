"""Tier 4 G7.2 (PHASE-67 part 3): status rules, status history and pins are bound to the host's card ref, so a card
rename in the host loses nothing. A chat without a ref is read by its name, as before."""

from __future__ import annotations

import json

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from conftest import make_client
from nmos_sidecar import api, state
from simchat import SimChat
from test_sidecar_integration import recall, sync
from test_status_shape import bar, conversation, story

CARD = "Lantern Keeper"
RENAMED = "Lantern Keeper (arc 2)"
REF = "0b9c4f2e-7d1a-4c55-9e0f-3a8b6d2c1e47"  # a card's id as the host sends it (`saying` of its first reply)
OTHER_REF = "5e2d8a10-4b3c-4f6e-8d7a-9c1b2e3f4a50"
SHAPE = {"id": "status", "kind": "shape", "role": "char", "keys": ["date", "hp", "place", "items"]}
# The parser document and pins exactly as the base commit's code (f9ffe3b `runtime.bind_card`, `put_status_pins`)
# wrote them for this card: bound by display name, no card ref anywhere.
BASE_PARSERS = {"rules": [{"id": "card-fb375f7d4673c17e:0:status", "kind": "shape", "role": "char",
                           "keys": ["date", "hp", "place", "items"], "card": CARD}]}
BASE_PINS = {CARD: ["items"]}


def rows(url: str, sql: str, *params):
    with psycopg.connect(url, row_factory=dict_row) as conn:
        return conn.execute(sql, params).fetchall()


def observations(url: str, chat: SimChat) -> list[tuple]:
    return [(r["id"], r["source_revision_id"], r["rules_version"], r["key"], r["value"]) for r in rows(
        url, "SELECT st.* FROM state_observation st JOIN conversation c ON c.id = st.conversation_id"
             " WHERE c.host_chat_ref = %s ORDER BY st.id", chat.id)]


def bindings(url: str) -> dict:
    found = rows(url, "SELECT value FROM app_config WHERE key = %s", state.CARD_BINDINGS_KEY)
    return found[0]["value"] if found else {}


def write_base_config(url: str) -> None:
    with psycopg.connect(url) as conn:
        for key, value in (("parsers", BASE_PARSERS), ("status_pins", BASE_PINS)):
            conn.execute("INSERT INTO app_config (key, value) VALUES (%s, %s)"
                         " ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", (key, Jsonb(value)))


@pytest.fixture
def reparses(monkeypatch):
    calls: list = []
    real = api.reparse_conversation

    def counted(conn, ruleset, conv_id):
        calls.append(conv_id)
        return real(conn, ruleset, conv_id)
    monkeypatch.setattr(api, "reparse_conversation", counted)
    return calls


def test_a_rename_keeps_the_history_the_rules_and_the_pins(migrated, reparses):
    """Item 2, the full path: sync under name A with a status window, pin a key, rename to B, sync again."""
    chat = story()
    with make_client(migrated, packet_policy="packet-v18") as c:
        sync(c, chat, character_name=CARD, character_ref=REF)
        conv = conversation(migrated, chat)
        [cand] = c.get(f"/v1/conversations/{conv}/status/candidates").json()["candidates"]
        assert c.post("/v1/parsers/card/track", json={"card": CARD, "keys": cand["keys"]}).status_code == 200
        assert c.put("/v1/parsers/card/pins", json={"card": CARD, "keys": ["items"]}).json() == {
            "card": CARD, "pins": ["items"]}
        before = observations(migrated, chat)
        assert before and bindings(migrated) == {REF: CARD}
        config = c.get("/v1/config").json()["parsers"]
        reparses.clear()

        chat.reply(bar(5, 120, items="물약 ×1 / 열쇠"))
        chat.user("다음.")
        sync(c, chat, character_name=RENAMED, character_ref=REF)  # renamed in the host; the same card
        assert reparses == []  # the rename alone reads nothing again
        after = observations(migrated, chat)
        assert after[:len(before)] == before  # no row deleted or rewritten, same rules version
        assert len(after) > len(before) and {r[2] for r in after} == {before[0][2]}
        assert c.get("/v1/config").json()["parsers"] == config  # the rule document did not change
        assert rows(migrated, "SELECT host_character_name FROM conversation WHERE id = %s", conv)[0][
            "host_character_name"] == RENAMED  # the label follows the host

        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            head = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (conv,)).fetchone()[
                "head_commit_id"]
            hp = [e["value"] for e in state.history(conn, head, before[0][2])["hp"]]
        assert hp == ["200 / 200", "180 / 200", "150 / 200", "120 / 200"]  # both names' turns, one history

        out = recall(c, chat, "다음.", budget=1200)
        assert '<Item key="items"' in out["packet"]["text"] and "물약 ×1 / 열쇠" in out["packet"]["text"]
        assert c.get(f"/v1/trace/{out['trace_id']}").json()["recall_options"]["state_pins"] == ["items"]

        found = c.get(f"/v1/conversations/{conv}/status/candidates").json()
        assert found["card"] == CARD and found["card_name"] == RENAMED and found["pins"] == ["items"]
        assert all(x["tracked"] for x in found["candidates"])
        # The plugin sends back the card it was given: the write replaces this card's pins, no second set.
        assert c.put("/v1/parsers/card/pins", json={"card": found["card"], "keys": ["hp"]}).json() == {
            "card": CARD, "pins": ["hp"]}
        assert json.loads(json.dumps(rows(migrated, "SELECT value FROM app_config WHERE key = 'status_pins'")[0][
            "value"])) == {CARD: ["hp"]}
        # A write by the new label (Settings, typed) lands on the card the chat is read under.
        assert c.put("/v1/parsers/card/pins", json={"card": RENAMED, "keys": ["items"]}).json()["card"] == CARD
        assert '<Item key="items"' in recall(c, chat, "다음.", budget=1200)["packet"]["text"]


def test_a_configuration_written_by_the_base_commit_applies_with_no_owner_action(migrated, reparses):
    """Item 3: pins and rules saved by name before this change, chats synced before it (refs stored, no binding):
    after the deploy nothing stops matching, and a rename on the first sync after the deploy keeps them."""
    chat = story()
    with make_client(migrated, packet_policy="packet-v18") as c:
        sync(c, chat, character_name=CARD, character_ref=REF)
    with psycopg.connect(migrated) as conn:  # the base commit never wrote a binding
        conn.execute("DELETE FROM app_config WHERE key = %s", (state.CARD_BINDINGS_KEY,))
    write_base_config(migrated)
    with make_client(migrated, packet_policy="packet-v18") as c:  # the deploy: the stored configuration as it is
        conv = conversation(migrated, chat)
        found = c.get(f"/v1/conversations/{conv}/status/candidates").json()
        assert found["card"] == CARD and found["pins"] == ["items"] and found["candidates"][0]["tracked"]
        assert '<Item key="items"' in recall(c, chat, "다음.", budget=1200)["packet"]["text"]
        before = observations(migrated, chat)
        assert before
        chat.reply(bar(5, 120))
        chat.user("다음.")
        sync(c, chat, character_name=RENAMED, character_ref=REF)  # renamed while the old image ran
        assert bindings(migrated) == {REF: CARD}  # bound to the name its rules and pins were saved under
        assert reparses == [] and observations(migrated, chat)[:len(before)] == before
        assert '<Item key="items"' in recall(c, chat, "다음.", budget=1200)["packet"]["text"]
        # A chat without a ref stays name-keyed and reads the same name's entries, as before.
        plain = story(((7, 90), (8, 80), (8, 70)))
        sync(c, plain, character_name=CARD)
        assert c.get(f"/v1/conversations/{conversation(migrated, plain)}/status/candidates").json()["pins"] == [
            "items"]
        assert "1214년 9월 8일" in recall(c, plain, "다음.", budget=1200)["packet"]["text"]
    assert bindings(migrated) == {REF: CARD}


def test_a_ref_that_arrives_later_binds_the_name_and_a_new_chat_of_the_renamed_card_is_read_under_it(migrated,
                                                                                                    reparses):
    """The ref is null until a reply carries the card's id: the name it was read under so far is the one bound. A
    later chat of the card, first seen with no ref under the new label, is read again once its ref arrives."""
    write_base_config(migrated)
    chat = story()
    with make_client(migrated, packet_policy="packet-v18") as c:
        sync(c, chat, character_name=CARD)  # no ref yet: by name
        conv = conversation(migrated, chat)
        assert c.get(f"/v1/conversations/{conv}/status/candidates").json()["pins"] == ["items"]
        before = observations(migrated, chat)
        sync(c, chat, character_name=CARD, character_ref=REF)
        assert bindings(migrated) == {REF: CARD} and observations(migrated, chat) == before
        reparses.clear()
        sync(c, chat, character_name=RENAMED, character_ref=REF)
        assert reparses == [] and observations(migrated, chat) == before

        fresh = SimChat()  # a new chat of the renamed card, before its first reply: no ref
        fresh.user("시작.")
        sync(c, fresh, character_name=RENAMED)
        fresh.reply(bar(9, 60))
        fresh.user("다음.")
        sync(c, fresh, character_name=RENAMED, character_ref=REF)  # its ref arrives: the card it is read under changes
        fid = conversation(migrated, fresh)
        assert reparses[-1] == fid  # (its first sync, a new chat, is read once too: nothing there yet)
        found = c.get(f"/v1/conversations/{fid}/status/candidates")
        assert found.status_code == 200 and found.json()["card"] == CARD
        assert "1214년 9월 9일" in recall(c, fresh, "다음.", budget=1200)["packet"]["text"]
        assert bindings(migrated) == {REF: CARD}  # never rebound


def test_two_cards_sharing_a_name_are_not_merged_and_none_captures_the_others_pins(migrated):
    """Item 3's rule: each ref is bound on its own to the name it had when first seen, and a binding never moves an
    entry from one card to another. Two cards first seen under one name read that name's entries, as they did before
    the deploy; a write by a label shared by cards read under different names is taken as written."""
    write_base_config(migrated)
    x, y = story(), story(((7, 90), (8, 80), (8, 70)))
    with make_client(migrated, packet_policy="packet-v18") as c:
        sync(c, x, character_name=CARD, character_ref=REF)
        sync(c, y, character_name=CARD, character_ref=OTHER_REF)
        assert bindings(migrated) == {REF: CARD, OTHER_REF: CARD}
        x.reply(bar(5, 120))
        x.user("다음.")
        sync(c, x, character_name=RENAMED, character_ref=REF)
        for chat in (x, y):  # the first seen did not take the other's pins
            assert c.get(f"/v1/conversations/{conversation(migrated, chat)}/status/candidates").json()["pins"] == [
                "items"]
        z = story(((2, 50), (2, 40), (3, 40)))  # a third card, first seen under x's new label
        sync(c, z, character_name=RENAMED, character_ref="9a7b6c5d-1e2f-4a3b-8c9d-0e1f2a3b4c5d")
        zid = conversation(migrated, z)
        assert c.get(f"/v1/conversations/{zid}/status/candidates").json()["card"] == RENAMED  # not x's card
        # The label RENAMED is x's (read under CARD) and z's (read under RENAMED): a write by it stays on RENAMED.
        assert c.put("/v1/parsers/card/pins", json={"card": RENAMED, "keys": ["hp"]}).json()["card"] == RENAMED
        assert c.get(f"/v1/conversations/{conversation(migrated, x)}/status/candidates").json()["pins"] == ["items"]
        # The optional conversation_id names the chat, so the write lands on its card whatever the label.
        out = c.put("/v1/parsers/card/pins", json={"card": RENAMED, "keys": ["date"],
                                                   "conversation_id": str(conversation(migrated, x))}).json()
        assert out == {"card": CARD, "pins": ["date"]}
        assert c.get(f"/v1/conversations/{conversation(migrated, y)}/status/candidates").json()["pins"] == ["date"]
        assert c.put("/v1/parsers/card/pins", json={"card": CARD, "keys": [], "conversation_id": "nope"}
                     ).status_code == 422


def test_a_chat_without_a_ref_renamed_is_read_again_in_one_transaction(migrated, monkeypatch, tmp_path):
    """Item 4: with no ref a rename still changes the card (as before); the delete and the rewrite are one transaction,
    so a failure between them keeps the chat's rows."""
    path = tmp_path / "rules.json"
    path.write_text(json.dumps({"rules": [{**SHAPE, "card": CARD}]}), encoding="utf-8")
    chat = story()
    with make_client(migrated, parsers_file=str(path), packet_policy="packet-v18") as c:
        sync(c, chat, character_name=CARD)
        before = observations(migrated, chat)
        assert before
        conv = conversation(migrated, chat)

        def broken(*_a, **_k):
            raise RuntimeError("parse failed")
        from nmos_sidecar import parsers
        rules = parsers.load_rules(str(path))
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            monkeypatch.setattr(state, "_parse", broken)
            with pytest.raises(RuntimeError):
                state.reparse_conversation(conn, rules, conv)
            assert conn.execute("SELECT count(*) AS n FROM state_observation WHERE conversation_id = %s",
                                (conv,)).fetchone()["n"] == len(before)  # same transaction: the delete was undone
        monkeypatch.undo()
        sync(c, chat, character_name=RENAMED)  # no ref: the chat is read under its new name, as before G7.2
        assert observations(migrated, chat) == []


def test_a_replay_reads_the_pins_its_request_recorded(migrated):
    """Item 6 (ADR 0027): a request records the pins it used; changing the pins and renaming the card later changes
    neither its record nor its replay."""
    chat = story()
    with make_client(migrated, packet_policy="packet-v18") as c:
        sync(c, chat, character_name=CARD, character_ref=REF)
        [cand] = c.get(f"/v1/conversations/{conversation(migrated, chat)}/status/candidates").json()["candidates"]
        c.post("/v1/parsers/card/track", json={"card": CARD, "keys": cand["keys"]})
        c.put("/v1/parsers/card/pins", json={"card": CARD, "keys": ["items"]})
        out = recall(c, chat, "다음.", budget=1200)
        assert '<Item key="items"' in out["packet"]["text"]
        c.put("/v1/parsers/card/pins", json={"card": CARD, "keys": ["place"]})
        sync(c, chat, character_name=RENAMED, character_ref=REF)
        assert c.get(f"/v1/trace/{out['trace_id']}").json()["recall_options"]["state_pins"] == ["items"]
        assert c.get(f"/v1/trace/{out['trace_id']}/replay").json()["reproduced"] is True
        now = recall(c, chat, "다음.", budget=1200)["packet"]["text"]
        assert '<Item key="place"' in now and '<Item key="items"' not in now  # the pins in force now are told now


def test_the_status_flags_of_a_renamed_card_stay(migrated, tmp_path):
    """Every reader of the chat's card goes through its binding: the flags (PHASE-39 Q4) read the same card after a
    rename as before it."""
    import re
    from test_state_history import RULE, bar as gold_bar
    path = tmp_path / "rules.json"
    path.write_text(json.dumps({"rules": [{**RULE, "card": CARD, "watch": ["Gold"]}]}), encoding="utf-8")
    chat = SimChat()
    chat.user("시작.")
    chat.reply(gold_bar(1, 100))
    chat.user("쉰다.")
    chat.reply(gold_bar(1, 70))  # Gold changed without the reply saying so
    chat.user("다음.")
    with make_client(migrated, parsers_file=str(path)) as c:
        sync(c, chat, character_name=CARD, character_ref=REF)
        conv = conversation(migrated, chat)
        flags = lambda: re.findall(r'data-repair="state_dismiss:([0-9a-f]{16})"',  # noqa: E731
                                   c.get(f"/v1/inspector/c/{conv}?lang=en").json()["html"])
        before = flags()
        assert len(before) == 1
        sync(c, chat, character_name=RENAMED, character_ref=REF)
        assert flags() == before
