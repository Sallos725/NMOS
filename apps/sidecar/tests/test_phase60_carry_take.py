"""PHASE-60 S6 (ADR 0085): DB reading for carry (`cutoff_of`, `take_reading`, `preview`).

Stub extractor, summarizer and canon extractor only; synthetic names 세라, 카이토, 하나, 유나, 도현."""

from __future__ import annotations

from uuid import UUID

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import active_generation, alias_yes, make_client
from nmos_sidecar import canonfacts, carry, summaries
from nmos_sidecar.entities import PERSONA
from nmos_sidecar.extraction import ALIAS_CONFIRM_SYSTEM
from nmos_sidecar.facts import fact_text, memory_view
from nmos_sidecar.ids import uuid7
from nmos_sidecar.worker import run_once
from simchat import SimChat
from test_canon import push as push_canon
from test_extraction import drain as drain_extract
from test_generations import LLM, conv_id
from test_sidecar_integration import sync
from test_summaries import drain as drain_summaries

USED = {"calls": 1, "input": 100, "output": 10}
ON = {**LLM, "summaries": True, "extract_backfill": 100}
CANON_ON = {**LLM, "summaries": False, "canon_facts": True, "extract_backfill": 100}

TURN_0 = "세라는 등대에 있고 피곤한 상태다. 세라는 카이토의 오랜 동료이며, 도현과 함께 서 있다."
TURN_1 = "세라는 카이토에게 내일 새벽 등대 열쇠를 찾아주겠다고 약속했다. 사람들은 세라를 등대지기라고도 부른다."
TURN_2 = "하나는 유나와 항구 시장으로 이동했다. 하나는 상처가 나은 상태다."
SECRET_TEXT = "붉은 벽돌 아래 지하 창고 열쇠가 숨겨져 있다"
TURN_SECRET = f"세라는 카이토 모르게 {SECRET_TEXT}는 사실을 알고 있다."


def _fact(subject: str, predicate: str, value: str | None = None,
          obj: str | None = None, obj_type: str | None = None, **kw) -> dict:
    return {
        "subject": subject, "subject_type": "character", "predicate": predicate,
        "object": obj, "object_type": obj_type, "value": value,
        "polarity": "positive", "modality": "actual", "source": "narration",
        "evidence": "", **kw,
    }


def _stub_extract(system: str, user: str) -> tuple[dict, str, dict]:
    if system == ALIAS_CONFIRM_SYSTEM:
        ans, raw = alias_yes(user)
        return ans, raw, USED
    target = user.split("TARGET turn", 1)[-1]
    rows: list[dict] = []
    if TURN_0 in target:
        rows += [
            _fact("세라", "located_in", None, "등대", "place", evidence="세라는 등대에 있고"),
            _fact("세라", "has_status", "피곤함", evidence="피곤한 상태다"),
            _fact("세라", "relationship", "오랜 동료", "카이토", "character", evidence="카이토의 오랜 동료"),
            _fact("도현", "located_in", None, "등대", "place", evidence="도현과 함께 서 있다"),
        ]
    if TURN_1 in target:
        rows += [
            _fact("세라", "promised", "내일 새벽 등대 열쇠를 찾아주기", "카이토", "character",
                  evidence="등대 열쇠를 찾아주겠다고 약속했다"),
            _fact("세라", "also_called", "등대지기", evidence="세라를 등대지기라고도 부른다"),
        ]
    if TURN_2 in target:
        rows += [
            _fact("하나", "located_in", None, "항구 시장", "place", evidence="항구 시장으로 이동했다"),
            _fact("하나", "has_status", "회복됨", evidence="상처가 나은 상태다"),
            _fact("하나", "relationship", "친구", "유나", "character", evidence="유나와 항구 시장으로"),
        ]
    if TURN_SECRET in target:
        rows.append(
            _fact("세라", "knows", SECRET_TEXT, knowledge="limited",
                  known_by=["세라"], hidden_from=["카이토"], evidence=SECRET_TEXT)
        )
    return {"assertions": rows}, "{}", USED


def _stub_summary(system: str, user: str) -> tuple[dict, str]:
    if system == summaries.STORY_PROMPT:
        return {"summary": "세라와 카이토는 등대에서 열쇠를 찾기로 약속하고 항구로 향했다."}, "{}"
    return {"summary": "등대와 항구에서 일행이 만났다."}, "{}"


def _leaky_summary(system: str, user: str) -> tuple[dict, str]:
    if system == summaries.STORY_PROMPT:
        return {"summary": f"세라의 비밀은 {SECRET_TEXT}는 것이다."}, "{}"
    return {"summary": "등대에서 세라가 무언가를 숨겼다."}, "{}"


def _build_source_chat(turns: int = 13, *, with_secret: bool = False) -> SimChat:
    sim = SimChat("src-chat")
    scripted = [TURN_0, TURN_1, TURN_2]
    if with_secret:
        scripted.append(TURN_SECRET)
    for i in range(turns):
        sim.user(f"턴 {i}의 대화 시작.")
        sim.reply(scripted[i] if i < len(scripted) else f"턴 {i}의 평온한 밤이 지나갔다.")
    sim.user("다음으로 이어가자.")
    return sim


def _keys(conn: psycopg.Connection, *, with_summary: bool = True, with_canon: bool = False) -> carry.Keys:
    return carry.Keys(
        extractor=active_generation(conn, "extract").key,
        summarize=active_generation(conn, "summarize").key if with_summary else None,
        canon=active_generation(conn, "canon").key if with_canon else None,
    )


def test_take_reading_and_preview_with_provenance_and_story(migrated: str) -> None:
    with make_client(migrated, **ON) as c:
        src_sim = _build_source_chat(13)
        sync(c, src_sim, character_name="세라", chat_name="항구의 밤", persona_name="도현")
        drain_extract(migrated, _stub_extract)
        drain_summaries(migrated, _stub_summary)
        src_id = UUID(conv_id(c, src_sim))

        tgt_sim = SimChat("tgt-chat")
        tgt_sim.user("새 이야기를 시작한다.")
        tgt_sim.reply("아침 햇살이 비춘다.")
        sync(c, tgt_sim, character_name="세라", chat_name="새 이야기", persona_name="유찬")
        tgt_id = UUID(conv_id(c, tgt_sim))

        with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
            keys = _keys(conn, with_summary=True)
            reading = carry.take_reading(conn, src_id, "continue", [], keys)

            assert reading["source"] == str(src_id)
            assert reading["mode"] == "continue"
            assert reading["names"] == []
            assert reading["cutoff"]["turn"] == 13
            assert len(reading["fingerprint"]) == 64

            snap = reading["snapshot"]
            assert snap["shape"] == carry.SHAPE
            preds = {(f["subject"], f["predicate"], f.get("object"), f.get("value")) for f in snap["facts"]}
            assert ("세라", "located_in", "등대", None) in preds
            assert ("세라", "has_status", None, "피곤함") in preds
            assert ("세라", "relationship", "카이토", "오랜 동료") in preds
            # Persona ("도현") was mapped to {{user}}.
            assert (PERSONA, "located_in", "등대", None) in preds
            assert not any(f["subject"] == "도현" for f in snap["facts"])

            # Alias carried.
            assert any(a["name"] == "세라" and a["alias"] == "등대지기" for a in snap["aliases"])

            # Open promise carried.
            assert len(snap["threads"]) == 1
            t = snap["threads"][0]
            assert t["kind"] == "promise" and t["by"] == "세라" and t["to"] == "카이토" and t["status"] == "open"
            assert t["closed_turn"] is None

            # Story so far carried with provenance.
            assert snap["story"] is not None
            assert "등대에서 열쇠를" in snap["story"]["text"]
            assert snap["story"]["from"]["conversation"] == str(src_id)
            assert snap["story"]["from"]["generation"] == keys.summarize
            assert snap["story_left_out"] is None

            # Provenance: every stored row's from.revision equals assertion.source_revision_id in DB.
            revs = {
                r["id"]: str(r["source_revision_id"])
                for r in conn.execute("SELECT id, source_revision_id FROM assertion").fetchall()
            }
            for row in (*snap["facts"], *snap["aliases"], *snap["threads"]):
                aid = row["from"]["assertion"]
                assert aid is not None and aid > 0
                assert row["from"]["revision"] == revs[aid]
                assert row["from"]["generation"] == keys.extractor
                assert row["from"]["conversation"] == str(src_id)

            assert keys.extractor in reading["generations"]["served"]
            assert keys.summarize in reading["generations"]["served"]
            assert "세라" in snap["characters"] and "도현" not in snap["characters"]

            # Preview writes nothing and summarizes counts, first_lines and source labels.
            prev = carry.preview(conn, tgt_id, src_id, "continue", [], keys)
            assert prev["mode"] == "continue"
            assert prev["source"] == {"id": str(src_id), "character": "세라", "chat": "항구의 밤"}
            assert prev["counts"] == {
                "facts": len(snap["facts"]),
                "aliases": len(snap["aliases"]),
                "threads": 1,
                "story": True,
            }
            expected_lines = ([fact_text(f) for f in snap["facts"]] + [t["text"]])[:carry.FIRST_LINES]
            assert prev["first_lines"] == expected_lines
            assert prev["fingerprint"] == reading["fingerprint"]
            assert prev["replaces"] is None
            assert conn.execute("SELECT count(*) AS n FROM conversation_carry").fetchone()["n"] == 0


def test_cutoff_turn_reads_only_up_to_that_turn_and_rejects_missing_turn(migrated: str) -> None:
    with make_client(migrated, **ON) as c:
        src_sim = _build_source_chat(4)
        sync(c, src_sim, character_name="세라", persona_name="도현")
        drain_extract(migrated, _stub_extract)
        src_id = UUID(conv_id(c, src_sim))

        with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
            keys = _keys(conn, with_summary=False)
            full = carry.take_reading(conn, src_id, "continue", [], keys)
            cut0 = carry.take_reading(conn, src_id, "continue", [], keys, cutoff_turn=0)

            assert cut0["cutoff"]["turn"] == 0
            assert cut0["cutoff"]["position"] < full["cutoff"]["position"]
            # Turn 0 has 세라's facts, but NOT turn 1's promise or turn 2's 하나 facts.
            assert any(f["subject"] == "세라" for f in cut0["snapshot"]["facts"])
            assert not any(f["subject"] == "하나" for f in cut0["snapshot"]["facts"])
            assert cut0["snapshot"]["threads"] == []
            assert cut0["fingerprint"] != full["fingerprint"]

            # Turn not on head -> CarryError.
            with pytest.raises(carry.CarryError, match="99"):
                carry.cutoff_of(conn, src_id, 99)

            # Unknown chat -> NoSuchChat.
            with pytest.raises(carry.NoSuchChat):
                carry.cutoff_of(conn, uuid7(), None)

            # Empty conversation without head_commit_id -> CarryError.
            empty_id = uuid7()
            conn.execute(
                "INSERT INTO conversation (id, host, host_chat_ref) VALUES (%s, 'pocketrisu', 'empty-chat')",
                (empty_id,),
            )
            with pytest.raises(carry.CarryError, match="no messages"):
                carry.cutoff_of(conn, empty_id, None)


def test_validation_guards_unknown_name_continue_with_names_self_carry_and_max_rows(
    migrated: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(migrated, **ON) as c:
        src_sim = _build_source_chat(4)
        sync(c, src_sim, character_name="세라", persona_name="도현")
        drain_extract(migrated, _stub_extract)
        src_id = UUID(conv_id(c, src_sim))

        with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
            keys = _keys(conn, with_summary=False)

            with pytest.raises(carry.CarryError, match="없는사람 is no character of the source"):
                carry.take_reading(conn, src_id, "regression", ["없는사람"], keys)

            with pytest.raises(carry.CarryError):
                carry.take_reading(conn, src_id, "continue", ["세라"], keys)

            with pytest.raises(carry.CarryError, match="never carries itself"):
                carry.preview(conn, src_id, src_id, "continue", [], keys)

            with pytest.raises(carry.NoSuchChat):
                carry.preview(conn, uuid7(), src_id, "continue", [], keys)

            # MAX_ROWS enforcement.
            monkeypatch.setattr(carry, "MAX_ROWS", 2)
            with pytest.raises(carry.CarryError, match="at most 2"):
                carry.take_reading(conn, src_id, "continue", [], keys)


def test_source_canon_fact_is_not_carried(migrated: str) -> None:
    def stub_model(system: str, user: str) -> tuple[dict, str, dict]:
        if "CANON" in system:
            return {"assertions": [
                _fact("세라", "identity", "북부 등대지기", evidence="세라는 북부 등대지기다"),
            ]}, "{}", USED
        return _stub_extract(system, user)

    with make_client(migrated, **CANON_ON) as c:
        src_sim = _build_source_chat(4)
        sync(c, src_sim, character_name="세라", persona_name="도현")
        push_canon(c, src_sim, {
            "card:name": ("세라", {"field": "name"}),
            "card:desc": ("{{char}}는 북부 등대지기다.", {"field": "desc"}),
        })
        drain_extract(migrated, stub_model)
        with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
            cg = active_generation(conn, "canon")
            while run_once(conn, {"canon": (cg.key, lambda cn, job: canonfacts.process(cn, job, stub_model, cg))}):
                pass
            src_id = UUID(conv_id(c, src_sim))
            head = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (src_id,)).fetchone()["head_commit_id"]
            keys = _keys(conn, with_summary=False, with_canon=True)

            # Confirm the source's own memory_view DOES contain the canon fact.
            src_view = memory_view(conn, head, keys.extractor, canon_key=keys.canon)
            assert any(f.get("canon") and f["predicate"] == "identity" for f in src_view["facts"])

            # Frozen reading drops canon rows while keeping story facts.
            reading = carry.take_reading(conn, src_id, "continue", [], keys)
            assert not any(f["predicate"] == "identity" and f.get("value") == "북부 등대지기"
                           for f in reading["snapshot"]["facts"])
            assert any(f["predicate"] == "has_status" and f.get("value") == "피곤함"
                       for f in reading["snapshot"]["facts"])


def test_story_repeating_a_kept_secret_is_left_out_with_reason(migrated: str) -> None:
    with make_client(migrated, **ON) as c:
        src_sim = _build_source_chat(13, with_secret=True)
        sync(c, src_sim, character_name="세라", persona_name="도현")
        drain_extract(migrated, _stub_extract)
        drain_summaries(migrated, _leaky_summary)
        src_id = UUID(conv_id(c, src_sim))

        with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
            keys = _keys(conn, with_summary=True)
            reading = carry.take_reading(conn, src_id, "continue", [], keys)
            snap = reading["snapshot"]
            assert snap["story"] is None
            assert snap["story_left_out"] == "secret"
            # The secret fact itself is still carried with its knowledge marks intact.
            secret_fact = next(f for f in snap["facts"] if f["predicate"] == "knows")
            assert secret_fact["knowledge"] == "limited"
            assert secret_fact["hidden_from"] == ["카이토"]
