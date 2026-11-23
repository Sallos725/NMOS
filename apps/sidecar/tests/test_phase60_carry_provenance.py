"""PHASE-60 S6 (ADR 0085): snapshot row provenance records its source turn (`from.turn`) and `SHAPE == 3`.

Pure and DB tests; stub extractor and summarizer only; synthetic names 세라, 카이토, 하나, 유나, 도현, 유찬."""

from __future__ import annotations

from uuid import UUID

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import make_client
from nmos_sidecar import carry
from nmos_sidecar.entities import resolve
from nmos_sidecar.facts import _annotate
from nmos_sidecar.threads import fold as fold_threads
from simchat import SimChat
from test_extraction import drain as drain_extract
from test_generations import conv_id
from test_phase60_carry_reading import REP_ID, REV_1, REV_2, REV_3, SRC_ID, SUM_ID, _make_view, _row
from test_phase60_carry_take import ON, _build_source_chat, _keys, _stub_extract, _stub_summary
from test_sidecar_integration import sync
from test_summaries import drain as drain_summaries

LINK_ID = "01960000-0000-7000-8000-000000000999"


def test_provenance_turn_for_facts_aliases_threads_owner_rows_and_story() -> None:
    """Every extracted snapshot row records its source turn (`int >= 0`), threads record their opening's turn,
    owner-corrected rows (`assertion: null`), turnless rows and the story record `null`, and `SHAPE == 3`."""
    f_turn0 = _row(10, "세라", "located_in", obj="등대", object_type="place", turn=0, position=1)
    f_turn3 = _row(11, "카이토", "has_status", value="피곤함", turn=3, position=6)
    f_noturn = _row(12, "하나", "has_status", value="대기 중", turn=None, position=2)
    f_negturn = _row(13, "유나", "has_status", value="경계 중", turn=-1, position=3)
    f_owner = _row(
        -987654321, "세라", "has_status", value="건강함", turn=4, position=8,
        owner=True, repair=str(REP_ID), generation=None,
    )
    alias = _row(14, "세라", "also_called", value="세라 언니", turn=1, position=2)
    opening = _row(15, "세라", "promised", obj="카이토", object_type="character", value="열쇠를 찾아주기",
                   turn=2, position=4)

    all_rows = [f_turn0, f_turn3, f_noturn, f_negturn, f_owner, alias, opening]
    r = resolve(SRC_ID, all_rows)
    for row in all_rows:
        _annotate(row, r)
    threads, _, _ = fold_threads([opening], r)
    # Even if a thread's own `turn` were absent or shifted, provenance reads its opening's turn.
    threads[0]["turn"] = 99

    view = {
        "facts": sorted([f_turn0, f_turn3, f_noturn, f_negturn, f_owner], key=lambda f: f["position"], reverse=True),
        "threads": threads,
        "assertions": all_rows,
        "resolution": r,
        "entities": r.entities(),
        "excluded": {},
    }
    story_row = {
        "id": SUM_ID, "text": "세라와 카이토는 항구에 머물렀다.", "first_turn": 0, "last_turn": 4,
        "generation": "summarize:s1",
    }

    revs = {10: REV_1, 11: REV_2, 12: REV_1, 13: REV_1, 14: REV_2, 15: REV_3}
    cont = carry.snapshot_of(view, {"story": story_row, "story_held": []}, "continue", [], SRC_ID, revs)
    assert cont["shape"] == carry.SHAPE == 3

    by_assertion = {f["from"]["assertion"]: f for f in cont["facts"] if f["from"]["assertion"] is not None}
    assert by_assertion[10]["from"]["turn"] == 0
    assert by_assertion[11]["from"]["turn"] == 3
    assert by_assertion[12]["from"]["turn"] is None
    assert by_assertion[13]["from"]["turn"] is None

    owner_row = next(f for f in cont["facts"] if f["from"]["repair"] == str(REP_ID))
    assert owner_row["from"]["assertion"] is None
    assert owner_row["from"]["turn"] is None

    assert len(cont["aliases"]) == 1
    assert cont["aliases"][0]["from"]["turn"] == 1

    assert len(cont["threads"]) == 1
    assert cont["threads"][0]["from"]["turn"] == 2  # opening's turn

    assert cont["story"] is not None
    assert cont["story"]["first_turn"] == 0 and cont["story"]["last_turn"] == 4
    assert cont["story"]["from"]["turn"] is None

    # `target_rows` copies `from` as `carried_from` for both continue and regression.
    carried_cont = carry.target_rows({
        "id": LINK_ID, "source_conversation_id": str(SRC_ID), "mode": "continue", "snapshot": cont,
    })
    by_carried_id = {row["carried_from"]["assertion"]: row for row in carried_cont.rows
                     if row["carried_from"]["assertion"] is not None}
    assert by_carried_id[10]["carried_from"]["turn"] == 0 and by_carried_id[10]["turn"] == -1
    assert by_carried_id[15]["carried_from"]["turn"] == 2 and by_carried_id[15]["turn"] == -1
    owner_carried = next(row for row in carried_cont.rows if row["carried_from"]["repair"] == str(REP_ID))
    assert owner_carried["carried_from"]["turn"] is None
    assert carried_cont.story is not None and carried_cont.story["from"]["turn"] is None

    reg = carry.snapshot_of(view, None, "regression", ["세라"], SRC_ID, revs)
    assert reg["shape"] == 3
    reg_fact = next(f for f in reg["facts"] if f["from"]["assertion"] == 10)
    assert reg_fact["from"]["turn"] == 0
    reg_owner = next(f for f in reg["facts"] if f["from"]["repair"] == str(REP_ID))
    assert reg_owner["from"]["turn"] is None
    assert reg["threads"][0]["from"]["turn"] == 2

    carried_reg = carry.target_rows({
        "id": LINK_ID, "source_conversation_id": str(SRC_ID), "mode": "regression", "snapshot": reg,
    })
    assert any(r["line"] == "fact" and r["carried_from"]["assertion"] == 10 and r["carried_from"]["turn"] == 0
               for r in carried_reg.regression)
    assert any(r["line"] == "thread" and r["carried_from"]["assertion"] == 15 and r["carried_from"]["turn"] == 2
               for r in carried_reg.regression)


def test_db_take_reading_and_linked_views_record_source_turn_provenance(migrated: str) -> None:
    """End-to-end DB check: extracted facts, alias, thread, owner-corrected fact, and story all record `from.turn`,
    and the linked target's `/facts` exposes `carried_from.turn`."""
    with make_client(migrated, **ON) as c:
        src_sim = _build_source_chat(13)
        sync(c, src_sim, character_name="세라", chat_name="항구의 밤", persona_name="도현")
        drain_extract(migrated, _stub_extract)
        drain_summaries(migrated, _stub_summary)
        src_id = UUID(conv_id(c, src_sim))

        # Owner-correct one source fact (`세라 has_status 피곤함` -> `기운참`) so it becomes an owner row.
        src_facts = c.get(f"/v1/conversations/{src_id}/facts").json()
        sera_status = next(f for f in src_facts if f["subject"] == "세라" and f["predicate"] == "has_status")
        rep_res = c.post(f"/v1/conversations/{src_id}/repairs", json={
            "kind": "fact_correct", "item": str(sera_status["id"]), "new_value": "기운참", "note": "주인 수정",
        })
        assert rep_res.status_code == 200, rep_res.text
        repair_id = rep_res.json()["repair"]["id"]

        tgt_sim = SimChat("tgt-prov-chat")
        tgt_sim.user("새 이야기를 시작한다.")
        tgt_sim.reply("아침 햇살이 비춘다.")
        sync(c, tgt_sim, character_name="세라", chat_name="새 이야기", persona_name="유찬")
        tgt_id = conv_id(c, tgt_sim)

        with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
            keys = _keys(conn, with_summary=True)
            reading = carry.take_reading(conn, src_id, "continue", [], keys)
            snap = reading["snapshot"]
            assert snap["shape"] == carry.SHAPE == 3

            sera_loc = next(f for f in snap["facts"] if f["subject"] == "세라" and f["predicate"] == "located_in")
            assert sera_loc["from"]["turn"] == 0
            hana_loc = next(f for f in snap["facts"] if f["subject"] == "하나" and f["predicate"] == "located_in")
            assert hana_loc["from"]["turn"] == 2

            repaired = next(f for f in snap["facts"] if f["subject"] == "세라" and f["predicate"] == "has_status")
            assert repaired["value"] == "기운참"
            assert repaired["from"]["assertion"] is None
            assert repaired["from"]["repair"] == repair_id
            assert repaired["from"]["turn"] is None

            alias = next(a for a in snap["aliases"] if a["alias"] == "등대지기")
            assert alias["from"]["turn"] == 1

            (thread,) = snap["threads"]
            assert thread["from"]["turn"] == 1

            assert snap["story"] is not None
            assert snap["story"]["from"]["turn"] is None

        # Link target and check `carried_from.turn` via `/v1/conversations/{tgt}/facts`.
        link_res = c.post(f"/v1/conversations/{tgt_id}/carry",
                          json={"source_conversation_id": str(src_id), "mode": "continue"})
        assert link_res.status_code == 200, link_res.text
        tgt_facts = c.get(f"/v1/conversations/{tgt_id}/facts").json()
        carried_loc = next(f for f in tgt_facts if f["subject"] == "하나" and f["predicate"] == "located_in")
        assert carried_loc["carried_from"]["turn"] == 2
        carried_rep = next(f for f in tgt_facts if f["subject"] == "세라" and f["predicate"] == "has_status")
        assert carried_rep["carried_from"]["repair"] == repair_id
        assert carried_rep["carried_from"]["turn"] is None


def test_too_many_rows_exception_shape() -> None:
    err = carry.TooManyRows(2005, 2000)
    assert isinstance(err, carry.CarryError)
    assert err.rows == 2005
    assert err.max == 2000
    assert str(err) == "the reading holds 2005 rows; a link carries at most 2000"


def test_row_cap_refusal_returns_422_string_with_counts_on_preview_and_link(
    migrated: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exceeding `carry.MAX_ROWS` raises `TooManyRows` and answers 422 with a stable string detail
    `too_many_rows: rows=<N> max=<M> (<message>)` on both preview and link, while other `CarryError` refusals stay
    unchanged."""
    with make_client(migrated, **ON) as c:
        src_sim = _build_source_chat(4)
        sync(c, src_sim, character_name="세라", chat_name="항구의 밤", persona_name="도현")
        drain_extract(migrated, _stub_extract)
        src_id = conv_id(c, src_sim)

        tgt_sim = SimChat("tgt-cap-chat")
        tgt_sim.user("새 이야기를 시작한다.")
        tgt_sim.reply("아침 햇살이 비춘다.")
        sync(c, tgt_sim, character_name="세라", chat_name="새 이야기", persona_name="유찬")
        tgt_id = conv_id(c, tgt_sim)

        prev = c.post(f"/v1/conversations/{tgt_id}/carry/preview",
                      json={"source_conversation_id": src_id, "mode": "continue"}).json()
        counts = prev["counts"]
        total = counts["facts"] + counts["aliases"] + counts["threads"]
        assert total > 2

        monkeypatch.setattr(carry, "MAX_ROWS", 2)

        with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
            keys = _keys(conn, with_summary=False)
            with pytest.raises(carry.TooManyRows) as caught:
                carry.take_reading(conn, src_id, "continue", [], keys)
            assert caught.value.rows == total
            assert caught.value.max == 2
            assert str(caught.value) == f"the reading holds {total} rows; a link carries at most 2"

        msg = f"the reading holds {total} rows; a link carries at most 2"
        expected = f"too_many_rows: rows={total} max=2 ({msg})"
        for path in (f"/v1/conversations/{tgt_id}/carry/preview", f"/v1/conversations/{tgt_id}/carry"):
            res = c.post(path, json={"source_conversation_id": src_id, "mode": "continue"})
            assert res.status_code == 422, res.text
            detail = res.json()["detail"]
            assert isinstance(detail, str)
            assert detail.startswith("too_many_rows: rows=")
            assert f"rows={total}" in detail and "max=2" in detail
            assert detail == expected

        # Other CarryErrors stay plain strings without the too_many_rows prefix.
        other = c.post(f"/v1/conversations/{src_id}/carry/preview",
                       json={"source_conversation_id": src_id, "mode": "continue"})
        assert other.status_code == 422
        assert isinstance(other.json()["detail"], str) and "never carries itself" in other.json()["detail"]
        assert not other.json()["detail"].startswith("too_many_rows:")

        with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
            assert conn.execute("SELECT count(*) AS n FROM conversation_carry").fetchone()["n"] == 0

