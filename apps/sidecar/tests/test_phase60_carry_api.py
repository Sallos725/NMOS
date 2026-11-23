"""PHASE-60 S6 (ADR 0085): the carry API. Thin routes over `carry.py`; every decision is tested there.

Stub extractor only; synthetic names 세라, 카이토, 하나, 유나, 도현."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from conftest import make_client
from nmos_sidecar import archive
from nmos_sidecar.ids import uuid7
from simchat import SimChat
from test_extraction import drain as drain_extract
from test_generations import conv_id
from test_phase60_carry_take import ON, _build_source_chat, _stub_extract
from test_sidecar_integration import sync

SOURCE_LABELS = {"character_name": "세라", "chat_name": "항구의 밤", "persona_name": "도현"}


def _pair(c, migrated: str) -> tuple[SimChat, str, str]:
    src_sim = _build_source_chat(4)
    sync(c, src_sim, **SOURCE_LABELS)
    drain_extract(migrated, _stub_extract)
    tgt_sim = SimChat("tgt-chat")
    tgt_sim.user("새 이야기를 시작한다.")
    tgt_sim.reply("아침 햇살이 비춘다.")
    sync(c, tgt_sim, character_name="세라", chat_name="새 이야기", persona_name="유찬")
    return src_sim, conv_id(c, src_sim), conv_id(c, tgt_sim)


def _rows(url: str) -> list[dict]:
    with psycopg.connect(url, row_factory=dict_row) as conn:
        return conn.execute("SELECT * FROM conversation_carry ORDER BY created_at, id").fetchall()


def test_preview_then_link_then_the_link_is_in_force(migrated: str) -> None:
    with make_client(migrated, **ON) as c:
        _, src, tgt = _pair(c, migrated)
        assert c.get(f"/v1/conversations/{tgt}/carry").json() == {"in_force": None, "removed": []}

        body = {"source_conversation_id": src, "mode": "continue"}
        res = c.post(f"/v1/conversations/{tgt}/carry/preview", json={**body, "expect": "ignored"})
        assert res.status_code == 200, res.text
        seen = res.json()
        assert seen["source"] == {"id": src, "character": "세라", "chat": "항구의 밤"}
        assert seen["counts"]["facts"] > 0 and seen["replaces"] is None
        assert _rows(migrated) == []

        res = c.post(f"/v1/conversations/{tgt}/carry", json={**body, "expect": seen["fingerprint"]})
        assert res.status_code == 200, res.text
        made = res.json()
        assert made["replaced"] is None and "snapshot" not in made["link"]
        assert made["link"]["source_conversation_id"] == src and made["link"]["mode"] == "continue"

        got = c.get(f"/v1/conversations/{tgt}/carry").json()
        assert got["removed"] == []
        link = got["in_force"]
        assert link["id"] == made["link"]["id"] and "snapshot" not in link
        assert link["source"] == {"id": src, "character": "세라", "chat": "항구의 밤"}
        assert link["cutoff_turn"] == seen["cutoff"]["turn"]

        full = c.get(f"/v1/conversations/{tgt}/carry", params={"snapshot": True}).json()["in_force"]
        (stored,) = _rows(migrated)
        assert full["snapshot"] == stored["snapshot"]
        assert len(full["snapshot"]["facts"]) == seen["counts"]["facts"]

        assert c.get(f"/v1/conversations/{uuid7()}/carry").status_code == 404


def test_a_stale_fingerprint_answers_409_with_a_fresh_preview_and_writes_nothing(migrated: str) -> None:
    with make_client(migrated, **ON) as c:
        src_sim, src, tgt = _pair(c, migrated)
        body = {"source_conversation_id": src, "mode": "continue"}
        seen = c.post(f"/v1/conversations/{tgt}/carry/preview", json=body).json()

        src_sim.reply("하나는 등대 계단을 올랐다.")
        src_sim.user("그 다음은?")
        sync(c, src_sim, **SOURCE_LABELS)

        res = c.post(f"/v1/conversations/{tgt}/carry", json={**body, "expect": seen["fingerprint"]})
        assert res.status_code == 409, res.text
        detail = res.json()["detail"]
        assert detail["message"] == "the source changed since its preview"
        assert detail["preview"]["fingerprint"] != seen["fingerprint"]
        assert detail["preview"]["cutoff"]["position"] > seen["cutoff"]["position"]
        assert _rows(migrated) == []


def test_refusals(migrated: str) -> None:
    with make_client(migrated, **ON) as c:
        _, src, tgt = _pair(c, migrated)
        for path in (f"/v1/conversations/{tgt}/carry/preview", f"/v1/conversations/{tgt}/carry"):
            def post(**kw):
                return c.post(path, json={"source_conversation_id": src, "mode": "continue", **kw})

            res = c.post(path.replace(tgt, src), json={"source_conversation_id": src, "mode": "continue"})
            assert res.status_code == 422 and "never carries itself" in res.json()["detail"]
            assert post(source_conversation_id=str(uuid7())).status_code == 404
            assert c.post(path.replace(tgt, str(uuid7())),
                          json={"source_conversation_id": src, "mode": "continue"}).status_code == 404
            assert post(mode="regression").status_code == 422
            res = post(mode="regression", entity_names=["세라", "없는사람"])
            assert res.status_code == 422 and "없는사람 is no character of the source" in res.json()["detail"]
            assert post(entity_names=["세라"]).status_code == 422
            res = post(cutoff_turn=99)
            assert res.status_code == 422 and "turn 99" in res.json()["detail"]

            # The body's own refusals (CarryRequest).
            assert post(mode="sideways").status_code == 422
            assert post(mode="regression", entity_names=["세라"] * 9).status_code == 422
            assert post(mode="regression", entity_names=[""]).status_code == 422
            assert post(cutoff_turn=-1).status_code == 422
            assert c.post(path, json={"mode": "continue"}).status_code == 422
        assert _rows(migrated) == []


def test_a_second_link_replaces_the_first_and_delete_removes_it(migrated: str) -> None:
    with make_client(migrated, **ON) as c:
        _, src, tgt = _pair(c, migrated)
        first = c.post(f"/v1/conversations/{tgt}/carry",
                       json={"source_conversation_id": src, "mode": "continue", "cutoff_turn": 1}).json()["link"]
        res = c.post(f"/v1/conversations/{tgt}/carry",
                     json={"source_conversation_id": src, "mode": "regression", "entity_names": ["세라"]})
        assert res.status_code == 200, res.text
        second = res.json()
        assert second["replaced"] == first["id"]
        assert second["link"]["entity_names"] == ["세라"]

        got = c.get(f"/v1/conversations/{tgt}/carry").json()
        assert got["in_force"]["id"] == second["link"]["id"]
        assert [x["id"] for x in got["removed"]] == [first["id"]]
        assert got["removed"][0]["source"]["id"] == src

        res = c.delete(f"/v1/conversations/{tgt}/carry")
        assert res.status_code == 200, res.text
        removed = res.json()["removed"]
        assert removed["id"] == second["link"]["id"] and removed["removed_at"] is not None
        assert "snapshot" not in removed
        got = c.get(f"/v1/conversations/{tgt}/carry").json()
        assert got["in_force"] is None
        assert [x["id"] for x in got["removed"]] == [second["link"]["id"], first["id"]]

        res = c.delete(f"/v1/conversations/{tgt}/carry")
        assert res.status_code == 404 and res.json()["detail"] == "no link in force"


def test_cors_preflight_allows_the_unlink_delete_from_an_allowed_origin_only(migrated: str) -> None:
    """The panel unlinks a carried chat with a cross-origin DELETE when the sidecar is reached directly."""
    headers = {"Access-Control-Request-Method": "DELETE", "Access-Control-Request-Headers": "authorization"}
    path = f"/v1/conversations/{uuid7()}/carry"
    with make_client(migrated, **ON) as c:
        ok = c.options(path, headers={"Origin": "http://localhost:6101", **headers})
        assert ok.status_code == 200
        assert ok.headers["access-control-allow-origin"] == "http://localhost:6101"
        assert "DELETE" in ok.headers["access-control-allow-methods"]
        denied = c.options(path, headers={"Origin": "http://evil.example", **headers})
        assert "access-control-allow-origin" not in denied.headers


def test_deleting_the_source_chat_deletes_its_links(migrated: str) -> None:
    with make_client(migrated, **ON) as c:
        _, src, tgt = _pair(c, migrated)
        assert c.post(f"/v1/conversations/{tgt}/carry",
                      json={"source_conversation_id": src, "mode": "continue"}).status_code == 200
        res = c.post(f"/v1/conversations/{src}/delete")
        assert res.status_code == 200, res.text
        assert res.json()["deleted"]["carry_links"] >= 1
        assert c.get(f"/v1/conversations/{tgt}/carry").json() == {"in_force": None, "removed": []}


def test_an_api_made_link_round_trips_through_the_archive(
    migrated: str, database_url_factory, tmp_path: Path
) -> None:
    with make_client(migrated, **ON) as c:
        _, src, tgt = _pair(c, migrated)
        made = c.post(f"/v1/conversations/{tgt}/carry",
                      json={"source_conversation_id": src, "mode": "continue"}).json()["link"]
        res = c.get("/v1/archive", params={"conversation": [tgt, src]})
        assert res.status_code == 200, res.text
    path = tmp_path / f"both{archive.SUFFIX}"
    path.write_bytes(res.content)

    fresh = database_url_factory()
    done = archive.restore_file(fresh, str(path))
    assert done.rows["conversation_carry"] == 1
    (orig,) = _rows(migrated)
    (back,) = _rows(fresh)
    assert back["id"] == UUID(made["id"]) == orig["id"]
    assert back["snapshot"] == orig["snapshot"]
    assert back == orig
