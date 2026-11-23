"""PHASE-60 S6, A13 (ADR 0085): the carry link store (`link`, `unlink`, `in_force`, `as_of`, `by_id`, `history`).

A link stores a frozen reading: nothing that happens to the source after the link changes what the target carries.
Stub extractor only; synthetic names 세라, 카이토, 하나, 유나, 도현."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from conftest import make_client
from nmos_sidecar import carry, ledger
from nmos_sidecar.ids import uuid7
from simchat import SimChat
from test_extraction import drain as drain_extract
from test_generations import conv_id
from test_phase60_carry_take import ON, TURN_0, _build_source_chat, _keys, _stub_extract
from test_sidecar_integration import sync

TICK = timedelta(microseconds=1)


def _count(conn: psycopg.Connection) -> int:
    return conn.execute("SELECT count(*) AS n FROM conversation_carry").fetchone()["n"]


def _target(c, chat_id: str = "tgt-chat") -> UUID:
    sim = SimChat(chat_id)
    sim.user("새 이야기를 시작한다.")
    sim.reply("아침 햇살이 비춘다.")
    sync(c, sim, character_name="세라", chat_name="새 이야기", persona_name="유찬")
    return UUID(conv_id(c, sim))


def _source(c, migrated: str, turns: int = 4) -> tuple[SimChat, UUID]:
    sim = _build_source_chat(turns)
    sync(c, sim, character_name="세라", chat_name="항구의 밤", persona_name="도현")
    drain_extract(migrated, _stub_extract)
    return sim, UUID(conv_id(c, sim))


def _connect(migrated: str) -> psycopg.Connection:
    return psycopg.connect(migrated, row_factory=dict_row, autocommit=True)


def test_nothing_done_to_the_source_after_the_link_changes_what_the_target_carries(migrated: str) -> None:
    with make_client(migrated, **ON) as c:
        src_sim, src = _source(c, migrated)
        tgt = _target(c)
        with _connect(migrated) as conn:
            keys = _keys(conn, with_summary=False)
            made = carry.link(conn, tgt, src, "continue", [], keys)
            assert made["replaced"] is None and "snapshot" not in made["link"]
            before = carry.in_force(conn, tgt)
            assert before is not None and before["id"] == made["link"]["id"]
            assert before["snapshot"]["facts"] and before["snapshot"]["threads"]
            first_reading = carry.take_reading(conn, src, "continue", [], keys)
            assert first_reading["snapshot"] == before["snapshot"]

        # (i) An edit of a source message before the cutoff: a divergence, a new head, a new extraction.
        src_sim.edit(1, TURN_0.replace("피곤한 상태다", "기운이 넘치는 상태다"))
        sync(c, src_sim, character_name="세라", chat_name="항구의 밤", persona_name="도현")
        drain_extract(migrated, _stub_extract)
        with _connect(migrated) as conn:
            fresh = carry.take_reading(conn, src, "continue", [], keys)
            assert fresh["cutoff"]["commit"] != str(before["cutoff_commit_id"])
            assert carry.in_force(conn, tgt) == before

            # (ii) Membership rebuilt from the commits.
            ledger.rebuild_membership(conn, src)
            assert carry.in_force(conn, tgt) == before

        # (iii) A new extraction of the source that answers differently (no alias this time).
        def other_stub(system: str, user: str):
            ans, raw, used = _stub_extract(system, user)
            if "assertions" in ans:
                ans = {**ans, "assertions": [r for r in ans["assertions"] if r.get("predicate") != "also_called"]}
            return ans, raw, used

        assert before["snapshot"]["aliases"]
        res = c.post(f"/v1/conversations/{src}/rebuild")
        assert res.status_code == 200, res.text
        drain_extract(migrated, other_stub)
        with _connect(migrated) as conn:
            fresh = carry.take_reading(conn, src, "continue", [], keys)
            assert fresh["snapshot"]["aliases"] == []
            assert carry.in_force(conn, tgt) == before

        # (iv) An append to the source.
        src_sim.reply("세라는 바다를 바라보았다.")
        src_sim.user("계속.")
        sync(c, src_sim, character_name="세라", chat_name="항구의 밤", persona_name="도현")
        drain_extract(migrated, other_stub)
        with _connect(migrated) as conn:
            fresh = carry.take_reading(conn, src, "continue", [], keys)
            assert fresh["cutoff"]["position"] > before["cutoff_position"]
            after = carry.in_force(conn, tgt)
            assert after == before
            assert after["snapshot"] == first_reading["snapshot"]
            assert after["cutoff_commit_id"] == UUID(first_reading["cutoff"]["commit"])
            assert after["cutoff_position"] == first_reading["cutoff"]["position"]
            assert after["cutoff_turn"] == first_reading["cutoff"]["turn"]
            assert after["generations"] == first_reading["generations"]


def test_a_link_stores_its_reading_and_a_second_link_replaces_the_first(migrated: str) -> None:
    with make_client(migrated, **ON) as c:
        _, src = _source(c, migrated)
        tgt = _target(c)
        with _connect(migrated) as conn:
            keys = _keys(conn, with_summary=False)
            reading = carry.take_reading(conn, src, "continue", [], keys, cutoff_turn=1)
            first = carry.link(conn, tgt, src, "continue", [], keys, cutoff_turn=1)["link"]
            stored = carry.by_id(conn, first["id"])
            assert stored is not None
            assert stored["target_conversation_id"] == tgt and stored["source_conversation_id"] == src
            assert stored["mode"] == "continue" and stored["entity_names"] == []
            assert stored["cutoff_commit_id"] == UUID(reading["cutoff"]["commit"])
            assert stored["cutoff_position"] == reading["cutoff"]["position"]
            assert stored["cutoff_turn"] == 1
            assert stored["generations"] == reading["generations"]
            assert stored["snapshot"] == reading["snapshot"]
            assert stored["removed_at"] is None
            assert carry.in_force(conn, tgt, snapshot=False) == {k: v for k, v in stored.items() if k != "snapshot"}

            second = carry.link(conn, tgt, src, "regression", ["세라"], keys)
            assert second["replaced"] == first["id"]
            assert second["link"]["mode"] == "regression" and second["link"]["entity_names"] == ["세라"]
            old = carry.by_id(conn, first["id"])
            assert old["removed_at"] is not None
            assert old["removed_at"] == second["link"]["created_at"]
            assert carry.in_force(conn, tgt)["id"] == second["link"]["id"]

            hist = carry.history(conn, tgt)
            assert hist["in_force"]["id"] == second["link"]["id"]
            assert [x["id"] for x in hist["removed"]] == [first["id"]]
            assert "snapshot" not in hist["in_force"] and "snapshot" not in hist["removed"][0]
            assert carry.history(conn, tgt, snapshot=True)["removed"][0]["snapshot"] == reading["snapshot"]
            assert _count(conn) == 2


def test_unlink_removes_the_link_in_force_and_keeps_it_for_the_record(migrated: str) -> None:
    with make_client(migrated, **ON) as c:
        _, src = _source(c, migrated)
        tgt = _target(c)
        with _connect(migrated) as conn:
            keys = _keys(conn, with_summary=False)
            assert carry.unlink(conn, tgt) is None
            made = carry.link(conn, tgt, src, "continue", [], keys)["link"]
            removed = carry.unlink(conn, tgt)
            assert removed is not None and removed["id"] == made["id"] and removed["removed_at"] is not None
            assert "snapshot" not in removed
            assert carry.in_force(conn, tgt) is None
            assert carry.unlink(conn, tgt) is None
            hist = carry.history(conn, tgt)
            assert hist["in_force"] is None
            assert [x["id"] for x in hist["removed"]] == [made["id"]]
            # A replay reads the recorded link, removed since or not.
            assert carry.by_id(conn, made["id"])["snapshot"]["facts"]
            assert carry.by_id(conn, uuid7()) is None


def test_as_of_finds_the_one_link_in_force_at_every_instant(migrated: str) -> None:
    with make_client(migrated, **ON) as c:
        _, src = _source(c, migrated)
        tgt = _target(c)
        with _connect(migrated) as conn:
            keys = _keys(conn, with_summary=False)
            one = carry.link(conn, tgt, src, "continue", [], keys)["link"]
            two = carry.link(conn, tgt, src, "regression", ["카이토"], keys)["link"]
            t1, t2 = one["created_at"], two["created_at"]
            assert t1 < t2

            assert carry.as_of(conn, tgt, t1 - TICK) is None
            assert carry.as_of(conn, tgt, t1)["id"] == one["id"]
            assert carry.as_of(conn, tgt, t2 - TICK)["id"] == one["id"]
            assert carry.as_of(conn, tgt, t2)["id"] == two["id"]  # exactly at the replacement
            assert carry.as_of(conn, tgt, datetime.now(timezone.utc) + timedelta(hours=1))["id"] == two["id"]
            assert carry.as_of(conn, tgt, t2)["snapshot"]["mode"] == "regression"

            carry.unlink(conn, tgt)
            gone = carry.by_id(conn, two["id"])["removed_at"]
            assert carry.as_of(conn, tgt, gone - TICK)["id"] == two["id"]
            assert carry.as_of(conn, tgt, gone) is None


def test_a_stale_expect_writes_nothing_and_a_matching_one_links(migrated: str) -> None:
    with make_client(migrated, **ON) as c:
        src_sim, src = _source(c, migrated)
        tgt = _target(c)
        with _connect(migrated) as conn:
            keys = _keys(conn, with_summary=False)
            seen = carry.preview(conn, tgt, src, "continue", [], keys)

        src_sim.reply("하나는 등대 계단을 올랐다.")
        src_sim.user("그 다음은?")
        sync(c, src_sim, character_name="세라", chat_name="항구의 밤", persona_name="도현")

        with _connect(migrated) as conn:
            with pytest.raises(carry.CarryChanged) as caught:
                carry.link(conn, tgt, src, "continue", [], keys, expect=seen["fingerprint"])
            fresh = caught.value.preview
            assert fresh["fingerprint"] != seen["fingerprint"]
            assert fresh["cutoff"]["position"] > seen["cutoff"]["position"]
            assert fresh["replaces"] is None
            assert _count(conn) == 0

            made = carry.link(conn, tgt, src, "continue", [], keys, expect=fresh["fingerprint"])
            assert made["link"]["source_conversation_id"] == src
            assert _count(conn) == 1


def test_a_chat_never_carries_itself_or_an_unknown_chat(migrated: str) -> None:
    with make_client(migrated, **ON) as c:
        _, src = _source(c, migrated)
        tgt = _target(c)
        with _connect(migrated) as conn:
            keys = _keys(conn, with_summary=False)
            with pytest.raises(carry.CarryError, match="never carries itself"):
                carry.link(conn, src, src, "continue", [], keys)
            with pytest.raises(carry.NoSuchChat):
                carry.link(conn, uuid7(), src, "continue", [], keys)
            with pytest.raises(carry.NoSuchChat):
                carry.link(conn, tgt, uuid7(), "continue", [], keys)
            with pytest.raises(carry.CarryError, match="no character of the source"):
                carry.link(conn, tgt, src, "regression", ["없는사람"], keys)
            assert _count(conn) == 0
            # The table refuses a self-link anyway.
            with pytest.raises(psycopg.errors.CheckViolation):
                conn.execute(
                    "INSERT INTO conversation_carry (id, target_conversation_id, source_conversation_id, mode,"
                    " cutoff_commit_id, cutoff_position, snapshot) VALUES (%s, %s, %s, 'continue', %s, 0, %s)",
                    (uuid7(), src, src, uuid7(), Jsonb({})),
                )


def test_a_reading_never_follows_the_sources_own_link(migrated: str) -> None:
    with make_client(migrated, **ON) as c:
        # B: 하나 and 유나 at the harbour market. A: 세라 at the lighthouse. C: the target.
        b_sim = SimChat("chain-b")
        b_sim.user("시작.")
        b_sim.reply("하나는 유나와 항구 시장으로 이동했다. 하나는 상처가 나은 상태다.")
        b_sim.user("다음.")
        sync(c, b_sim, character_name="하나", persona_name="도현")
        a_sim = SimChat("chain-a")
        a_sim.user("시작.")
        a_sim.reply(TURN_0)
        a_sim.user("다음.")
        sync(c, a_sim, character_name="세라", persona_name="도현")
        drain_extract(migrated, _stub_extract)
        b, a = UUID(conv_id(c, b_sim)), UUID(conv_id(c, a_sim))
        target = _target(c, "chain-c")

        with _connect(migrated) as conn:
            keys = _keys(conn, with_summary=False)
            carry.link(conn, a, b, "continue", [], keys)
            made = carry.link(conn, target, a, "continue", [], keys)["link"]
            snap = carry.by_id(conn, made["id"])["snapshot"]
            assert snap["facts"]
            for row in (*snap["facts"], *snap["aliases"], *snap["threads"]):
                assert row["from"]["conversation"] == str(a)
            assert not any(f["subject"] in ("하나", "유나") for f in snap["facts"])
            assert "하나" not in snap["characters"]
