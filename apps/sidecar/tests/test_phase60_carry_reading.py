"""PHASE-60 S6 (ADR 0085): pure reading, persona mapping, regression rememberers, fingerprint and preview.

No database; synthetic names only (세라, 카이토, 하나, 유나, 도현)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from nmos_sidecar import carry
from nmos_sidecar.entities import PERSONA, resolve
from nmos_sidecar.facts import _annotate, fact_text
from nmos_sidecar.threads import fold as fold_threads

SRC_ID = UUID("01960000-0000-7000-8000-000000000001")
COMMIT_ID = UUID("01960000-0000-7000-8000-000000000002")
REV_1 = UUID("01960000-0000-7000-8000-000000000101")
REV_2 = UUID("01960000-0000-7000-8000-000000000102")
REV_3 = UUID("01960000-0000-7000-8000-000000000103")
SUM_ID = UUID("01960000-0000-7000-8000-000000000201")
REP_ID = UUID("01960000-0000-7000-8000-000000000301")


def _row(
    aid: int,
    subject: str,
    predicate: str,
    *,
    subject_type: str = "character",
    obj: str | None = None,
    object_type: str | None = None,
    value: str | None = None,
    turn: int | None = 1,
    position: int = 1,
    knowledge: str | None = "unknown",
    known_by: list[str] | None = None,
    hidden_from: list[str] | None = None,
    source: str = "narration",
    asserted_by: str | None = None,
    modality: str = "actual",
    polarity: str = "positive",
    participants: tuple[dict[str, str], ...] | list[dict[str, str]] | None = None,
    generation: str | None = "extract:gen-1",
    compiler: str | None = "extract-v16",
    **extra,
) -> dict:
    return {
        "id": aid,
        "subject": subject,
        "subject_type": subject_type,
        "predicate": predicate,
        "object": obj,
        "object_type": object_type,
        "value": value,
        "epistemic": "stated",
        "confidence": 0.9,
        "evidence": f"evidence-{aid}",
        "knowledge": knowledge,
        "known_by": known_by,
        "hidden_from": hidden_from,
        "polarity": polarity,
        "modality": modality,
        "source": source,
        "asserted_by": asserted_by,
        "salience": None,
        "participants": participants,
        "outcome": None,
        "because": None,
        "turn": turn,
        "position": position,
        "generation": generation,
        "compiler": compiler,
        "host_logical_id": f"m-{position}",
        "turn_hash": f"th-{turn}",
        **extra,
    }


def _make_view(
    facts: list[dict],
    *,
    extra_rows: list[dict] | None = None,
    threads: list[dict] | None = None,
    persona: tuple[str, ...] = ("도현",),
    canon_names: list[dict] | None = None,
    excluded: dict[str, dict] | None = None,
) -> dict:
    all_rows = list(facts) + list(extra_rows or [])
    r = resolve(SRC_ID, all_rows, persona=persona, canon=canon_names or [])
    for row in all_rows:
        _annotate(row, r)
    excl = excluded or {}
    entities = [
        {**e, "excluded": excl[str(e["id"])]["scope"]} if str(e["id"]) in excl else e
        for e in r.entities()
    ]
    return {
        "facts": sorted(facts, key=lambda f: f["position"], reverse=True),
        "threads": threads if threads is not None else [],
        "assertions": all_rows,
        "resolution": r,
        "entities": entities,
        "excluded": excl,
        "secrets": [],
    }


# --- persona mapping --------------------------------------------------------------------------------------------

def test_persona_mapping_covers_every_name_field_and_full_name_spelling() -> None:
    """Every character name field naming the source's persona — including a full-name spelling — maps to {{user}},
    while non-character names and alias values stay as written."""
    f1 = _row(
        1, "도현", "located_in", obj="항구", object_type="place",
        known_by=["도현", "한 도현", "세라"], hidden_from=["한 도현", "카이토"],
        asserted_by="한 도현",
        participants=({"type": "character", "name": "한 도현"}, {"type": "character", "name": "세라"},
                      {"type": "item", "name": "도현"}),
        turn=1, position=1,
    )
    f2 = _row(2, "세라", "relationship", obj="한 도현", object_type="character", value="동료", turn=2, position=2)
    # Non-character subject with the same string as the persona must NOT be rewritten.
    f3 = _row(3, "도현", "world_fact", subject_type="place", value="오래된 마을", turn=3, position=3)
    alias_assert = _row(4, "한 도현", "also_called", value="도현이", turn=1, position=1)
    place_alias = _row(5, "도현", "also_called", subject_type="place", value="옛 도현", turn=2, position=2)
    promise = _row(6, "한 도현", "promised", obj="세라", object_type="character", value="항구에서 만나기",
                   knowledge="limited", known_by=["한 도현", "세라"], hidden_from=["카이토"], turn=2, position=4)
    promise_to_persona = _row(7, "세라", "promised", obj="도현", object_type="character", value="열쇠를 돌려주기",
                              turn=3, position=5)

    all_rows = [f1, f2, f3, alias_assert, place_alias, promise, promise_to_persona]
    r = resolve(SRC_ID, all_rows, persona=("도현",))
    for row in all_rows:
        _annotate(row, r)
    threads, _, _ = fold_threads([promise, promise_to_persona], r)
    view = {
        "facts": [f3, f2, f1],
        "threads": threads,
        "assertions": all_rows,
        "resolution": r,
        "entities": r.entities(),
        "excluded": {},
    }

    snap = carry.snapshot_of(view, None, "continue", [], SRC_ID, {1: REV_1, 2: REV_2, 4: REV_1, 6: REV_3})
    by_id = {f["from"]["assertion"]: f for f in snap["facts"]}

    assert by_id[1]["subject"] == PERSONA
    assert by_id[1]["object"] == "항구"
    assert by_id[1]["known_by"] == [PERSONA, "세라"]
    assert by_id[1]["hidden_from"] == [PERSONA, "카이토"]
    assert by_id[1]["asserted_by"] == PERSONA
    assert by_id[1]["participants"] == [
        {"type": "character", "name": PERSONA},
        {"type": "character", "name": "세라"},
        {"type": "item", "name": "도현"},
    ]
    assert by_id[2]["subject"] == "세라" and by_id[2]["object"] == PERSONA
    assert by_id[3]["subject"] == "도현"  # place, not character

    # Aliases: persona's `name` maps to {{user}}, `alias` stays; place alias `name` stays.
    aliases_by_id = {a["from"]["assertion"]: a for a in snap["aliases"]}
    assert aliases_by_id[4]["name"] == PERSONA and aliases_by_id[4]["alias"] == "도현이"
    assert aliases_by_id[5]["name"] == "도현" and aliases_by_id[5]["alias"] == "옛 도현"

    # Threads: by, to and names map persona to {{user}}.
    threads_by_id = {t["from"]["assertion"]: t for t in snap["threads"]}
    assert threads_by_id[6]["by"] == PERSONA
    assert threads_by_id[6]["to"] == "세라"
    assert PERSONA in threads_by_id[6]["names"] and "도현" not in threads_by_id[6]["names"]
    assert "한 도현" not in threads_by_id[6]["names"]
    assert threads_by_id[6]["known_by"] == [PERSONA, "세라"]
    assert threads_by_id[7]["by"] == "세라" and threads_by_id[7]["to"] == PERSONA


# --- canon, owner repairs, row keys, threads, story -------------------------------------------------------------

def test_canon_rows_and_canon_aliases_are_left_out_and_fact_keys_stripped() -> None:
    story_fact = _row(
        10, "세라", "has_status", value="피곤함", turn=2, position=4,
        history=[{"turn": 1, "value": "건강함"}], versions=2, claims=[{"by": "카이토"}],
        when_happened="어제", feeling={"strength": 2, "sign": "pos", "under": "안도"},
    )
    canon_fact = _row(11, "세라", "identity", value="등대지기", turn=-1, position=-1, canon="card:desc")
    story_alias = _row(12, "세라", "also_called", value="세라 언니", turn=1, position=2)
    view = _make_view(
        [story_fact, canon_fact],
        extra_rows=[story_alias],
        canon_names=[{"key": "lore:sera", "names": ["세라", "등대의 세라"]}],
    )
    # Confirm canon alias exists on the resolution itself, so leaving it out is a real filter.
    assert any(row.get("canon") for _, _, row in view["resolution"].alias_rows)

    snap = carry.snapshot_of(view, None, "continue", [], SRC_ID, {10: REV_1, 12: REV_2})
    assert len(snap["facts"]) == 1
    fact = snap["facts"][0]
    assert fact["predicate"] == "has_status" and fact["value"] == "피곤함"
    assert fact["when_happened"] == "어제"
    assert fact["feeling"] == {"strength": 2, "sign": "pos", "under": "안도"}
    for forbidden in ("history", "versions", "claims", "subject_entity", "object_entity",
                      "names", "host_logical_id", "turn_hash", "id"):
        assert forbidden not in fact
    assert fact["from"] == {
        "conversation": str(SRC_ID),
        "assertion": 10,
        "revision": str(REV_1),
        "generation": "extract:gen-1",
        "repair": None,
    }
    assert len(snap["aliases"]) == 1
    assert snap["aliases"][0]["alias"] == "세라 언니"
    assert snap["aliases"][0]["from"]["assertion"] == 12
    assert snap["aliases"][0]["from"]["revision"] == str(REV_2)


def test_owner_repair_row_with_negative_id_records_null_assertion_and_repair_id() -> None:
    repaired = _row(
        -987654321, "세라", "located_in", obj="등대", object_type="place",
        turn=4, position=8, owner=True, repair=str(REP_ID), generation=None,
    )
    normal = _row(20, "카이토", "has_status", value="건강함", turn=2, position=4)
    view = _make_view([normal, repaired])

    snap = carry.snapshot_of(view, None, "continue", [], SRC_ID, {20: REV_1})
    # Newest first (position descending): position 8 before position 4.
    assert [f["position"] for f in snap["facts"]] == [8, 4]
    assert snap["facts"][0]["from"] == {
        "conversation": str(SRC_ID),
        "assertion": None,
        "revision": None,
        "generation": None,
        "repair": str(REP_ID),
    }
    assert snap["facts"][1]["from"]["assertion"] == 20
    assert snap["facts"][1]["from"]["revision"] == str(REV_1)


def test_continue_keeps_open_threads_only_and_regression_keeps_any_status() -> None:
    open_p = _row(30, "세라", "promised", obj="카이토", object_type="character",
                  value="열쇠를 찾아주기", turn=1, position=2, generation="extract:gen-open")
    closed_p = _row(31, "세라", "promised", obj="하나", object_type="character",
                    value="편지를 전해주기", turn=1, position=3, generation="extract:gen-closed")
    done_p = _row(32, "세라", "fulfilled", value="편지를 전해주기", turn=4, position=9)
    all_rows = [open_p, closed_p, done_p]
    r = resolve(SRC_ID, all_rows)
    for row in all_rows:
        _annotate(row, r)
    threads, _, _ = fold_threads(all_rows, r)
    view = {
        "facts": [],
        "threads": threads,
        "assertions": all_rows,
        "resolution": r,
        "entities": r.entities(),
        "excluded": {},
    }

    cont = carry.snapshot_of(view, None, "continue", [], SRC_ID, {30: REV_1, 31: REV_2})
    assert len(cont["threads"]) == 1
    assert cont["threads"][0]["status"] == "open"
    assert cont["threads"][0]["closed_turn"] is None
    assert cont["threads"][0]["from"]["generation"] == "extract:gen-open"
    assert cont["threads"][0]["from"]["revision"] == str(REV_1)

    reg = carry.snapshot_of(view, None, "regression", ["세라"], SRC_ID, {30: REV_1, 31: REV_2})
    assert {t["status"] for t in reg["threads"]} == {"open", "kept"}
    closed = next(t for t in reg["threads"] if t["status"] == "kept")
    assert closed["closed_turn"] == 4
    assert closed["from"]["generation"] == "extract:gen-closed"
    assert closed["knowledge"] == "limited" and closed["known_by"] == ["세라"]


def test_story_carried_held_or_omitted_by_mode() -> None:
    f = _row(40, "세라", "has_status", value="평온함", turn=1, position=2)
    view = _make_view([f])
    story_row = {"id": SUM_ID, "text": "세라와 카이토는 항구에 머물렀다.", "first_turn": 0, "last_turn": 7,
                 "generation": "summarize:s1"}

    kept = carry.snapshot_of(view, {"story": story_row, "story_held": []}, "continue", [], SRC_ID, {40: REV_1})
    assert kept["story"] == {
        "text": "세라와 카이토는 항구에 머물렀다.",
        "first_turn": 0,
        "last_turn": 7,
        "from": {"conversation": str(SRC_ID), "summary": str(SUM_ID), "generation": "summarize:s1"},
    }
    assert kept["story_left_out"] is None

    held = carry.snapshot_of(
        view, {"story": story_row, "story_held": [{"id": 99, "text": "비밀"}]},
        "continue", [], SRC_ID, {40: REV_1},
    )
    assert held["story"] is None and held["story_left_out"] == "secret"

    none_story = carry.snapshot_of(view, None, "continue", [], SRC_ID, {40: REV_1})
    assert none_story["story"] is None and none_story["story_left_out"] is None

    reg = carry.snapshot_of(view, {"story": story_row, "story_held": []}, "regression", ["세라"], SRC_ID, {40: REV_1})
    assert reg["story"] is None and reg["story_left_out"] is None and reg["aliases"] == []


# --- regression's five coordinator cases (each its own test) ----------------------------------------------------

def _regression_fixture() -> tuple[list[dict], object]:
    """Base characters 세라, 카이토, 하나, 유나 so every character resolves cleanly."""
    seed = [
        _row(100, "세라", "has_status", value="깨어 있음", position=1),
        _row(101, "카이토", "has_status", value="깨어 있음", position=2),
        _row(102, "하나", "has_status", value="깨어 있음", position=3),
        _row(103, "유나", "has_status", value="깨어 있음", position=4),
    ]
    return seed, resolve(SRC_ID, seed)


def test_regression_case_1_secret_kept_from_named_is_left_out() -> None:
    _, r = _regression_fixture()
    secret_from_sera = _row(
        110, "세라", "has_status", value="저주에 걸림",
        knowledge="limited", known_by=["하나"], hidden_from=["세라"], position=5,
    )
    secret_no_known_by = _row(
        111, "세라", "has_status", value="감시당함",
        knowledge="limited", known_by=None, hidden_from=["세라"], position=6,
    )
    assert carry.rememberers(secret_from_sera, ["세라"], r) == []
    assert carry.rememberers(secret_no_known_by, ["세라"], r) == []

    view = _make_view([secret_from_sera, secret_no_known_by], extra_rows=_regression_fixture()[0])
    snap = carry.snapshot_of(view, None, "regression", ["세라"], SRC_ID, {})
    assert snap["facts"] == []


def test_regression_case_2_secret_held_by_named_is_carried_for_that_named_only() -> None:
    seed, r = _regression_fixture()
    held_by_sera = _row(
        120, "세라", "knows", value="지하 통로의 암호",
        knowledge="limited", known_by=["세라"], hidden_from=["카이토", "하나"], position=5,
    )
    assert carry.rememberers(held_by_sera, ["세라", "카이토"], r) == ["세라"]

    view = _make_view([held_by_sera], extra_rows=seed)
    snap = carry.snapshot_of(view, None, "regression", ["세라", "카이토"], SRC_ID, {120: REV_1})
    assert len(snap["facts"]) == 1
    f = snap["facts"][0]
    assert f["knowledge"] == "limited"
    assert f["known_by"] == ["세라"]
    assert f["hidden_from"] == ["카이토", "하나"]
    assert f["orig_knowledge"] == "limited"
    assert f["orig_known_by"] == ["세라"]


def test_regression_case_3_public_fact_involving_named_is_remembered_by_all_named() -> None:
    seed, r = _regression_fixture()
    public_fact = _row(
        130, "세라", "relationship", obj="하나", object_type="character", value="자매",
        knowledge="public", known_by=None, hidden_from=None, position=5,
    )
    assert carry.rememberers(public_fact, ["카이토", "세라"], r) == ["카이토", "세라"]

    view = _make_view([public_fact], extra_rows=seed)
    snap = carry.snapshot_of(view, None, "regression", ["카이토", "세라"], SRC_ID, {130: REV_1})
    assert len(snap["facts"]) == 1
    f = snap["facts"][0]
    assert f["knowledge"] == "limited"
    assert f["known_by"] == ["카이토", "세라"]  # preserves order of `names`
    assert f["orig_knowledge"] == "public"
    assert f["orig_known_by"] is None


def test_regression_case_4_unmarked_fact_between_named_and_unnamed_remembered_by_involved_named_only() -> None:
    seed, r = _regression_fixture()
    unmarked = _row(
        140, "세라", "relationship", obj="하나", object_type="character", value="동료",
        knowledge="unknown", known_by=None, hidden_from=None, position=5,
    )
    limited_empty = _row(
        141, "세라", "event", value="하나와 약속함",
        participants=({"type": "character", "name": "하나"},),
        knowledge="limited", known_by=[], hidden_from=None, position=6,
    )
    assert carry.rememberers(unmarked, ["세라", "카이토"], r) == ["세라"]
    assert carry.rememberers(limited_empty, ["세라", "카이토"], r) == ["세라"]

    view = _make_view([unmarked, limited_empty], extra_rows=seed)
    snap = carry.snapshot_of(view, None, "regression", ["세라", "카이토"], SRC_ID, {})
    assert len(snap["facts"]) == 2
    for f in snap["facts"]:
        assert f["knowledge"] == "limited"
        assert f["known_by"] == ["세라"]


def test_regression_case_5_revealed_secret_is_carried() -> None:
    """After a reveal, the secret fold moves the named out of hidden_from and into known_by."""
    seed, r = _regression_fixture()
    revealed = _row(
        150, "하나", "event", value="편지를 태움",
        participants=({"type": "character", "name": "세라"},),
        knowledge="limited", known_by=["하나", "세라"], hidden_from=None, position=5,
    )
    assert carry.rememberers(revealed, ["세라", "카이토"], r) == ["세라"]

    view = _make_view([revealed], extra_rows=seed)
    snap = carry.snapshot_of(view, None, "regression", ["세라", "카이토"], SRC_ID, {150: REV_1})
    assert len(snap["facts"]) == 1
    f = snap["facts"][0]
    assert f["knowledge"] == "limited"
    assert f["known_by"] == ["세라"]
    assert f["orig_knowledge"] == "limited"
    assert f["orig_known_by"] == ["하나", "세라"]


def test_regression_row_involving_no_named_character_is_never_carried() -> None:
    seed, r = _regression_fixture()
    other_public = _row(160, "하나", "relationship", obj="유나", object_type="character", value="친구",
                        knowledge="public", position=5)
    other_known = _row(161, "하나", "has_status", value="피곤함",
                       knowledge="limited", known_by=["세라"], position=6)
    assert carry.rememberers(other_public, ["세라"], r) == []
    assert carry.rememberers(other_known, ["세라"], r) == []

    view = _make_view([other_public, other_known], extra_rows=seed)
    snap = carry.snapshot_of(view, None, "regression", ["세라"], SRC_ID, {})
    assert snap["facts"] == []


def test_regression_names_validation_deduplication_and_characters_list() -> None:
    f1 = _row(200, "세라", "has_status", value="건강함", position=1)
    f2 = _row(201, "세라", "located_in", obj="항구", object_type="place", position=2)
    f3 = _row(202, "카이토", "has_status", value="경계 중", position=3)
    f4 = _row(203, "유나", "has_status", value="대기 중", position=4)
    f5 = _row(204, "도현", "has_status", value="대기 중", position=5)
    alias = _row(205, "세라", "also_called", value="세라 언니", position=2)
    all_rows = [f1, f2, f3, f4, f5, alias]
    r = resolve(SRC_ID, all_rows, persona=("도현",))
    yuna_id = str(r.entity("character", "유나")["id"])
    kaito_id = str(r.entity("character", "카이토")["id"])
    excluded = {
        yuna_id: {"scope": "memory", "repair": "r1", "name": "유나"},
        kaito_id: {"scope": "cast", "repair": "r2", "name": "카이토"},
    }
    view = _make_view([f1, f2, f3, f4, f5], extra_rows=[alias], persona=("도현",), excluded=excluded)

    # Characters list: persona and memory-excluded left out; cast-excluded kept; most mentioned first.
    cont = carry.snapshot_of(view, None, "continue", [], SRC_ID, {})
    assert cont["characters"] == ["세라", "카이토"]

    # Aliases of one entity kept once, first spelling.
    reg = carry.snapshot_of(view, None, "regression", ["세라 언니", "세라", "카이토"], SRC_ID, {})
    assert reg["names"] == ["세라 언니", "카이토"]

    # Validation errors.
    with pytest.raises(carry.CarryError, match="유나 is no character of the source"):
        carry.snapshot_of(view, None, "regression", ["유나"], SRC_ID, {})
    with pytest.raises(carry.CarryError, match="도현 is no character of the source"):
        carry.snapshot_of(view, None, "regression", ["도현"], SRC_ID, {})
    with pytest.raises(carry.CarryError, match="모르는이 is no character of the source"):
        carry.snapshot_of(view, None, "regression", ["모르는이"], SRC_ID, {})
    with pytest.raises(carry.CarryError):
        carry.snapshot_of(view, None, "regression", [], SRC_ID, {})
    with pytest.raises(carry.CarryError):
        carry.snapshot_of(view, None, "continue", ["세라"], SRC_ID, {})
    with pytest.raises(carry.CarryError):
        carry.snapshot_of(view, None, "other", [], SRC_ID, {})
    with pytest.raises(carry.CarryError):
        carry.snapshot_of(view, None, "regression", [f"캐릭터{i}" for i in range(carry.MAX_NAMES + 1)], SRC_ID, {})


def test_regression_maps_persona_in_orig_known_by_and_resolves_aliases() -> None:
    alias = _row(210, "세라", "also_called", value="세라 언니", position=1)
    f_alias_known = _row(
        211, "세라 언니", "knows", value="탑의 비밀",
        knowledge="limited", known_by=["도현", "세라 언니"], hidden_from=["카이토"], position=2,
    )
    f_alias_hidden = _row(
        212, "세라", "has_status", value="추적당함",
        knowledge="limited", known_by=["하나"], hidden_from=["세라 언니"], position=3,
    )
    f_kaito = _row(213, "카이토", "has_status", value="대기", position=1)
    f_hana = _row(214, "하나", "has_status", value="대기", position=1)
    view = _make_view([f_alias_known, f_alias_hidden, f_kaito, f_hana], extra_rows=[alias], persona=("도현",))

    snap = carry.snapshot_of(view, None, "regression", ["세라"], SRC_ID, {211: REV_1})
    assert len(snap["facts"]) == 1
    f = snap["facts"][0]
    assert f["known_by"] == ["세라"]
    assert f["orig_knowledge"] == "limited"
    assert f["orig_known_by"] == [PERSONA, "세라 언니"]
    assert carry.served_generations(snap) == ["extract:gen-1"]


# --- fingerprint, JSON serializability and preview_of -----------------------------------------------------------

def test_fingerprint_stability_sensitivity_and_json_serializability() -> None:
    f = _row(
        300, "세라", "event", value="열쇠를 주움",
        confidence=Decimal("0.85"),
        participants=({"type": "character", "name": "카이토"},),
        turn=3, position=6,
    )
    view = _make_view([f])
    snap = carry.snapshot_of(view, None, "continue", [], SRC_ID, {300: REV_1})
    # Must be plain JSON serializable (Decimal -> float, tuple -> list, UUID -> str).
    dumped = json.dumps(snap, ensure_ascii=False)
    loaded = json.loads(dumped)
    assert loaded["facts"][0]["confidence"] == 0.85
    assert loaded["facts"][0]["participants"] == [{"type": "character", "name": "카이토"}]

    reading_a = {
        "source": str(SRC_ID),
        "mode": "continue",
        "names": [],
        "cutoff": {"commit": str(COMMIT_ID), "position": 6, "turn": 3},
        "generations": {"extractor": "extract:gen-1", "summarize": None, "canon": None, "served": ["extract:gen-1"]},
        "snapshot": snap,
    }
    # Adding non-stored metadata (e.g. link id or created_at) must not change the fingerprint.
    reading_b = {**reading_a, "id": "ignored", "created_at": datetime.now(timezone.utc).isoformat()}
    fp_a = carry.fingerprint(reading_a)
    assert len(fp_a) == 64
    assert carry.fingerprint(reading_b) == fp_a

    # Changing any stored value changes the fingerprint.
    changed_snap = json.loads(dumped)
    changed_snap["facts"][0]["value"] = "열쇠를 잃어버림"
    assert carry.fingerprint({**reading_a, "snapshot": changed_snap}) != fp_a
    assert carry.fingerprint({**reading_a, "cutoff": {**reading_a["cutoff"], "position": 7}}) != fp_a
    assert carry.fingerprint({**reading_a, "mode": "regression"}) != fp_a


def test_preview_of_counts_and_first_lines() -> None:
    facts = [_row(400 + i, "세라", "has_trait", value=f"특징 {i}", turn=i, position=i) for i in range(1, 7)]
    p1 = _row(420, "세라", "promised", obj="카이토", object_type="character", value="첫 약속", turn=1, position=10)
    p2 = _row(421, "세라", "promised", obj="카이토", object_type="character", value="둘째 약속", turn=2, position=11)
    p3 = _row(422, "세라", "promised", obj="카이토", object_type="character", value="셋째 약속", turn=3, position=12)
    all_rows = facts + [p1, p2, p3]
    r = resolve(SRC_ID, all_rows)
    for row in all_rows:
        _annotate(row, r)
    threads, _, _ = fold_threads([p1, p2, p3], r)
    view = {
        "facts": sorted(facts, key=lambda x: x["position"], reverse=True),
        "threads": threads,
        "assertions": all_rows,
        "resolution": r,
        "entities": r.entities(),
        "excluded": {},
    }
    snap = carry.snapshot_of(view, None, "continue", [], SRC_ID, {})
    reading = {
        "source": str(SRC_ID),
        "mode": "continue",
        "names": [],
        "cutoff": {"commit": str(COMMIT_ID), "position": 12, "turn": 3},
        "generations": {"extractor": "extract:gen-1", "summarize": None, "canon": None, "served": ["extract:gen-1"]},
        "snapshot": snap,
    }
    reading["fingerprint"] = carry.fingerprint(reading)

    prev = carry.preview_of(reading, {"character": "세라", "chat": "항구의 밤"}, replaces=REP_ID)
    assert prev["mode"] == "continue"
    assert prev["source"] == {"id": str(SRC_ID), "character": "세라", "chat": "항구의 밤"}
    assert prev["counts"] == {"facts": 6, "aliases": 0, "threads": 3, "story": False}
    assert len(prev["first_lines"]) == carry.FIRST_LINES  # 6 facts + first 2 threads = 8
    assert prev["first_lines"][:6] == [fact_text(f) for f in snap["facts"]]
    assert prev["first_lines"][6:] == [snap["threads"][0]["text"], snap["threads"][1]["text"]]
    assert prev["replaces"] == str(REP_ID)
    assert prev["fingerprint"] == reading["fingerprint"]
    assert prev["characters"] == ["세라", "카이토"]
