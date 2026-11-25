"""Tier 1 (owner-agreed fixes F1–F4, C5): a regression that names the persona, rememberers by knowledge marks, aliases
and owner joins carried, a reading through the source's own link, closed regression threads, the story's leak bar,
carried rows in repairs, joins and the author's note, a secret repair that queues summaries again, and the archive's
list of links it left out.

Pure tests first, then the database. Stub extractor and summarizer only; synthetic names 세라, 카이토, 하나, 유나, 도현,
유찬, 민준, 하루."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from conftest import make_client
from nmos_sidecar import api, archive, carry, summaries
from nmos_sidecar.entities import PERSONA, resolve
from nmos_sidecar.facts import _annotate, memory_view
from nmos_sidecar.threads import fold as fold_threads
from simchat import SimChat
from test_extraction import drain as drain_extract
from test_generations import conv_id
from test_phase60_carry import _connect, _source, _target
from test_phase60_carry_reading import REV_1, SRC_ID, _make_view, _row
from test_phase60_carry_take import ON, _build_source_chat, _fact, _keys, _stub_extract
from test_sidecar_integration import sync

LINK_ID = "01960000-0000-7000-8000-0000000000aa"
TGT_ID = UUID("01960000-0000-7000-8000-000000000009")


def _cast() -> list[dict]:
    """세라, 카이토, 하나, 유나 and the persona 도현, each mentioned once so every name resolves."""
    return [
        _row(100, "세라", "has_status", value="깨어 있음", position=1),
        _row(101, "카이토", "has_status", value="깨어 있음", position=2),
        _row(102, "하나", "has_status", value="깨어 있음", position=3),
        _row(103, "유나", "has_status", value="깨어 있음", position=4),
        _row(104, "도현", "has_status", value="깨어 있음", position=5),
    ]


def _link_row(snapshot: dict[str, Any], mode: str) -> dict[str, Any]:
    return {"id": LINK_ID, "source_conversation_id": str(SRC_ID), "mode": mode,
            "entity_names": snapshot.get("names") or [], "snapshot": snapshot}


# --- F1: the persona regresses -----------------------------------------------------------------------------------

def test_the_persona_alone_regresses_by_any_of_its_spellings() -> None:
    cast = _cast()
    mine = _row(110, "도현", "knows", value="탑의 붕괴 날짜", knowledge="limited", known_by=["도현"], position=6)
    theirs = _row(111, "세라", "has_status", value="저주에 걸림", knowledge="unknown", position=7)
    view = _make_view([mine, theirs], extra_rows=cast)
    for spelling in ("도현", PERSONA, "{{user}}"):
        snap = carry.snapshot_of(view, None, "regression", [spelling], SRC_ID, {})
        assert snap["names"] == [PERSONA], spelling
        assert [f["from"]["assertion"] for f in snap["facts"]] == [110], spelling
        f = snap["facts"][0]
        assert f["subject"] == PERSONA and f["known_by"] == [PERSONA] and f["orig_known_by"] == [PERSONA]
    assert snap["persona_character"] == "도현" and "도현" in snap["characters"]


def test_the_persona_and_a_character_regress_together_and_read_as_the_targets_persona() -> None:
    cast = _cast()
    told = _row(120, "세라", "knows", value="왕의 배신", knowledge="limited", known_by=["세라", "도현"],
                hidden_from=["카이토"], position=6)
    pact = _row(121, "도현", "relationship", obj="세라", object_type="character", value="맹약",
                knowledge="unknown", position=7)
    view = _make_view([told, pact], extra_rows=cast)
    snap = carry.snapshot_of(view, None, "regression", ["도현", "세라"], SRC_ID, {120: REV_1})
    assert snap["names"] == [PERSONA, "세라"]
    by_id = {f["from"]["assertion"]: f for f in snap["facts"]}
    assert by_id[120]["known_by"] == [PERSONA, "세라"] and by_id[120]["hidden_from"] == ["카이토"]
    assert by_id[121]["known_by"] == [PERSONA, "세라"] and by_id[121]["subject"] == PERSONA

    # The target's persona is spelled 민준: the stored marker reads as 민준 in names, rememberers and every name field.
    read = carry.target_rows(_link_row(snap, "regression")).for_persona("민준")
    assert read.names == ("민준", "세라")
    lines = {x["from"]["assertion"]: x for x in read.regression}
    assert lines[120]["known_by"] == ["민준", "세라"]
    assert lines[121]["known_by"] == ["민준", "세라"] and lines[121]["subject"] == "민준"
    target = resolve(TGT_ID, [_row(1, "민준", "has_status", value="깨어 있음")], persona=("민준",))
    assert target.is_persona("character", lines[121]["subject"])


def test_a_persona_regression_preview_marks_the_persona() -> None:
    view = _make_view([_row(110, "도현", "has_status", value="결의", position=6)], extra_rows=_cast())
    snap = carry.snapshot_of(view, None, "continue", [], SRC_ID, {})
    reading = {"source": str(SRC_ID), "mode": "continue", "names": [],
               "cutoff": {"commit": str(SRC_ID), "position": 6, "turn": 1},
               "generations": {}, "snapshot": snap}
    reading["fingerprint"] = carry.fingerprint(reading)
    prev = carry.preview_of(reading, {"character": "세라", "chat": "항구"})
    assert prev["persona_character"] == "도현" and "도현" in prev["characters"]
    # every listed name is one a regression takes as it is
    for name in prev["characters"]:
        carry.snapshot_of(view, None, "regression", [name], SRC_ID, {})


# --- F1: who remembers a row -------------------------------------------------------------------------------------

def test_a_public_world_fact_and_an_items_place_are_remembered_by_every_named() -> None:
    world = _row(130, "왕국", "world_fact", subject_type="place", value="겨울이 길다", knowledge="public", position=6)
    sword = _row(131, "검", "located_in", subject_type="item", obj="탑", object_type="place",
                 knowledge="public", position=7)
    gone = _row(132, "반지", "destroyed", subject_type="item", knowledge="public", position=8)
    rumour = _row(133, "왕국", "world_fact", subject_type="place", value="용이 산다", knowledge="unknown", position=9)
    r = _make_view([], extra_rows=_cast())["resolution"]
    for row in (world, sword, gone):
        assert carry.rememberers(row, ["카이토", "세라"], r) == ["카이토", "세라"]
    # an unmarked row is remembered by the named it involves only: a world fact involves no one
    assert carry.rememberers(rumour, ["카이토", "세라"], r) == []


def test_a_third_partys_public_event_and_secret_follow_their_marks() -> None:
    cast = _cast()
    r = _make_view([], extra_rows=cast)["resolution"]
    public_event = _row(140, "하나", "event", value="왕을 만남", knowledge="public", position=6)
    told_secret = _row(141, "하나", "knows", value="숨은 통로", knowledge="limited", known_by=["하나", "세라"],
                       position=7)
    kept_from = _row(142, "하나", "has_status", value="임신함", knowledge="limited", known_by=["유나"],
                     hidden_from=["세라"], position=8)
    public_but_hidden = _row(143, "하나", "event", value="편지를 받음", knowledge="public", hidden_from=["카이토"],
                             position=9)
    assert carry.rememberers(public_event, ["세라", "카이토"], r) == ["세라", "카이토"]
    assert carry.rememberers(told_secret, ["세라", "카이토"], r) == ["세라"]
    assert carry.rememberers(kept_from, ["세라", "카이토"], r) == []
    assert carry.rememberers(public_but_hidden, ["세라", "카이토"], r) == ["세라"]


def test_a_reading_carries_up_to_max_rows() -> None:
    assert carry.MAX_ROWS == 5000
    err = carry.TooManyRows(5001, carry.MAX_ROWS)
    assert str(err) == "the reading holds 5001 rows; a link carries at most 5000"


# --- F3: aliases, owner joins and nicknames ----------------------------------------------------------------------

@pytest.mark.parametrize("nickname", [
    _row(150, "하루", "also_called", value="도현", position=6),  # the story calls the persona 하루: alias side
    _row(151, "도현", "also_called", value="하루", position=6),  # name side
])
def test_a_persona_nickname_stays_attached_on_either_side_of_an_alias(nickname: dict) -> None:
    """Before Tier 1 the name side was mapped by entity, so `하루 also_called 도현` was stored as {{user}} -> 도현 and
    the nickname 하루 was lost; now a side is the marker only when it spells the persona itself."""
    view = _make_view([], extra_rows=[*_cast(), dict(nickname)])
    snap = carry.snapshot_of(view, None, "continue", [], SRC_ID, {})
    pairs = {frozenset((a["name"], a["alias"])) for a in snap["aliases"]}
    assert pairs == {frozenset(("하루", PERSONA))}

    # Read in a target whose persona is 민준: the nickname joins 민준, the persona.
    read = carry.target_rows(_link_row(snap, "continue")).for_persona("민준")
    target = resolve(TGT_ID, [_row(1, "민준", "has_status", value="깨어 있음"), *read.rows], persona=("민준",))
    assert target.is_persona("character", "하루")


def test_an_alias_whose_two_sides_both_spell_the_persona_is_left_out() -> None:
    view = _make_view([], extra_rows=[*_cast(), _row(152, "한 도현", "also_called", value="도현", position=6),
                                      _row(153, "세라", "also_called", value="세라 언니", position=7)])
    snap = carry.snapshot_of(view, None, "continue", [], SRC_ID, {})
    assert [(a["name"], a["alias"]) for a in snap["aliases"]] == [("세라", "세라 언니")]


def test_an_owner_join_in_the_source_is_carried_as_an_alias_with_its_link() -> None:
    rows = [*_cast(), _row(160, "검은 기사", "has_status", value="침묵", position=6)]
    join = {"id": "01960000-0000-7000-8000-0000000000c1", "entity_type": "character", "name": "검은 기사",
            "same_as": "카이토", "created_at": None}
    r = resolve(SRC_ID, rows, persona=("도현",), links=[join])
    assert r.entity("character", "검은 기사")["id"] == r.entity("character", "카이토")["id"]
    for row in rows:
        _annotate(row, r)
    view = {"facts": rows, "threads": [], "assertions": rows, "resolution": r, "entities": r.entities(),
            "excluded": {}, "secrets": []}
    snap = carry.snapshot_of(view, None, "continue", [], SRC_ID, {})
    linked = [a for a in snap["aliases"] if a["from"].get("link") == join["id"]]
    assert [(a["name"], a["alias"]) for a in linked] == [("검은 기사", "카이토")]
    assert linked[0]["from"]["assertion"] is None

    # the target keeps them one entity without any join of its own
    read = carry.target_rows(_link_row(snap, "continue"))
    target = resolve(TGT_ID, list(read.rows), persona=("유찬",))
    assert target.entity("character", "검은 기사")["id"] == target.entity("character", "카이토")["id"]


def test_a_regression_keeps_the_named_characters_other_spellings_only() -> None:
    sera = _row(170, "세라", "also_called", value="세라 언니", position=6)
    kaito = _row(171, "카이토", "also_called", value="검은 기사", position=7)
    view = _make_view([_row(172, "세라", "has_status", value="결의", position=8)], extra_rows=[*_cast(), sera, kaito])
    snap = carry.snapshot_of(view, None, "regression", ["세라"], SRC_ID, {170: REV_1})
    assert [(a["name"], a["alias"]) for a in snap["aliases"]] == [("세라", "세라 언니")]
    assert snap["aliases"][0]["from"]["revision"] == str(REV_1)
    # a regression link still folds nothing into the target's resolution
    assert carry.target_rows(_link_row(snap, "regression")).rows == ()


def test_a_row_carried_into_the_source_keeps_its_first_chats_provenance() -> None:
    first = {"conversation": "01960000-0000-7000-8000-0000000000f1", "assertion": 7, "revision": str(REV_1),
             "generation": "extract:gen-0", "repair": None, "turn": 3}
    carried_fact = _row(-5, "하나", "located_in", obj="항구", object_type="place", position=-500_000,
                        carried=LINK_ID, carried_from=first)
    own = _row(180, "세라", "has_status", value="결의", position=6)
    view = _make_view([carried_fact, own], extra_rows=_cast())
    snap = carry.snapshot_of(view, None, "continue", [], SRC_ID, {180: REV_1})
    by_subject = {f["subject"]: f for f in snap["facts"]}
    assert by_subject["하나"]["from"] == first
    assert by_subject["세라"]["from"]["conversation"] == str(SRC_ID)
    assert "carried" not in by_subject["하나"] and "carried_from" not in by_subject["하나"]


# --- F1: closed regression threads -------------------------------------------------------------------------------

def _regression_thread_lines() -> list[dict[str, Any]]:
    cast = _cast()
    kept = _row(190, "세라", "promised", obj="카이토", object_type="character", value="등대 열쇠를 찾아주기",
                position=6)
    broken = _row(191, "하나", "promised", obj="유나", object_type="character", value="항구에서 기다리기",
                  position=7)
    fulfilled = _row(192, "세라", "fulfilled", obj="카이토", object_type="character", value="등대 열쇠를 찾아주기",
                     position=8, turn=2)
    rows = [*cast, kept, broken, fulfilled]
    r = resolve(SRC_ID, rows, persona=("도현",))
    for row in rows:
        _annotate(row, r)
    threads, _, _ = fold_threads([kept, broken, fulfilled], r)
    return threads


def test_regression_threads_ranks_a_closed_thread_the_message_brings_up() -> None:
    threads = _regression_thread_lines()
    status = {t["by"]: t["status"] for t in threads}
    assert status["세라"] != "open" and status["하나"] == "open"
    picked = carry.regression_threads(threads, "카이토는 어디 있지?", "", set(), 5)
    assert [t["by"] for t in picked] == ["세라"]
    assert picked[0] is next(t for t in threads if t["by"] == "세라") and picked[0]["status"] != "open"
    # the user's message before the previous reply, newest first within each
    both = carry.regression_threads(threads, "유나에게", "카이토가 말했다", set(), 5)
    assert [t["by"] for t in both] == ["하나", "세라"]
    assert carry.regression_threads(threads, "아무 말", "", set(), 5) == []
    # a thread whose opening message is still in the prompt is left out, as relevant_threads leaves it out
    in_prompt = {t["host_logical_id"] for t in threads if t["by"] == "세라"}
    assert carry.regression_threads(threads, "카이토", "", in_prompt, 5) == []
    # the words of a promise bring it with `about`
    assert [t["by"] for t in carry.regression_threads(threads, "등대 열쇠를 찾아주기", "", set(), 5, about=True)] \
        == ["세라"]
    assert all(t["status"] == s for t, s in zip(threads, [t["status"] for t in _regression_thread_lines()]))


# --- the database ------------------------------------------------------------------------------------------------

ARC_1 = "미나는 북쪽 숲의 오두막에 산다. 미나는 하나에게 은빛 열쇠를 돌려주겠다고 약속했다."


def _stub_arcs(system: str, user: str) -> tuple[dict, str, dict]:
    ans, raw, used = _stub_extract(system, user)
    if ARC_1 in user.split("TARGET turn", 1)[-1]:
        ans = {"assertions": [
            *(ans.get("assertions") or []),
            _fact("미나", "located_in", None, "북쪽 숲의 오두막", "place", evidence="북쪽 숲의 오두막에 산다"),
            _fact("미나", "promised", "은빛 열쇠를 돌려주기", "하나", "character", evidence="돌려주겠다고 약속했다"),
        ]}
    return ans, raw, used


def _chain(c, migrated: str) -> tuple[UUID, UUID]:
    """A (arc 1): 미나 in the northern forest, a promise to 하나. B (arc 2): the source chat at the lighthouse, which
    never names 미나."""
    a_sim = SimChat("arc-1")
    a_sim.user("시작.")
    a_sim.reply(ARC_1)
    a_sim.user("다음.")
    sync(c, a_sim, character_name="미나", persona_name="도현")
    b_sim = _build_source_chat(4)
    sync(c, b_sim, character_name="세라", chat_name="항구의 밤", persona_name="도현")
    drain_extract(migrated, _stub_arcs)
    return UUID(conv_id(c, a_sim)), UUID(conv_id(c, b_sim))


def test_a_reading_of_a_chat_that_continues_another_carries_both_arcs(migrated: str) -> None:
    """Changed in Tier 1 (F3, owner-agreed): test_phase60_carry's `test_a_reading_never_follows_the_sources_own_link`
    pinned the opposite. Arc 3 now keeps arc 1's still-current facts and open threads, read from arc 2's frozen
    link (never from arc 1 again), each with arc 1's provenance."""
    with make_client(migrated, **ON) as c:
        a, b = _chain(c, migrated)
        target = _target(c, "arc-3")
        with _connect(migrated) as conn:
            keys = _keys(conn, with_summary=False)
            carry.link(conn, b, a, "continue", [], keys)
            snap = carry.by_id(conn, carry.link(conn, target, b, "continue", [], keys)["link"]["id"])["snapshot"]
            origin = {(f["subject"], f["predicate"]): f["from"]["conversation"] for f in snap["facts"]}
            assert origin[("미나", "located_in")] == str(a) and origin[("세라", "located_in")] == str(b)
            assert all(f["from"]["assertion"] is not None for f in snap["facts"])
            # arc 1's open promise comes along as an open thread, with arc 1's provenance
            promise = next(t for t in snap["threads"] if t["by"] == "미나")
            assert promise["status"] == "open" and promise["from"]["conversation"] == str(a)
            assert promise["opening"] is not None
            # arc 3 reads it as arc 2 did
            view = memory_view(conn, conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s",
                                                  (target,)).fetchone()["head_commit_id"], keys.extractor,
                               carried=carry.target_rows(carry.in_force(conn, target)))
            assert any(f.get("carried") and f["subject"] == "미나" for f in view["facts"])
            assert any(t.get("carried") and t["by"] == "미나" and t["status"] == "open" for t in view["threads"])


def test_a_reading_never_brings_the_targets_own_memory_back(migrated: str) -> None:
    with make_client(migrated, **ON) as c:
        a, b = _chain(c, migrated)
        with _connect(migrated) as conn:
            keys = _keys(conn, with_summary=False)
            carry.link(conn, b, a, "continue", [], keys)  # B continues A
            snap = carry.by_id(conn, carry.link(conn, a, b, "continue", [], keys)["link"]["id"])["snapshot"]
            assert snap["facts"] and all(f["from"]["conversation"] == str(b) for f in snap["facts"])


def test_a_regression_source_link_is_not_followed(migrated: str) -> None:
    with make_client(migrated, **ON) as c:
        a, b = _chain(c, migrated)
        target = _target(c, "arc-3")
        with _connect(migrated) as conn:
            keys = _keys(conn, with_summary=False)
            carry.link(conn, b, a, "regression", ["하나"], keys)
            snap = carry.by_id(conn, carry.link(conn, target, b, "continue", [], keys)["link"]["id"])["snapshot"]
            assert snap["facts"] and all(f["from"]["conversation"] == str(b) for f in snap["facts"])


def test_the_story_is_read_with_every_open_secrets_keepers_present(migrated: str, monkeypatch) -> None:
    seen: list[frozenset[str]] = []
    real = summaries.current

    def spy(*args: Any, **kwargs: Any) -> dict[str, Any]:
        seen.append(kwargs.get("present", frozenset()))
        return real(*args, **kwargs)

    monkeypatch.setattr(carry.summaries, "current", spy)
    with make_client(migrated, **ON) as c:
        sim = _build_source_chat(4, with_secret=True)
        sync(c, sim, character_name="세라", chat_name="항구의 밤", persona_name="도현")
        drain_extract(migrated, _stub_extract)
        src, tgt = UUID(conv_id(c, sim)), _target(c)
        with _connect(migrated) as conn:
            carry.preview(conn, tgt, src, "continue", [], _keys(conn))
    assert seen and seen[-1] == frozenset({"카이토"})


def _continue_pair(c, migrated: str) -> tuple[UUID, UUID]:
    _, src = _source(c, migrated)
    tgt = _target(c)
    res = c.post(f"/v1/conversations/{tgt}/carry", json={"source_conversation_id": str(src), "mode": "continue"})
    assert res.status_code == 200, res.text
    return src, tgt


def _carried_fact(c, tgt: UUID, subject: str, predicate: str) -> dict[str, Any]:
    return next(f for f in c.get(f"/v1/conversations/{tgt}/facts").json()
                if f.get("carried") and f["subject"] == subject and f["predicate"] == predicate)


def test_a_character_only_the_carried_rows_name_is_pinned_and_left_out(migrated: str) -> None:
    """Before Tier 1 a repair was planned against the chat's own memory, so a character only a `continue` link
    brings (하나) was not one of the chat's: a pin or an exclusion of it answered 422."""
    with make_client(migrated, **ON) as c:
        _, tgt = _continue_pair(c, migrated)
        assert _carried_fact(c, tgt, "하나", "located_in")
        pin = c.post(f"/v1/conversations/{tgt}/repairs", json={"kind": "entity_pin", "item": "하나"})
        assert pin.status_code == 200, pin.text
        assert pin.json()["applied"] is not None
        listed = {r["id"]: r for r in c.get(f"/v1/conversations/{tgt}/repairs").json()["repairs"]}
        assert listed[pin.json()["repair"]["id"]]["applied"] is not None
        body = {"kind": "entity_exclude", "entity_type": "character", "item": "하나", "scope": "memory"}
        prev = c.post(f"/v1/conversations/{tgt}/repairs/preview", json=body)
        assert prev.status_code == 200, prev.text
        assert prev.json()["scopes"]["memory"]["facts"] > 0
        out = c.post(f"/v1/conversations/{tgt}/repairs", json={**body, "expect": prev.json()["fingerprint"]})
        assert out.status_code == 200, out.text
        assert not any(f.get("carried") and f["subject"] == "하나"
                       for f in c.get(f"/v1/conversations/{tgt}/facts").json())


def test_a_carried_name_is_joined_and_its_preview_lists_no_carried_row_as_a_change(migrated: str) -> None:
    with make_client(migrated, **ON) as c:
        _, tgt = _continue_pair(c, migrated)
        body = {"entity_type": "character", "name": "하나", "same_as": "유나"}  # both only in the carried rows
        prev = c.post(f"/v1/conversations/{tgt}/entity-links/preview", json=body)
        assert prev.status_code == 200, prev.text
        changed = [line for line in prev.json()["lines"] if line.get("change") not in (None, "same")]
        assert all(line.get("subject") in ("하나", "유나", None) for line in changed), changed
        res = c.post(f"/v1/conversations/{tgt}/entity-links", json={**body, "expect": prev.json()["fingerprint"]})
        assert res.status_code == 200, res.text
        assert res.json()["entity"] is not None
        # taking the join back is previewed and made with the link in force too
        join_id = res.json()["link"]["id"]
        undo = c.post(f"/v1/conversations/{tgt}/entity-links/{join_id}/remove/preview")
        assert undo.status_code == 200, undo.text
        gone = c.post(f"/v1/conversations/{tgt}/entity-links/{join_id}/remove",
                      json={"expect": undo.json()["fingerprint"]})
        assert gone.status_code == 200, gone.text


def test_the_authors_note_and_repairs_read_the_link(migrated: str, monkeypatch) -> None:
    carried: list[bool] = []
    real = api.memory_view

    def spy(*args: Any, **kwargs: Any) -> dict[str, Any]:
        carried.append(kwargs.get("carried") is not None)
        return real(*args, **kwargs)

    monkeypatch.setattr(api, "memory_view", spy)
    with make_client(migrated, **ON) as c:
        _, tgt = _continue_pair(c, migrated)
        for method, url, body in (
            ("post", f"/v1/conversations/{tgt}/notes", {"sections": ["changed", "address"], "model": False}),
            ("get", f"/v1/conversations/{tgt}/repairs", None),
            ("post", f"/v1/conversations/{tgt}/repairs/preview",
             {"kind": "entity_exclude", "entity_type": "character", "item": "하나"}),
        ):
            carried.clear()
            res = getattr(c, method)(url, **({"json": body} if body is not None else {}))
            assert res.status_code == 200, (url, res.text)
            assert carried and all(carried), url


def test_a_secret_repair_queues_the_summaries_again_when_made_and_taken_back(migrated: str, monkeypatch) -> None:
    queued: list[UUID] = []
    real = summaries.schedule_stale

    def spy(conn: Any, conv: UUID, key: str, *args: Any, **kwargs: Any) -> int:
        queued.append(conv)
        return real(conn, conv, key, *args, **kwargs)

    monkeypatch.setattr(api.summaries, "schedule_stale", spy)
    with make_client(migrated, **ON) as c:
        sim = _build_source_chat(4, with_secret=True)
        sync(c, sim, character_name="세라", chat_name="항구의 밤", persona_name="도현")
        drain_extract(migrated, _stub_extract)
        conv = UUID(conv_id(c, sim))
        secret = c.get(f"/v1/conversations/{conv}/secrets").json()[0]
        queued.clear()
        res = c.post(f"/v1/conversations/{conv}/repairs",
                     json={"kind": "secret_found_out", "item": str(secret["id"]), "character": "카이토"})
        assert res.status_code == 200, res.text
        assert queued == [conv]
        assert c.post(f"/v1/conversations/{conv}/repairs/{res.json()['repair']['id']}/remove").status_code == 200
        assert queued == [conv, conv]
        # another kind queues nothing
        tired = next(f for f in c.get(f"/v1/conversations/{conv}/facts").json() if f["predicate"] == "has_status")
        assert c.post(f"/v1/conversations/{conv}/repairs",
                      json={"kind": "fact_retract", "item": str(tired["id"])}).status_code == 200
        assert queued == [conv, conv]


def _manifest(data: bytes) -> dict[str, Any]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return json.loads(zf.read("manifest.json"))


def test_a_single_chat_export_names_the_links_it_left_out_by_id(migrated: str, tmp_path: Path) -> None:
    with make_client(migrated, **ON) as c:
        src, tgt = _continue_pair(c, migrated)
        with _connect(migrated) as conn:
            link_id = str(carry.in_force(conn, tgt, snapshot=False)["id"])
    for only, missing, other in ((tgt, "source", src), (src, "target", tgt)):
        out = tmp_path / f"{only}.zip"
        archive.export_file(migrated, str(out), conversations=[only])
        m = _manifest(out.read_bytes())
        assert m["carry_left_out"] == 1
        assert m["carry_left_out_details"] == [{"link": link_id, "target": str(tgt), "source": str(src),
                                                "mode": "continue", "in_force": True, "missing": missing}]
        assert m["carry_left_out_conversations"] == [str(other)]
        # no name of the chat that was not exported
        assert "항구의 밤" not in json.dumps(m, ensure_ascii=False) or only == src
    whole = tmp_path / "both.zip"
    archive.export_file(migrated, str(whole), conversations=[src, tgt])
    m = _manifest(whole.read_bytes())
    assert m["carry_left_out"] == 0 and m["carry_left_out_details"] == [] and m["carry_left_out_conversations"] == []


def test_an_unlinked_chats_export_has_empty_details(migrated: str, tmp_path: Path) -> None:
    with make_client(migrated, **ON) as c:
        _, src = _source(c, migrated)
    out = tmp_path / "one.zip"
    archive.export_file(migrated, str(out), conversations=[src])
    m = _manifest(out.read_bytes())
    assert m["carry_left_out"] == 0 and m["carry_left_out_details"] == [] and m["carry_left_out_conversations"] == []

