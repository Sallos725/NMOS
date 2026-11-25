"""Phase 64 (`extract-v20`, `canon-v2`, ADR 0091): conditional forms of address.

Verifies migration `0040_address_condition.sql`, upgrade preservation, archive round-trip, normalization,
prompt and generation key guarantees (ADDS zero-reextract switch, canon-v2 pairing and reuse), read-side
slot folding (default/public/private/situational/all, split cleanup, negation, deletion rollback, locks,
repairs, dropped-fact restore, carry links), independent knowledge marks (<Private> and Author's Note),
packet rendering (`packet-v19` and `packet-v20`, `replaced_marks`, `packet.restated`, situational cap),
and UI surfaces (Inspector, Panel views, Timeline, Author's Note). Synthetic names only."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import active_generation, make_client
from nmos_sidecar import (archive, canonfacts, carry, dropped, extraction as X, facts, generations, inspector,
                          memorymap, notes, packet, predicates as P, repairs, retrieval, timeline, views)
from nmos_sidecar.config import Settings
from nmos_sidecar.migrate import apply_migrations, migration_files
from simchat import SimChat
from test_archive import read as read_archive
from test_canon import push as push_canon
from test_canon_facts import drain as drain_canon
from test_extraction import drain, filler
from test_generations import LLM, conv_id
from test_phase60_pins import BASE, PINNED_EXTRACT_SPEC_FIELDS
from test_sidecar_integration import recall, sync
from test_upgrade import FIXTURES, LATEST, restore

USED = {"calls": 1, "input": 100, "output": 10}
CHAR = "character"


def addr(
    subject: str,
    obj: str,
    value: str,
    cond: dict[str, Any] | None = None,
    *,
    polarity: str = "positive",
    knowledge: str = "public",
    known_by: list[str] | None = None,
    hidden_from: list[str] | None = None,
    evidence: str = "",
    **extra: Any,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "subject": subject,
        "subject_type": CHAR,
        "predicate": "addresses",
        "object": obj,
        "object_type": CHAR,
        "value": value,
        "polarity": polarity,
        "modality": "actual",
        "source": "narration",
        "knowledge": knowledge,
        "known_by": known_by or [],
        "hidden_from": hidden_from or [],
        "evidence": evidence,
        **extra,
    }
    if cond is not None:
        row["address_condition"] = cond
    return row


def _fold_row(
    idx: int,
    value: str,
    cond: dict[str, Any] | None = None,
    *,
    turn: int | None = None,
    polarity: str = "positive",
    canon: str | None = None,
    knowledge: str = "public",
    known_by: list[str] | None = None,
    hidden_from: list[str] | None = None,
    subject: str = "하나",
    obj: str = "도윤",
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": idx + 1,
        "position": -1_000_000 + idx if canon else idx * 2 + 1,
        "turn": -1 if canon else (idx if turn is None else turn),
        "subject": subject,
        "subject_type": CHAR,
        "predicate": "addresses",
        "object": obj,
        "object_type": CHAR,
        "value": value,
        "polarity": polarity,
        "modality": "actual",
        "source": "narration",
        "knowledge": knowledge,
        "known_by": known_by,
        "hidden_from": hidden_from,
        "host_logical_id": f"canon:{canon}" if canon else f"m{idx}",
        "evidence": value,
    }
    if canon:
        row["canon"] = canon
    if cond is not None:
        row["address_condition"] = cond
    return row


# --- 1. Normalization & helpers -------------------------------------------------------------------------------


def test_address_condition_normalization_and_labels():
    assert P.address_condition(addr("하나", "도윤", "존댓말", {"scope": "public", "when": "  회사  · 남들 앞 "})) == {
        "scope": "public", "when": "회사 · 남들 앞",
    }
    assert P.address_condition(addr("하나", "도윤", "존댓말", {"scope": "PUBLIC", "when": None})) == {
        "scope": "public", "when": None,
    }
    assert P.address_condition(addr("하나", "도윤", "반말", {"scope": "private", "when": "둘만 있을 때"})) == {
        "scope": "private", "when": "둘만 있을 때",
    }
    assert P.address_condition(addr("하나", "도윤", "코드네임", {"scope": "situational", "when": "임무 중"})) == {
        "scope": "situational", "when": "임무 중",
    }
    # Situational without a non-empty phrase degrades to None (never creates an unnamed slot)
    assert P.address_condition(addr("하나", "도윤", "반말", {"scope": "situational", "when": ""})) is None
    assert P.address_condition(addr("하나", "도윤", "반말", {"scope": "situational", "when": "null"})) is None
    assert P.address_condition(addr("하나", "도윤", "반말", {"scope": "situational"})) is None
    # `all` drops any stray `when`
    assert P.address_condition(addr("하나", "도윤", "반말", {"scope": "all", "when": "어디서든"})) == {
        "scope": "all", "when": None,
    }
    # Truncation at 60 chars
    long_when = "가" * 80
    assert P.address_condition(addr("하나", "도윤", "반말", {"scope": "situational", "when": long_when})) == {
        "scope": "situational", "when": "가" * 60,
    }
    # Invalid scopes / non-dict / non-addresses predicates
    for bad in ({"scope": "default"}, {"scope": "casual"}, {"scope": ""}, "public", None, []):
        assert P.address_condition(addr("하나", "도윤", "반말", bad)) is None
    other_pred = {**addr("하나", "도윤", "연인", {"scope": "private", "when": "둘만"}), "predicate": "relationship"}
    assert P.address_condition(other_pred) is None

    # Labels (localized fallback when `when` is None; `all` and default emit no label)
    assert P.address_label(addr("하나", "도윤", "존댓말")) is None
    assert P.address_label(addr("하나", "도윤", "반말", {"scope": "all", "when": None})) is None
    assert P.address_label(addr("하나", "도윤", "존댓말", {"scope": "public", "when": None}), "ko") == "공적인 자리"
    assert P.address_label(addr("하나", "도윤", "존댓말", {"scope": "public", "when": None}), "en") == "in public"
    assert P.address_label(addr("하나", "도윤", "반말", {"scope": "private", "when": None}), "ko") == "사적인 자리"
    assert P.address_label(addr("하나", "도윤", "반말", {"scope": "private", "when": None}), "en") == "in private"
    assert P.address_label(addr("하나", "도윤", "반말", {"scope": "private", "when": "둘만 있을 때"}), "en") == "둘만 있을 때"


def test_normalize_gates_address_condition_by_compiler():
    item = addr("하나", "도윤", "반말, '오빠'", {"scope": "private", "when": "둘만 있을 때"})
    for old in ("extract-v15", "extract-v16", "extract-v17", "extract-v18", "extract-v19"):
        assert X.normalize([item], "", compiler=old)[0]["address_condition"] is None
    assert X.normalize([item], "", compiler="extract-v20")[0]["address_condition"] == {
        "scope": "private", "when": "둘만 있을 때",
    }
    assert X.normalize([item], "", address_conditions=True)[0]["address_condition"] == {
        "scope": "private", "when": "둘만 있을 때",
    }


# --- 2. Prompts, generation keys, and zero-reextract switch ---------------------------------------------------


def test_v20_and_canon_v2_prompts_and_growth_bounds():
    assert X.DEFAULT_COMPILER == "extract-v16" and "extract-v20" in X.COMPILERS
    assert "extract-v20" in X.ROLES & X.PARTS_APART & X.CONFIRMS & X.FEELINGS & X.HAPPENED & X.ADDRESS_CONDITIONS
    assert "extract-v20" not in X.HORIZONS | X.SPEAKERS
    assert "told" in P.registry_for("extract-v20")

    v19, v20 = X.prompt_of("extract-v19"), X.prompt_of("extract-v20")
    assert X.ADDRESS_CONDITION_RULE not in v19 and '"address_condition"' not in v19
    assert X.ADDRESS_CONDITION_RULE in v20 and '"address_condition"' in v20
    assert v20 == X._v20(v19)
    assert X.prompt_of("extract-v20", roles=False) == X.SYSTEM_V20 and X.ROLE_ENDINGS not in X.SYSTEM_V20
    formatted19 = v19.format(registry=P.registry_prompt(compiler="extract-v19"))
    formatted20 = v20.format(registry=P.registry_prompt(compiler="extract-v20"))
    growth = (len(formatted20) - len(formatted19)) / len(formatted19)
    assert 0 < growth < 0.15, f"prompt grew by {growth:.1%}"

    # Canon-v1 untouched; canon-v2 paired with extract-v20 only
    assert canonfacts.CANON_ADDRESS_RULE not in canonfacts.PROMPT
    assert canonfacts.CANON_ADDRESS_RULE in canonfacts.PROMPT_V2
    assert canonfacts.PROMPT_V2.format(registry=P.registry_prompt(canonfacts.PREDICATES))
    for c in ("", "extract-v15", "extract-v16", "extract-v17", "extract-v18", "extract-v19"):
        assert canonfacts.version_of(Settings(**BASE, extract_compiler=c)) == "canon-v1"
    assert canonfacts.version_of(Settings(**BASE, extract_compiler="extract-v20")) == "canon-v2"
    c1 = canonfacts.generation(Settings(**BASE, extract_compiler="extract-v19"))
    c2 = canonfacts.generation(Settings(**BASE, extract_compiler="extract-v20"))
    assert c1.key != c2.key and c1.spec["version"] == "canon-v1" and c2.spec["version"] == "canon-v2"


def test_v20_spec_matches_adds_fields_and_switch_queues_zero_turns(migrated: str, db: psycopg.Connection):
    v19_spec = X.extractor(Settings(**BASE, extract_compiler="extract-v19")).spec
    v20_spec = X.extractor(Settings(**BASE, extract_compiler="extract-v20")).spec
    assert sorted(v20_spec) == sorted(v19_spec) == PINNED_EXTRACT_SPEC_FIELDS["extract-v18"]
    assert {k for k in v19_spec if v19_spec[k] != v20_spec[k]} == {"compiler", "prompt"}
    assert "extract-v20" in generations.ADDS

    chat = SimChat()
    chat.user("하나가 도윤에게 인사한다.")
    chat.reply("하나는 도윤을 향해 고개를 숙였다. \"안녕하세요, 과장님.\"")
    chat.user("다음.")
    chat.reply("잔잔한 오후였다.")

    def stub_extract(system: str, user: str) -> tuple[dict[str, Any], str, dict[str, int]]:
        target = user.split("TARGET turn", 1)[1] if "TARGET turn" in user else ""
        if "과장님" in target:
            return {"assertions": [addr("하나", "도윤", "존댓말, '과장님'", evidence="안녕하세요, 과장님")]}, "{}", USED
        return {"assertions": []}, "{}", USED

    with make_client(migrated, **LLM, extract_backfill=100, extract_compiler="extract-v19") as c:
        sync(c, chat)
        drain(migrated, stub_extract)
    assert db.execute("SELECT count(*) AS n FROM job WHERE kind = 'extract' AND status = 'queued'").fetchone()["n"] == 0

    # Switch v19 -> v20 -> v19 -> v16: zero extract jobs queued on an already-covered chat
    for comp in ("extract-v20", "extract-v19", "extract-v16", "extract-v20"):
        with make_client(migrated, **LLM, extract_backfill=100, extract_compiler=comp):
            queued = db.execute("SELECT count(*) AS n FROM job WHERE kind = 'extract' AND status = 'queued'").fetchone()["n"]
            assert queued == 0, comp


# --- 3. Migration 0040, CHECK constraints, upgrade fixtures, and archive round-trip ---------------------------


def test_migration_0040_check_constraint_and_upgrade_fixtures(migrated: str, db: psycopg.Connection):
    col = db.execute(
        "SELECT data_type, is_nullable FROM information_schema.columns"
        " WHERE table_schema = 'public' AND table_name = 'assertion' AND column_name = 'address_condition'"
    ).fetchone()
    assert col == {"data_type": "jsonb", "is_nullable": "YES"}
    assert X.ASSERTION_COLUMNS[-1] == "address_condition"
    assert "address_condition" in X.JSON_COLUMNS

    chat = SimChat()
    chat.user("시작.")
    chat.reply("하나는 도윤을 과장님이라고 부른다.")
    chat.user("다음.")
    chat.reply("오후가 지나갔다.")
    with make_client(migrated, **LLM, extract_compiler="extract-v20") as c:
        sync(c, chat)
        drain(migrated, lambda s, u: ({"assertions": [addr("하나", "도윤", "존댓말, '과장님'", evidence="과장님")]}, "{}", USED))
    row_id = db.execute("SELECT id FROM assertion ORDER BY id LIMIT 1").fetchone()["id"]

    with psycopg.connect(migrated, row_factory=dict_row, autocommit=False) as conn:
        invalid_payloads = [
            '"public"',
            '[]',
            '{}',
            '{"scope": "unknown"}',
            '{"scope": "situational"}',
            '{"scope": "situational", "when": null}',
            '{"scope": "situational", "when": "   "}',
            f'{{"scope": "situational", "when": "{"가" * 61}"}}',
            '{"scope": "all", "when": "어디서든"}',
            '{"scope": "public", "when": 123}',
            '{"scope": "public", "when": "   "}',
            f'{{"scope": "public", "when": "{"가" * 61}"}}',
        ]
        for bad in invalid_payloads:
            with pytest.raises(psycopg.errors.CheckViolation, match="address_condition"):
                with conn.transaction():
                    conn.execute("UPDATE assertion SET address_condition = %s::jsonb WHERE id = %s", (bad, row_id))

        valid_payloads = [
            '{"scope": "public", "when": null}',
            '{"scope": "public", "when": "공적인 자리"}',
            '{"scope": "private", "when": "둘만 있을 때"}',
            f'{{"scope": "situational", "when": "{"가" * 60}"}}',
            '{"scope": "all", "when": null}',
        ]
        for ok in valid_payloads:
            conn.execute("UPDATE assertion SET address_condition = %s::jsonb WHERE id = %s", (ok, row_id))
        conn.execute("UPDATE assertion SET address_condition = NULL WHERE id = %s", (row_id,))
        conn.rollback()


@pytest.mark.parametrize("dump", FIXTURES, ids=[p.stem for p in FIXTURES])
def test_upgrade_fixtures_apply_0040_with_nulls_and_preserved_rows(dump: Path, database_url: str, tmp_path: Path):
    restore(database_url, dump)
    pre_dir = tmp_path / "migrations_to_0039"
    pre_dir.mkdir()
    for path in migration_files():
        if path.name <= "0039_model_call.sql":
            shutil.copy(path, pre_dir / path.name)
    apply_migrations(database_url, directory=pre_dir)
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        before = conn.execute(
            "SELECT count(*) AS n, md5(string_agg(id::text, ',' ORDER BY id)) AS h FROM assertion"
        ).fetchone()
    applied = apply_migrations(database_url)
    assert "0040_address_condition.sql" in applied
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        after = conn.execute(
            "SELECT count(*) AS n, md5(string_agg(id::text, ',' ORDER BY id)) AS h,"
            " count(address_condition) AS non_null FROM assertion"
        ).fetchone()
    assert (after["n"], after["h"], after["non_null"]) == (before["n"], before["h"], 0)


# --- 4. Pure read-side folding scenarios (`facts._address_versions`) ------------------------------------------


def test_folding_default_and_private_coexist_without_supersession():
    rows = [
        _fold_row(0, "존댓말, '과장님'", turn=0),
        _fold_row(1, "반말, '오빠'", {"scope": "private", "when": "둘만 있을 때"}, turn=5),
    ]
    out = facts._versions(rows)
    assert len(out) == 2
    by_slot = {P.address_slot(f): f for f in out}
    assert by_slot[("default",)]["value"] == "존댓말, '과장님'"
    assert by_slot[("private",)]["value"] == "반말, '오빠'"
    assert facts.earlier(by_slot[("default",)]) is None
    assert facts.earlier(by_slot[("private",)]) is None
    # Neither is superseded, so `replaced_marks` suppresses no old excerpts
    assert retrieval.replaced_marks(out, frozenset({"하나", "도윤"}), calls=True) == []


def test_folding_default_and_public_coexist_when_no_private():
    rows = [
        _fold_row(0, "반말, '도윤아'", turn=0),
        _fold_row(1, "존댓말, '과장님'", {"scope": "public", "when": "회사에서"}, turn=4),
    ]
    out = facts._versions(rows)
    assert {(P.address_slot(f), f["value"]) for f in out} == {
        (("default",), "반말, '도윤아'"),
        (("public",), "존댓말, '과장님'"),
    }


def test_folding_split_cleanup_retires_stale_default_once_public_and_private_both_exist():
    # Case Z2: Turn 0 default 과장님 -> Turn 5 private 오빠 -> Turn 10 public 팀장님
    rows = [
        _fold_row(0, "존댓말, '과장님'", turn=0),
        _fold_row(1, "반말, '오빠'", {"scope": "private", "when": "둘만 있을 때"}, turn=5),
        _fold_row(2, "존댓말, '팀장님'", {"scope": "public", "when": "공적인 자리"}, turn=10),
    ]
    out = facts._versions(rows)
    assert len(out) == 2  # no zombie default
    by_slot = {P.address_slot(f): f for f in out}
    assert set(by_slot) == {("public",), ("private",)}
    assert by_slot[("public",)]["value"] == "존댓말, '팀장님'"
    assert facts.earlier(by_slot[("public",)])["value"] == "존댓말, '과장님'"
    assert facts.earlier(by_slot[("private",)]) is None
    # `replaced_marks` drops superseded '과장님' but keeps active '팀장님' and '오빠'
    marks = retrieval.replaced_marks(out, frozenset({"하나", "도윤"}), calls=True)
    assert len(marks) == 1 and "과장님" in marks[0][1] and "오빠" not in marks[0][1]


def test_folding_same_turn_split_attaches_stale_default_to_matching_side():
    # Case Z1: Turn 0 default 과장님 -> Turn 5 emits BOTH public 과장님 and private 오빠
    rows = [
        _fold_row(0, "존댓말, '과장님'", turn=0),
        _fold_row(1, "존댓말, '과장님'", {"scope": "public", "when": "공적인 자리"}, turn=5),
        _fold_row(2, "반말, '오빠'", {"scope": "private", "when": "둘만 있을 때"}, turn=5),
    ]
    out = facts._versions(rows)
    assert len(out) == 2
    by_slot = {P.address_slot(f): f for f in out}
    assert facts.earlier(by_slot[("public",)]) is None  # same value as old default
    assert facts.earlier(by_slot[("private",)]) is None  # old default did NOT attach to private


def test_folding_default_update_keeps_private_intact():
    rows = [
        _fold_row(0, "존댓말, '과장님'", turn=0),
        _fold_row(1, "반말, '오빠'", {"scope": "private", "when": "둘만 있을 때"}, turn=5),
        _fold_row(2, "존댓말, '팀장님'", turn=10),  # model omitted `public`
    ]
    out = facts._versions(rows)
    by_slot = {P.address_slot(f): f for f in out}
    assert set(by_slot) == {("default",), ("private",)}
    assert by_slot[("default",)]["value"] == "존댓말, '팀장님'"
    assert facts.earlier(by_slot[("default",)])["value"] == "존댓말, '과장님'"
    assert by_slot[("private",)]["value"] == "반말, '오빠'"


def test_folding_all_unifies_and_deleting_unifying_turn_restores_branches():
    before_unify = [
        _fold_row(0, "존댓말, '팀장님'", {"scope": "public", "when": "공적인 자리"}, turn=0),
        _fold_row(1, "반말, '오빠'", {"scope": "private", "when": "둘만 있을 때"}, turn=5),
        _fold_row(2, "코드네임 '레이븐'", {"scope": "situational", "when": "임무 중"}, turn=8),
    ]
    unified_row = _fold_row(3, "반말, '오빠'", {"scope": "all", "when": None}, turn=12)

    out = facts._versions([*before_unify, unified_row])
    assert len(out) == 1
    [sole] = out
    assert sole["value"] == "반말, '오빠'"
    assert P.address_label(sole) is None  # unconditional display
    assert facts.fact_text(sole) == "하나 addresses 도윤: 반말, '오빠'"
    # Prior distinct values stay in history so `earlier()`/`first()` still answer "how did she call him before?"
    assert facts.first(sole)["value"] == "존댓말, '팀장님'"
    assert facts.earlier(sole)["value"] == "코드네임 '레이븐'"

    # Invariant 7: removing turn 12 immediately restores all three branches
    restored = facts._versions(before_unify)
    assert len(restored) == 3
    assert {P.address_slot(f) for f in restored} == {("public",), ("private",), ("situational", "임무 중")}


def test_folding_situational_coexist_update_and_negation_is_slot_scoped():
    rows = [
        _fold_row(0, "존댓말, '과장님'", {"scope": "public", "when": "공적인 자리"}, turn=0),
        _fold_row(1, "반말, '오빠'", {"scope": "private", "when": "둘만 있을 때"}, turn=2),
        _fold_row(2, "코드네임 '레이븐'", {"scope": "situational", "when": "임무 중"}, turn=4),
        _fold_row(3, "풀네임 '김도윤'", {"scope": "situational", "when": "화났을 때"}, turn=6),
        _fold_row(4, "코드네임 '울프'", {"scope": "situational", "when": "임무 중"}, turn=8),
        _fold_row(5, "반말, '오빠'", {"scope": "private", "when": "둘만 있을 때"}, turn=10, polarity="negative"),
    ]
    out = facts._versions(rows)
    by_slot = {P.address_slot(f): f for f in out}
    assert set(by_slot) == {("public",), ("private",), ("situational", "임무 중"), ("situational", "화났을 때")}
    assert by_slot[("public",)]["polarity"] == "positive"
    assert by_slot[("private",)]["polarity"] == "negative"  # only private ended
    assert by_slot[("situational", "임무 중")]["value"] == "코드네임 '울프'"
    assert facts.earlier(by_slot[("situational", "임무 중")])["value"] == "코드네임 '레이븐'"
    assert by_slot[("situational", "화났을 때")]["value"] == "풀네임 '김도윤'"


def test_packet_selection_caps_situational_addresses_at_three_newest_unless_queried():
    rows = [
        _fold_row(0, "존댓말, '과장님'", {"scope": "public", "when": "공적인 자리"}, turn=0),
        _fold_row(1, "반말, '오빠'", {"scope": "private", "when": "둘만 있을 때"}, turn=1),
        _fold_row(2, "별명 A", {"scope": "situational", "when": "변장했을 때"}, turn=2),
        _fold_row(3, "별명 B", {"scope": "situational", "when": "화났을 때"}, turn=3),
        _fold_row(4, "별명 C", {"scope": "situational", "when": "임무 중"}, turn=4),
        _fold_row(5, "별명 D", {"scope": "situational", "when": "편지할 때"}, turn=5),
    ]
    folded = facts._versions(rows)
    assert len(folded) == 6
    picked = facts.relevant_facts(folded, "하나가 도윤을 본다.", "", set(), limit=12)
    sit_picked = [f for f in picked if (f.get("address_condition") or {}).get("scope") == "situational"]
    assert len(sit_picked) == facts.SITUATIONAL_ADDRESS_MAX == 3
    assert {f["value"] for f in sit_picked} == {"별명 B", "별명 C", "별명 D"}
    # Public & private are never dropped by the situational cap
    assert {f["value"] for f in picked if (f.get("address_condition") or {}).get("scope") in ("public", "private")} == {
        "존댓말, '과장님'", "반말, '오빠'",
    }
    # Explicitly asking about the oldest situational condition ranks it in
    queried = facts.relevant_facts(folded, "하나가 변장했을 때 도윤을 뭐라고 불러?", "", set(), limit=12)
    assert "별명 A" in {f["value"] for f in queried}


def test_packet_restated_keeps_distinct_conditional_addresses_even_with_same_value():
    pub = _fold_row(0, "존댓말, '도윤 씨'", {"scope": "public", "when": "공적인 자리"}, turn=0)
    priv = _fold_row(1, "존댓말, '도윤 씨'", {"scope": "private", "when": "둘만 있을 때"}, turn=2)
    lines = [facts.fact_entry(pub), facts.fact_entry(priv)]
    assert packet.restated(lines) == {}


def test_past_given_name_now_full_name_plus_emotional_slip_habit():
    """Owner scenario: used to call by given name ('도윤아'), now calls by full name ('서도윤'),
    but when flustered or overcome by emotion the old given name ('도윤아') slips out."""
    rows = [
        _fold_row(0, "반말, '도윤아'라고 이름만으로 부름", turn=0),
        _fold_row(1, "존댓말, '서도윤'이라고 풀네임으로 부름", turn=10),
        _fold_row(2, "반말, '도윤아'라고 이름만으로 튀어나옴",
                  {"scope": "situational", "when": "감정이 흐트러지거나 격해질 때"}, turn=10),
    ]
    out = facts._versions(rows)
    by_slot = {P.address_slot(f): f for f in out}
    assert set(by_slot) == {("default",), ("situational", "감정이 흐트러지거나 격해질 때")}
    dflt = by_slot[("default",)]
    slip = by_slot[("situational", "감정이 흐트러지거나 격해질 때")]

    # Default line keeps the current full name AND names the past given name via `before:`
    dflt_line = facts.fact_line(dflt, before=True)
    assert "하나 addresses 도윤: 존댓말, '서도윤'이라고 풀네임으로 부름" in dflt_line
    assert "before, turn 0: 하나 addresses 도윤: 반말, '도윤아'라고 이름만으로 부름" in dflt_line

    # Situational line stays active beside it with no spurious `before:`
    slip_line = facts.fact_line(slip, before=True)
    assert "하나 addresses 도윤 [감정이 흐트러지거나 격해질 때]: 반말, '도윤아'라고 이름만으로 튀어나옴" in slip_line
    assert "; before," not in slip_line

    # Because '도윤아' is STILL active in the situational slot, `replaced_marks` must NOT treat '도윤아' as obsolete
    marks = retrieval.replaced_marks(out, frozenset({"하나", "도윤"}), calls=True)
    assert all("도윤아" not in old_q for _, old_q, _, _, _ in marks)


def test_default_repair_target_never_cross_matches_private_slot_on_quote_fallback():
    dflt = _fold_row(0, "존댓말, '과장님'", turn=2)
    dflt["evidence"] = "회사에선 과장님, 둘만 있을 땐 오빠라고 부른다."
    priv = _fold_row(1, "반말, '오빠'", {"scope": "private", "when": "둘만 있을 때"}, turn=2)
    priv["evidence"] = "회사에선 과장님, 둘만 있을 땐 오빠라고 부른다."
    target = repairs.fact_target(dflt)
    assert repairs.match_fact(target, [priv], None, quote=True) is None
    assert repairs.match_fact(target, [priv, dflt], None, quote=True) is dflt


# --- 5. End-to-end DB: extract-v20, canon-v2, secrets/<Private>, locks, repairs, dropped, carry, archive, UI ---


def test_e2e_v20_secrets_private_packet_notes_views_timeline_and_archive(
    migrated: str, database_url_factory, tmp_path: Path
):
    chat = SimChat()
    chat.user("회사에서 첫 인사.")
    chat.reply("하나는 도윤을 향해 고개를 숙였다. \"과장님, 안녕하세요.\"")
    chat.user("둘만 남았다.")
    chat.reply("도윤이 웃었다. \"둘만 있을 땐 반말하고 오빠라고 불러. 민수한테는 비밀로 하고.\"")
    filler(chat, 8)  # move turns out of the prompt window so the packet includes them

    def complete(system: str, user: str) -> tuple[dict[str, Any], str, dict[str, int]]:
        target = user.split("TARGET turn", 1)[1] if "TARGET turn" in user else ""
        items = []
        if "과장님, 안녕하세요" in target:
            items.append(addr("하나", "도윤", "존댓말, '과장님'",
                              {"scope": "public", "when": "공적인 자리·회사"},
                              knowledge="public", evidence="과장님, 안녕하세요"))
        if "둘만 있을 땐" in target:
            items.append(addr("하나", "도윤", "반말, '오빠'",
                              {"scope": "private", "when": "둘만 있을 때"},
                              knowledge="limited", known_by=["하나", "도윤"], hidden_from=["민수"],
                              evidence="둘만 있을 땐 반말하고 오빠라고 불러"))
        return {"assertions": items}, "{}", USED

    with make_client(migrated, **LLM, extract_compiler="extract-v20", packet_policy="packet-v20") as c:
        sync(c, chat)
        drain(migrated, complete)
        cid = conv_id(c, chat)

        # Scene includes 민수: public title goes to <Facts>, secret private address goes to <Private>
        pkt_v20 = recall(c, chat, "민수가 회의실로 들어오며 하나와 도윤을 불렀다.", budget=2000)["packet"]["text"]
        assert "<Facts>" in pkt_v20 and "<Private>" in pkt_v20
        facts_sec = pkt_v20.split("<Facts>", 1)[1].split("</Facts>", 1)[0]
        priv_sec = pkt_v20.split("<Private>", 1)[1].split("</Private>", 1)[0]
        assert "하나 addresses 도윤 [공적인 자리·회사]: 존댓말, '과장님'" in facts_sec
        assert "오빠" not in facts_sec
        assert "하나 addresses 도윤 [둘만 있을 때]: 반말, '오빠'" in priv_sec

        # Also works under default packet-v19
        with make_client(migrated, **LLM, extract_compiler="extract-v20", packet_policy="packet-v19") as c19:
            pkt_v19 = recall(c19, chat, "민수가 회의실로 들어오며 하나와 도윤을 불렀다.", budget=2000)["packet"]["text"]
            assert "하나 addresses 도윤 [공적인 자리·회사]: 존댓말, '과장님'" in pkt_v19
            assert "하나 addresses 도윤 [둘만 있을 때]: 반말, '오빠'" in pkt_v19

        # Author's Note: secrets=False keeps public and hides secret private; secrets=True shows both with conditions
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            head = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (cid,)).fetchone()["head_commit_id"]
            view = facts.memory_view(conn, head, active_generation(conn, "extract").key)

        addr_no_sec = "\n".join(notes.address_lines(view["facts"], secrets=False))
        addr_with_sec = "\n".join(notes.address_lines(view["facts"], secrets=True))
        assert "[공적인 자리·회사]" in addr_no_sec and "과장님" in addr_no_sec
        assert "오빠" not in addr_no_sec
        assert "[공적인 자리·회사]" in addr_with_sec and "[둘만 있을 때]" in addr_with_sec and "오빠" in addr_with_sec

        # Inspector, Panel views, Memory map, Timeline
        insp_html = c.get(f"/inspector/c/{cid}", params={"lang": "ko"}).text
        assert "공적인 자리·회사" in insp_html and "둘만 있을 때" in insp_html

        mem_html = c.get(f"/views/c/{cid}/memory", params={"lang": "ko"}).text
        assert "[공적인 자리·회사]" in mem_html and "[둘만 있을 때]" in mem_html

        hana_id = next(e["id"] for e in view["entities"] if e["name"] == "하나")
        person_html = c.get(f"/views/c/{cid}/person/{hana_id}", params={"lang": "ko"}).text
        assert "[공적인 자리·회사]" in person_html and "[둘만 있을 때]" in person_html

        tl_html = inspector.character_timeline({"id": cid}, hana_id, view, lang="ko", now=10)
        assert "[공적인 자리·회사]" in tl_html and "[둘만 있을 때]" in tl_html

        # Memory map detail carries conditions on speech
        g = memorymap.graph({**view, "facts": [*view["facts"], {
            **view["facts"][0], "id": 999999, "predicate": "relationship", "value": "동료",
        }]})
        assert any("[공적인 자리·회사]" in views._tie_text(e, "ko") and "[둘만 있을 때]" in views._tie_text(e, "ko")
                   for e in g["edges"] if e["kind"] == "tie")

    # Archive round-trip preserves address_condition losslessly
    arc = tmp_path / f"cond{archive.SUFFIX}"
    archive.export_file(migrated, str(arc))
    assert read_archive(arc.read_bytes())[0]["schema"]["level"] == LATEST >= "0040_address_condition.sql"
    restored_db = database_url_factory()
    archive.restore_file(restored_db, str(arc))
    q = "SELECT value, address_condition FROM assertion WHERE predicate = 'addresses' ORDER BY id"
    with psycopg.connect(migrated, row_factory=dict_row) as a, psycopg.connect(restored_db, row_factory=dict_row) as b:
        assert a.execute(q).fetchall() == b.execute(q).fetchall()
        assert len(b.execute(q).fetchall()) == 2


def test_canon_v2_extracts_reuses_and_folds_with_story_and_locks(migrated: str, db: psycopg.Connection):
    card_desc = "평소 공적인 자리에서는 하나가 도윤에게 존댓말로 과장님이라 부르고, 둘만 있을 때는 반말로 오빠라고 부른다."

    def model(system: str, user: str) -> tuple[dict[str, Any], str, dict[str, int]]:
        if "CANON" in system:
            if "과장님" in user:
                return {"assertions": [
                    addr("하나", "도윤", "존댓말, '과장님'", {"scope": "public", "when": "공적인 자리"},
                         evidence="공적인 자리에서는 하나가 도윤에게 존댓말로 과장님이라 부르고"),
                    addr("하나", "도윤", "반말, '오빠'", {"scope": "private", "when": "둘만 있을 때"},
                         evidence="둘만 있을 때는 반말로 오빠라고 부른다"),
                    # `all` from canon must normalize to None (baseline)
                    addr("도윤", "하나", "반말, '하나야'", {"scope": "all", "when": None},
                         evidence="하나가 도윤에게"),
                ]}, "{}", USED
            return {"assertions": []}, "{}", USED
        target = user.split("TARGET turn", 1)[1] if "TARGET turn" in user else ""
        if "자기야" in target:
            return {"assertions": [
                addr("하나", "도윤", "반말, '자기야'", {"scope": "private", "when": "둘만 있을 때"},
                     evidence="이제 둘만 있을 땐 자기야라고 불러"),
            ]}, "{}", USED
        if "팀장님" in target:
            return {"assertions": [
                addr("하나", "도윤", "존댓말, '팀장님'", {"scope": "public", "when": "회사에서"},
                     evidence="이제 회사에선 팀장님으로 불러"),
            ]}, "{}", USED
        return {"assertions": []}, "{}", USED

    chat1 = SimChat("canon-cond-1")
    chat1.user("둘이 있을 때 이야기한다.")
    chat1.reply("도윤이 속삭였다. \"이제 둘만 있을 땐 자기야라고 불러.\"")
    chat1.user("다음.")
    chat1.reply("하나는 웃으며 고개를 끄덕였다.")

    chat2 = SimChat("canon-cond-2")
    chat2.user("시작.")
    chat2.reply("평범한 아침이었다.")

    calls = {"canon": 0}

    def counting_model(system: str, user: str):
        if "CANON" in system:
            calls["canon"] += 1
        return model(system, user)

    with make_client(migrated, **LLM, extract_compiler="extract-v20", canon_facts=True) as c:
        sync(c, chat1)
        push_canon(c, chat1, {"card:name": ("하나", {"field": "name"}), "card:desc": (card_desc, {"field": "desc"})})
        drain_canon(migrated, counting_model)
        first_canon_calls = calls["canon"]
        assert first_canon_calls >= 1

        # Second chat with identical canon reuses the read and copies `address_condition` (Phase 57 A1)
        sync(c, chat2)
        push_canon(c, chat2, {"card:name": ("하나", {"field": "name"}), "card:desc": (card_desc, {"field": "desc"})})
        drain_canon(migrated, counting_model)
        assert calls["canon"] == first_canon_calls  # zero extra canon model calls

        cid1, cid2 = conv_id(c, chat1), conv_id(c, chat2)
        cg = active_generation(db, "canon")
        assert cg.spec["version"] == "canon-v2"
        ex = active_generation(db, "extract")

        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            h1 = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (cid1,)).fetchone()["head_commit_id"]
            h2 = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (cid2,)).fetchone()["head_commit_id"]
            v1 = facts.memory_view(conn, h1, ex.key, canon_key=cg.key)
            v2 = facts.memory_view(conn, h2, ex.key, canon_key=cg.key)

        # Chat 2 got copied conditional canon addresses, and canon `all` degraded to None
        v2_addrs = {(f["subject"], P.address_slot(f), f["value"], f.get("address_condition") is None)
                    for f in v2["facts"] if f["predicate"] == "addresses"}
        assert ("하나", ("public",), "존댓말, '과장님'", False) in v2_addrs
        assert ("하나", ("private",), "반말, '오빠'", False) in v2_addrs
        assert ("도윤", ("default",), "반말, '하나야'", True) in v2_addrs

        # Chat 1 updated only `private` -> canon's `public` stays intact & `notes.changes()` reports ONLY `private`!
        v1_hana = {P.address_slot(f): f for f in v1["facts"] if f["predicate"] == "addresses" and f["subject"] == "하나"}
        assert v1_hana[("public",)]["value"] == "존댓말, '과장님'" and v1_hana[("public",)].get("canon")
        assert v1_hana[("private",)]["value"] == "반말, '자기야'" and not v1_hana[("private",)].get("canon")
        changed = notes.changed_lines(v1["facts"])
        assert any("[둘만 있을 때]" in line and "오빠" in line and "자기야" in line for line in changed)
        assert not any("과장님" in line for line in changed)

        # Lock canon's `public` address, then add a story turn changing `public` -> lock holds off `public` only!
        pub_fact = v1_hana[("public",)]
        locked = c.post(f"/v1/conversations/{cid1}/repairs", json={"kind": "fact_lock", "item": str(pub_fact["id"])})
        assert locked.status_code == 200 and locked.json()["applied"], locked.text

        chat1.user("회사에서 승진했다.")
        chat1.reply("도윤이 말했다. \"이제 회사에선 팀장님으로 불러.\"")
        chat1.user("다음.")
        chat1.reply("알겠다고 답했다.")
        sync(c, chat1)
        drain_canon(migrated, counting_model)

        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            h1 = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (cid1,)).fetchone()["head_commit_id"]
            v1_after = facts.memory_view(conn, h1, ex.key, canon_key=cg.key)
        v1_hana_after = {P.address_slot(f): f for f in v1_after["facts"]
                         if f["predicate"] == "addresses" and f["subject"] == "하나"}
        assert v1_hana_after[("public",)]["value"] == "존댓말, '과장님'" and v1_hana_after[("public",)].get("locked")
        assert v1_hana_after[("private",)]["value"] == "반말, '자기야'"  # lock on public did NOT block private
        assert any(cf["kind"] == "locked" and cf["against"]["value"] == "존댓말, '팀장님'" for cf in v1_after["conflicts"])


def test_same_turn_retract_dropped_restore_and_carry_preserve_address_condition(migrated: str, db: psycopg.Connection):
    chat = SimChat("cond-repair-src")
    chat.user("호칭을 정했다.")
    chat.reply("회사에선 과장님, 둘만 있을 땐 오빠라고 부르기로 했다.")
    chat.user("다음.")
    chat.reply("하루가 지났다.")

    both = [
        addr("하나", "도윤", "존댓말, '과장님'", {"scope": "public", "when": "공적인 자리"}, evidence="회사에선 과장님"),
        addr("하나", "도윤", "반말, '오빠'", {"scope": "private", "when": "둘만 있을 때"}, evidence="둘만 있을 땐 오빠"),
    ]
    only_pub = [both[0]]

    def emit(rows_to_emit):
        def fn(system: str, user: str):
            target = user.split("TARGET turn", 1)[1] if "TARGET turn" in user else ""
            return {"assertions": rows_to_emit if "과장님" in target else []}, "{}", USED
        return fn

    with make_client(migrated, **LLM, extract_compiler="extract-v20", packet_policy="packet-v20") as c:
        sync(c, chat)
        drain(migrated, emit(both))
        cid = conv_id(c, chat)
        ex = active_generation(db, "extract")

        # 1. Carry link (`continue`) preserves `address_condition` into a new chat
        target_chat = SimChat("cond-repair-dst")
        target_chat.user("새 이야기 시작.")
        target_chat.reply("하나는 도윤을 다시 만났다.")
        sync(c, target_chat)
        dst_id = conv_id(c, target_chat)
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            made = carry.link(conn, dst_id, cid, "continue", None, carry.Keys(extractor=ex.key))
            dst_head = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (dst_id,)).fetchone()["head_commit_id"]
            loaded = carry.target_rows(carry.in_force(conn, dst_id))
            carried_view = facts.memory_view(conn, dst_head, ex.key, carried=loaded)
        assert made["link"]["id"]
        carried_slots = {P.address_slot(f): f["value"] for f in carried_view["facts"] if f["predicate"] == "addresses"}
        assert carried_slots == {("public",): "존댓말, '과장님'", ("private",): "반말, '오빠'"}

        # 2. Same-turn retract of `private` leaves `public` untouched
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            head = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (cid,)).fetchone()["head_commit_id"]
            v = facts.memory_view(conn, head, ex.key)
        priv_row = next(f for f in v["facts"] if f["predicate"] == "addresses" and P.address_slot(f) == ("private",))
        ret = c.post(f"/v1/conversations/{cid}/repairs", json={"kind": "fact_retract", "item": str(priv_row["id"])})
        assert ret.status_code == 200 and ret.json()["applied"]
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            v_after = facts.memory_view(conn, head, ex.key)
        assert {P.address_slot(f) for f in v_after["facts"] if f["predicate"] == "addresses"} == {("public",)}
        # Undo retraction before testing rebuild/dropped restore
        c.post(f"/v1/conversations/{cid}/repairs/{ret.json()['repair']['id']}/remove")

        # 3. Rebuild that drops `private` while keeping `public` is detected by `dropped.find` and restored with condition
        c.post(f"/v1/conversations/{cid}/rebuild")
        drain(migrated, emit(only_pub))
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            v_rebuilt = facts.memory_view(conn, head, ex.key)
            lost = dropped.find(conn, head, ex.key, v_rebuilt)
        assert len(lost) == 1 and lost[0]["address_condition"] == {"scope": "private", "when": "둘만 있을 때"}
        rest = c.post(f"/v1/conversations/{cid}/repairs", json={"kind": "fact_restore", "item": str(lost[0]["id"])})
        assert rest.status_code == 200 and rest.json()["applied"]
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            v_restored = facts.memory_view(conn, head, ex.key)
        restored_slots = {P.address_slot(f): f["value"] for f in v_restored["facts"] if f["predicate"] == "addresses"}
        assert restored_slots == {("public",): "존댓말, '과장님'", ("private",): "반말, '오빠'"}
