"""Tier 3 / PHASE-64 part 1: migration 0040, the full typed ontology of `extract-v20` and its compiler.

Pins that every earlier compiler (`extract-v15`..`extract-v19`) keeps its generation key, prompt and registry byte for
byte; checks migration 0040's columns and constraints, the ontology's predicates and validators (`condition`, `guise`,
`item_kind`, `knowledge_scope`, the wider `because` and `when_happened`), the composed `SYSTEM_V20` prompt, the
storage of the four marks, the tail-preserving CONTEXT cut, the hint lists ranked by the TARGET turn, solo secrets,
carried rows, and the carry-on switch to `extract-v20` (`generations.ADDS`). Stub models only; synthetic names only."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import make_client
from nmos_sidecar import extraction as X, generations, predicates as P, reveals, canonfacts, summaries
from nmos_sidecar.config import Settings
from nmos_sidecar.worker import run_once
from simchat import SimChat
from test_generations import LLM, conv_id
from test_phase61_pins import BASE
from test_semantics import row
from test_sidecar_integration import sync

V20 = "extract-v20"
EARLIER = ("extract-v15", "extract-v16", "extract-v17", "extract-v18", "extract-v19")
CONV = UUID("01900000-0000-7000-8000-0000000000e2")
CHAR = {"subject_type": "character", "object_type": "character"}
MIGRATION = Path(__file__).resolve().parents[3] / "migrations" / "0040_extract_v20_ontology.sql"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def ctx(text: str, turn: int = 20, persona: str | None = None, context: list[str] | None = None) -> dict:
    return {"target": {"conversation_id": CONV, "host_persona_name": persona, "links": (), "splits": (), "canon": (),
                       "turn": turn, "commit_id": None},
            "context": [{"metadata": {"role": "user"}, "content": c, "turn": turn - 1, "position": 0}
                        for c in context or ()],
            "members": [{"metadata": {"role": "user"}, "content": text, "turn": turn, "position": 1}]}


# --- earlier compilers: byte-identical -------------------------------------------------------------------------------

# Captured at aa331c1 (Wave 1 HEAD), before any extract-v20 change.
GOLDEN_KEYS = {
    "extract-v15": "extract-8ed39e6a2cf25ffae903b29d7ac9acd9",
    "extract-v16": "extract-029fac9f22f705a5130c70505c98ba49",
    "extract-v17": "extract-c98f66fc178127c0e3126c8503e4b8e9",
    "extract-v18": "extract-15d6e23accadb12ba64df5040859fc22",
    "extract-v19": "extract-aa30ae15592772fe3e31d5aa5a571dc5",
}
GOLDEN_PROMPTS = {  # (prompt_of roles, prompt_of no roles, registry_prompt, _prompt_print)
    "extract-v15": ("4adc94dedbe8d6c5", "4adc94dedbe8d6c5", "9cd5747815110702", "4adc94dedbe8d6c5"),
    "extract-v16": ("a6fec3fe3aabc852", "bf18ec1172bd61ab", "9cd5747815110702", "a6fec3fe3aabc852"),
    "extract-v17": ("1b054eef6b3891eb", "654dd7bfe18349a7", "9cd5747815110702", "1b054eef6b3891eb"),
    "extract-v18": ("a135aa624feace96", "49e63c4d20e13c17", "9cd5747815110702", "a135aa624feace96"),
    "extract-v19": ("64cf949b8bb6ffba", "19afa2351ca1bcb4", "f0b9fffe030c3183", "eba567531358fba0"),
}
GOLDEN_OTHER = {"reveal": "reveal-9b682161681128f8a06f7db566d54899", "canon": "canon-5fb6b7fb622106e4949b20ab6e422366",
                "summarize": "summarize-9ff98c40c22744e5ec947542b77f9125"}


@pytest.mark.parametrize("compiler", EARLIER)
def test_an_earlier_compilers_key_prompt_and_registry_are_byte_identical(compiler):
    assert X.extractor(Settings(**BASE, extract_compiler=compiler)).key == GOLDEN_KEYS[compiler]
    assert (sha(X.prompt_of(compiler, True)), sha(X.prompt_of(compiler, False)),
            sha(P.registry_prompt(compiler=compiler)), X._prompt_print(compiler)) == GOLDEN_PROMPTS[compiler]
    assert set(P.registry_for(compiler)) & P.V20_PREDICATES == set()


def test_the_registry_and_the_other_workers_keys_are_unchanged():
    assert sha(repr(sorted(P.REGISTRY.items()))) == "ec86a5ac4362f77d"
    assert P.EXTENSIONS["extract-v19"] == {"told": P.TOLD}
    assert P.REGISTRY["role_toward"].subject_types == ("character",)
    assert P.REGISTRY["promised"].object_types == ("character",)
    settings = Settings(**BASE)
    assert {"reveal": reveals.generation(settings).key, "canon": canonfacts.generation(settings).key,
            "summarize": summaries.summarizer(settings).key} == GOLDEN_OTHER


def test_v20_is_not_selectable_by_the_settings_yet_but_builds_from_its_name():
    assert V20 not in X.COMPILERS  # the settings accept exactly COMPILERS (test_extract_v16); config is a later part
    with pytest.raises(ValueError, match="NMOS_EXTRACT_COMPILER"):
        Settings(**BASE, extract_compiler=V20)
    gen = X.extractor(Settings(**BASE), V20)
    assert gen.spec["compiler"] == V20 and gen.key not in GOLDEN_KEYS.values()


# --- migration 0040 --------------------------------------------------------------------------------------------------

def test_migration_0040_adds_four_nullable_columns_with_checks(migrated, db):
    cols = {r["column_name"]: (r["data_type"], r["is_nullable"]) for r in db.execute(
        "SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_schema = 'public'"
        " AND table_name = 'assertion' AND column_name = ANY(%s)", (list(X.ONTOLOGY_COLUMNS),)).fetchall()}
    assert cols == {"condition": ("jsonb", "YES"), "guise": ("text", "YES"), "item_kind": ("text", "YES"),
                    "knowledge_scope": ("text", "YES")}
    assert X.ASSERTION_COLUMNS[-4:] == X.ONTOLOGY_COLUMNS and "condition" in X.JSON_COLUMNS


BAD = [("item_kind", "rare"), ("knowledge_scope", "public_except_maybe"), ("knowledge_scope", "secret"),
       ("guise", ""), ("guise", "가" * 81), ("condition", '["in_public"]'), ("condition", '"x"'),
       ("condition", json.dumps({"when": "가" * 400}, ensure_ascii=False))]
GOOD = [("item_kind", "unique"), ("item_kind", "fungible"), ("knowledge_scope", "public_except"), ("guise", "카이"),
        ("guise", "가" * 80), ("condition", '{"in_public": false}'), ("knowledge_scope", None), ("condition", None)]


def check_constraints(url: str) -> None:
    """Each bad value is refused and each good one kept, on a stored assertion row; then 0040 runs again cleanly."""
    with psycopg.connect(url, row_factory=dict_row, autocommit=True) as conn:
        row_id = conn.execute("SELECT id FROM assertion ORDER BY id LIMIT 1").fetchone()["id"]
        for column, bad in BAD:
            cast = "jsonb" if column == "condition" else "text"
            with pytest.raises(psycopg.errors.CheckViolation):
                with conn.transaction():
                    conn.execute(f"UPDATE assertion SET {column} = %s::{cast} WHERE id = %s", (bad, row_id))
        for column, good in GOOD:
            cast = "jsonb" if column == "condition" else "text"
            conn.execute(f"UPDATE assertion SET {column} = %s::{cast} WHERE id = %s", (good, row_id))
        conn.execute(MIGRATION.read_text())  # idempotent: each ADD COLUMN IF NOT EXISTS skips, with its CHECK
        n = conn.execute("SELECT count(*) AS n FROM pg_constraint WHERE conrelid = 'assertion'::regclass"
                         " AND contype = 'c' AND pg_get_constraintdef(oid) ~ '(condition|guise|item_kind|knowledge_scope)'"
                         ).fetchone()["n"]
        assert n == 4


# --- the ontology ----------------------------------------------------------------------------------------------------

def item(predicate: str, **kw: Any) -> dict[str, Any]:
    return {"subject": "하나", "subject_type": "character", "predicate": predicate, **kw}


def test_v20_registry_has_the_ontology_and_the_widened_predicates():
    reg = P.registry_for(V20)
    assert P.V20_PREDICATES == {"vital_status", "lives_in", "cover_identity", "disguised_as", "holds_rank",
                                "contained_in", "believes", "forgot"}
    assert P.V20_PREDICATES | {"told", "role_toward", "promised"} == P.ONTOLOGY_PREDICATES <= set(reg)
    assert reg["told"] is P.TOLD and P.EXTENSION_PARTICIPANTS[V20] == {"told"}
    spec = {n: (p.subject_types, p.object_types, p.cardinality, p.needs_value, p.per_object) for n, p in reg.items()}
    assert spec["vital_status"] == (("character",), None, "single", True, False)
    assert spec["lives_in"] == (("character", "group"), ("place",), "single", False, False)
    assert spec["cover_identity"] == (("character",), None, "multi", True, False)
    assert spec["disguised_as"] == (("character",), ("character",), "single", False, False)
    assert spec["holds_rank"] == (("character",), ("group",), "single", True, True)
    assert spec["contained_in"] == (("item", "place"), ("item", "place"), "single", False, False)
    assert spec["believes"] == (("character",), None, "multi", True, False)
    assert spec["forgot"] == (("character",), None, "multi", True, False)
    assert spec["role_toward"] == (("character", "group"), ("character", "group"), "single", True, True)
    assert spec["promised"] == (("character", "group"), ("character", "group"), "multi", True, False)
    text = P.registry_prompt(compiler=V20)
    assert all(f"- {name} (" in text for name in P.ONTOLOGY_PREDICATES)
    assert "- role_toward (subject: character|group, object: character|group" in text


def test_a_group_role_or_promise_validates_in_v20_only():
    guild = {"subject": "백은 길드", "subject_type": "group", "object": "하나", "object_type": "character",
             "value": "고용주"}
    for predicate in ("role_toward", "promised"):
        assert P.validate({**guild, "predicate": predicate}, P.registry_for(V20)) == ("valid", None)
        assert P.validate({**guild, "predicate": predicate}, P.registry_for("extract-v19"))[0] == "pending"
    assert P.validate(item("vital_status", value="사망"), P.registry_for("extract-v19")) == ("pending",
                                                                                          "unknown predicate")
    assert P.validate(item("holds_rank", object="백은 길드", object_type="group", value="부길드장"),
                      P.registry_for(V20)) == ("valid", None)
    assert P.validate({"subject": "부엌", "subject_type": "place", "predicate": "contained_in",
                       "object": "카이토의 저택", "object_type": "place"}, P.registry_for(V20)) == ("valid", None)


def test_a_guise_keeps_its_optional_note_and_valueless_v20_predicates_drop_theirs():
    reg = P.registry_for(V20)
    assert P.takes_value("disguised_as", reg) and not P.takes_value("lives_in", reg)
    assert not P.takes_value("contained_in", reg) and P.takes_value("vital_status", reg)
    assert not P.takes_value("located_in") and not P.takes_value("located_in", reg)  # unchanged for REGISTRY's


def test_condition_keeps_only_its_known_keys():
    raw = {"in_public": True, "audience": ["상사", {"name": "귀족"}, "상사", "", None, 3], "as_guise": " 카이 ",
           "when": "변장 중", "mood": "x", "in_private": True}
    assert P.condition(item("addresses", condition=raw)) == {"in_public": True, "audience": ["상사", "귀족"],
                                                              "as_guise": "카이", "when": "변장 중"}
    assert P.condition(item("addresses", condition={"in_public": "true"})) is None  # a JSON boolean only
    assert P.condition(item("addresses", condition={"in_public": False})) == {"in_public": False}
    assert P.condition(item("addresses", condition={"when": "null", "audience": []})) is None
    assert P.condition(item("addresses", condition="공석에서")) is None
    assert P.condition(item("event", condition={"in_public": True})) is None  # not a conditioned predicate
    assert {p for p in P.REGISTRY | P.registry_for(V20)
            if P.condition(item(p, condition={"in_public": True}))} == P.CONDITIONED_PREDICATES


def test_condition_is_capped_in_count_length_and_bytes():
    names = [f"{'귀족가문의대리인' * 12}{i}" for i in range(12)]
    out = P.condition(item("relationship", condition={"audience": names, "as_guise": "가" * 200, "when": "나" * 300}))
    assert len(json.dumps(out, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()) <= 512
    assert 1 <= len(out["audience"]) <= P.AUDIENCE_MAX and all(len(n) <= 80 for n in out["audience"])
    assert len(out["as_guise"]) <= 80 and 1 <= len(out["when"]) <= 120
    small = P.condition(item("relationship", condition={"audience": [f"n{i}" for i in range(20)]}))
    assert small == {"audience": [f"n{i}" for i in range(8)]}


def test_guise_item_kind_and_the_four_way_knowledge_scope():
    assert P.guise(item("feels_toward", guise=" 카이 ")) == "카이"
    assert P.guise(item("addresses", condition={"as_guise": "카이"})) == "카이"
    assert P.guise(item("event", guise="none")) is None and P.guise(item("event", guise="가" * 90)) == "가" * 80
    assert P.item_kind(item("possesses", object="물약", object_type="item", item_kind="Fungible")) == "fungible"
    assert P.item_kind({"subject": "열쇠", "subject_type": "item", "predicate": "contained_in",
                        "item_kind": "unique"}) == "unique"
    assert P.item_kind(item("located_in", item_kind="unique")) is None  # a character's whereabouts
    assert P.item_kind({"subject": "부엌", "subject_type": "place", "predicate": "contained_in",
                        "item_kind": "unique"}) is None
    assert P.item_kind(item("possesses", item_kind="rare")) is None
    hidden = item("knows", value="v", knowledge="public_except", hidden_from=["카이토"])
    assert P.knowledge(hidden)[0] == "limited" and P.knowledge_scope(hidden) == "public_except"
    assert P.knowledge_scope({**hidden, "knowledge": "public"}) == "public_except"
    assert P.knowledge_scope({**hidden, "hidden_from": []}) == P.knowledge({**hidden, "hidden_from": []})[0] == "unknown"
    contradicted = {**hidden, "known_by": ["카이토"]}  # both lists: unknown awareness, nobody kept out
    assert P.knowledge_scope(contradicted) == P.knowledge(contradicted)[0] == "unknown"
    assert P.knowledge_scope(item("knows", knowledge="limited", known_by=["하나"])) == "limited"
    assert P.knowledge_scope(item("knows", knowledge="whatever")) == "unknown"
    assert P.knowledge_scope(item("knows", knowledge="public")) == "public"
    for raw in (hidden, contradicted, item("knows", knowledge="public", known_by=["하나"])):  # never contradicts
        scope = P.knowledge_scope(raw)
        assert P.knowledge(raw)[0] == ("limited" if scope == "public_except" else scope)


def test_because_and_when_happened_reach_more_predicates_in_v20_only():
    for predicate in P.V20_TIMED:
        raw = item(predicate, because="빚 때문에", when_happened="3년 전 겨울")
        assert P.because(raw, V20) == "빚 때문에" and P.when_happened(raw, 80, V20) == "3년 전 겨울"
        assert P.because(raw, "extract-v19") == P.because(raw) == (
            "빚 때문에" if predicate in P.CAUSED else None)
        assert P.when_happened(raw, 80, "extract-v19") == (
            "3년 전 겨울" if predicate in P.HAPPENED_PREDICATES else None)
    assert P.CAUSED == {"event", "feels_toward", "relationship", "has_status", "goal"}


# --- the prompt ------------------------------------------------------------------------------------------------------

def test_v20_prompt_unifies_v17_v19_and_the_ontology_rule():
    v19, v20 = X.prompt_of("extract-v19"), X.prompt_of(V20)
    assert v20 == X.PROMPTS[V20] == X.SYSTEM_V20_ROLES == X._v20(X.SYSTEM_V16_ROLES)
    assert X.prompt_of(V20, roles=False) == X.SYSTEM_V20 and X.ROLE_ENDINGS not in X.SYSTEM_V20
    for part in (X.HORIZON_RULE, X.FEELING_RULE, X.TOLD_RULE, X.V20_ONTOLOGY_RULE, X._HORIZON_ANSWER,
                 X._SPEAKERS_ANSWER, X._BECAUSE_V20, X._HAPPENED_V20, X._ONTOLOGY_ANSWER, X._KNOWLEDGE_ANSWER_V20,
                 X._FOUND_OUT_V20, X.ROLE_ENDINGS, X.ALIAS_RULE):
        assert v20.count(part) == 1, part[:60]
    for part in (X.V20_ONTOLOGY_RULE, X._BECAUSE_V20, X._ONTOLOGY_ANSWER, X._KNOWLEDGE_ANSWER_V20):
        assert part not in v19
    assert X._BECAUSE_V19 not in v20 and X._HAPPENED_ANSWER_V19 not in v20
    rule = X.V20_ONTOLOGY_RULE
    assert "과장님" in rule and "오빠" in rule and '"in_public": false' in rule
    for word in ("vital_status", "has_status", "lives_in", "located_in", "cover_identity", "disguised_as",
                 "hidden_from", "holds_rank", "contained_in", '"fungible"', '"unique"', "believes", "forgot",
                 '"public_except"', "`guise`"):
        assert word in rule, word
    for system in (X.SYSTEM_V20, X.SYSTEM_V20_ROLES):
        filled = system.format(registry=P.registry_prompt(compiler=V20))
        assert '"condition": {"in_public": true' in filled and "- vital_status (subject: character" in filled


def test_v20_sets_and_its_fingerprint():
    assert X.ONTOLOGY == {V20}
    for name in ("ROLES", "PARTS_APART", "HORIZONS", "SPEAKERS", "FEELINGS", "HAPPENED", "CONFIRMS"):
        assert V20 in getattr(X, name), name
    assert X.HORIZONS - X.ONTOLOGY == X.SPEAKERS - X.ONTOLOGY == {"extract-v17"}
    printed = X._prompt_print(V20)
    assert printed != generations.fingerprint(X.prompt_of(V20)) and printed != X._prompt_print("extract-v19")
    assert X.SPEAKER_RULE in X.ONTOLOGY_PRINT and str(P.CONDITION_MAX_BYTES) in X.ONTOLOGY_PRINT


def test_v20_build_prompt_lists_quoted_lines_and_reads_the_clock():
    c = ctx('하나가 말했다. "내일 다시 오세요."')
    prompt = X.build_prompt(c, compiler=V20, clock="4월 12일")
    assert "QUOTED LINES of the TARGET turn:" in prompt and X.SPEAKER_RULE in prompt
    assert "STORY CLOCK at the TARGET turn" in prompt
    assert "QUOTED LINES" not in X.build_prompt(c, compiler="extract-v19")


def test_a_long_context_message_keeps_its_end_in_v20_only():
    long = "가" * 400 + "중간" * 500 + "그는 그녀에게 열쇠를 건넸다"
    shown = X.context_text(long, V20)
    assert shown.startswith("가" * 300) and shown.endswith(long[-700:]) and X.CONTEXT_GAP in shown
    assert len(shown) == 300 + len(X.CONTEXT_GAP) + 700
    assert X.context_text(long, "extract-v19") == X.context_text(long) == long[:1000]
    assert X.context_text("짧다", V20) == "짧다" and X.context_text("가" * 1000, V20) == "가" * 1000
    assert "열쇠를 건넸다" in X.build_prompt(ctx("t", context=[long]), compiler=V20)
    assert "열쇠를 건넸다" not in X.build_prompt(ctx("t", context=[long]), compiler="extract-v19")


# --- storage ---------------------------------------------------------------------------------------------------------

def raw_items() -> list[dict[str, Any]]:
    return [
        {"subject": "하나", "subject_type": "character", "predicate": "addresses", "object": "카이토",
         "object_type": "character", "value": "존댓말, '과장님'이라고 부름", "modality": "actual",
         "condition": {"in_public": True, "audience": ["회사 동료"], "junk": 1}, "evidence": "과장님"},
        {"subject": "하나", "subject_type": "character", "predicate": "disguised_as", "object": "카이",
         "object_type": "character", "value": "남장", "modality": "actual", "knowledge": "public_except",
         "hidden_from": ["카이토"]},
        {"subject": "하나", "subject_type": "character", "predicate": "possesses", "object": "회복 물약",
         "object_type": "item", "item_kind": "fungible", "modality": "actual"},
        {"subject": "카이토", "subject_type": "character", "predicate": "feels_toward", "object": "하나",
         "object_type": "character", "value": "호감", "guise": "카이", "modality": "actual",
         "feeling": {"intensity": "clear", "valence": "positive"}},
        {"subject": "하나", "subject_type": "character", "predicate": "vital_status", "value": "실종",
         "modality": "actual", "because": "폭풍 때문에", "when_happened": "3년 전"},
    ]


def test_v20_rows_carry_the_four_marks_and_earlier_rows_do_not():
    turn = "과장님 하나는 카이로 변장했다 회복 물약 카이 호감 실종"
    rows = X.normalize(raw_items(), turn, compiler=V20, feelings=True)
    by = {r["predicate"]: r for r in rows}
    assert all(r["status"] == "valid" for r in rows), [r["reason"] for r in rows]
    assert by["addresses"]["condition"] == {"in_public": True, "audience": ["회사 동료"]}
    assert by["disguised_as"]["value"] == "남장" and by["disguised_as"]["knowledge"] == "limited"
    assert by["disguised_as"]["knowledge_scope"] == "public_except" and by["disguised_as"]["hidden_from"] == ["카이토"]
    assert by["possesses"]["item_kind"] == "fungible" and by["feels_toward"]["guise"] == "카이"
    assert by["vital_status"]["because"] == "폭풍 때문에" and by["vital_status"]["when_happened"] == "3년 전"
    assert {r["knowledge_scope"] for r in rows} <= set(P.KNOWLEDGE_SCOPES_V20)
    values = X.assertion_values(by["addresses"])
    assert len(values) == len(X.ASSERTION_COLUMNS)
    for compiler in EARLIER:
        old = X.normalize(raw_items(), turn, compiler=compiler)
        assert all(not set(X.ONTOLOGY_COLUMNS) & set(r) for r in old)
        assert all(v is None for v in X.assertion_values(old[0])[-4:])


# --- hint lists ------------------------------------------------------------------------------------------------------

def promises(n: int) -> list[dict[str, Any]]:
    out = [row(1, "하나", "promised", "카이토", "등대 열쇠를 돌려주겠다", turn_hash="h1", **CHAR)]
    out += [row(i, "하나", "promised", "카이토", f"사소한 약속 {i}번째", turn_hash=f"h{i}", **CHAR)
            for i in range(2, n + 1)]
    return out


def test_an_old_promise_the_turn_is_about_is_never_cut_past_eight():
    rows = promises(12)
    text = "하나는 카이토에게 등대 열쇠를 돌려주겠다고 했던 약속을 떠올렸다."
    default = X.promise_hints(ctx(text), rows)
    assert len(default) == 8 and "등대 열쇠를 돌려주겠다" not in [p["text"] for p in default]  # newest first, as before
    ranked = X.promise_hints(ctx(text), rows, turn_text=text)
    assert ranked[0]["text"] == "등대 열쇠를 돌려주겠다" and len(ranked) == 8
    assert [p["text"] for p in ranked[1:]] == [p["text"] for p in default[:7]]


def secret(pos: int, value: str, **marks: Any) -> dict[str, Any]:
    return row(pos, "하나", "knows", value=value, subject_type="character", turn_hash=f"h{pos}",
               knowledge="limited", **marks)


def test_an_old_secret_the_turn_is_about_ranks_first_and_defaults_are_unchanged():
    rows = [secret(1, "지하실 열쇠는 하나가 숨겼다", known_by=["하나"], hidden_from=["카이토"])]
    rows += [secret(i, f"다른 비밀 {i}", known_by=["하나"], hidden_from=["카이토"]) for i in range(2, 12)]
    text = "카이토는 지하실 열쇠는 누가 숨겼는지 물었다."
    default = X.secret_hints(ctx(text), rows)
    assert len(default) == 8 and all("지하실" not in s["text"] for s in default)
    ranked = X.secret_hints(ctx(text), rows, turn_text=text)
    assert "지하실 열쇠" in ranked[0]["text"] and len(ranked) == 8 and not any(s.get("solo") for s in ranked)


def test_a_solo_secret_is_listed_and_can_be_found_out_in_v20():
    solo = secret(3, "하나는 카이토를 좋아한다", known_by=["하나"])
    text = "하나가 카이토를 좋아한다는 걸 유이가 눈치챘다."
    assert X.secret_hints(ctx(text), [solo]) == [] == X.secret_hints(ctx(text), [solo], turn_text=text)
    (listed,) = X.secret_hints(ctx(text), [solo], turn_text=text, include_solo=True)
    assert listed["solo"] is True and listed["kept_from"] == [] and listed["holders"] == ["하나"]
    assert "kept from: everyone else" in "\n".join(X.secrets_block([listed]))
    answer = {"secrets": [{"secret": "S1", "found_out_by": ["유이", "하나"], "evidence": text}]}
    (learned,) = X.revealed(answer, [listed], text)
    assert learned["subject"] == "유이" and learned["value"] == f"[turn 3] {listed['text']}"
    # once found out (the worker's own reveal of it), it is not listed again
    later = row(5, "유이", "learned", value=learned["value"], subject_type="character")
    assert X.secret_hints(ctx(text, turn=9), [solo, later], turn_text=text, include_solo=True) == []
    # unrelated to the TARGET turn: not listed (a holder's every private feeling would flood the list)
    assert X.secret_hints(ctx("비가 왔다. 유이는 우산을 폈다."), [solo], turn_text="비가 왔다. 유이는 우산을 폈다.",
                          include_solo=True) == []
    named_only = "하나는 비를 맞으며 혼자 걸었다."  # its holder named, its words not: still not listed
    assert X.secret_hints(ctx(named_only), [solo], turn_text=named_only, include_solo=True) == []


def test_a_kept_from_secret_outranks_a_solo_one_of_the_same_rank():
    kept = secret(1, "하나는 카이토의 편지를 읽었다", known_by=["하나"], hidden_from=["카이토"])
    solo = secret(2, "하나는 카이토의 편지를 태웠다", known_by=["하나"])
    text = "하나는 카이토의 편지를 들고 있었다."
    listed = X.secret_hints(ctx(text), [kept, solo], turn_text=text, include_solo=True)
    assert [bool(s.get("solo")) for s in listed] == [False, True]


def test_roles_are_ranked_by_the_turn_in_v20():
    roles = [row(i, "하나", "role_toward", f"인물{i}", f"역할 {i}", turn_hash=f"h{i}", **CHAR) for i in range(1, 11)]
    roles[0] = row(1, "하나", "role_toward", "카이토", "하녀: 카이토의 저택에서 일하며 지냄", turn_hash="h1", **CHAR)
    text = "하나는 " + ", ".join(f"인물{i}" for i in range(1, 11)) + " 그리고 카이토의 저택에서 일하며 지냄을 떠올렸다."
    default = [r["to"] for r in X.role_hints(ctx(text), roles)]
    assert "카이토" not in default and len(default) == 8
    ranked = [r["to"] for r in X.role_hints(ctx(text), roles, turn_text=text)]
    assert ranked[0] == "카이토" and len(ranked) == 8


def carried_row(pos: int, subject: str, predicate: str, obj: str | None = None, value: str | None = None,
                **kw: Any) -> dict[str, Any]:
    return {**row(pos, subject, predicate, obj, value, **kw), "id": -pos, "position": -1000 + pos, "turn": -1,
            "turn_hash": "carried:L", "host_logical_id": "carried:L", "carried": "L"}


def test_carried_rows_enter_every_hint_list():
    text = "하나와 카이토는 유이를 다시 만났다."
    carried = [
        carried_row(1, "유이", "located_in", "등대", subject_type="character", object_type="place"),
        carried_row(2, "하나", "promised", "카이토", "등대에서 다시 만나겠다", **CHAR),
        carried_row(3, "카이토", "goal", value="잃어버린 배를 찾는다", subject_type="character"),
        carried_row(4, "하나", "knows", value="배는 가라앉았다", subject_type="character", knowledge="limited",
                    known_by=["하나"], hidden_from=["카이토"]),
        carried_row(5, "하나", "role_toward", "카이토", "조수", **CHAR),
    ]
    c = ctx(text)
    assert X.promise_hints(c, []) == [] and X.secret_hints(c, []) == [] and X.thread_hints(c, []) == []
    assert X.role_hints(c, []) == []
    assert [p["text"] for p in X.promise_hints(c, [], carried=carried)] == ["등대에서 다시 만나겠다"]
    assert [t["text"] for t in X.thread_hints(c, [], carried=carried)] == ["잃어버린 배를 찾는다"]
    assert [s["kept_from"] for s in X.secret_hints(c, [], carried=carried)] == [["카이토"]]
    assert [(r["by"], r["to"]) for r in X.role_hints(c, [], carried=carried)] == [("하나", "카이토")]
    names = {h["name"] for h in X.entity_hints(None, c, "k", 30, [], carried=carried)}
    assert {"유이", "등대", "카이토"} <= names
    assert carried[3]["hidden_from"] == ["카이토"] and "_kept" not in carried[3]  # the link's rows stay as they were


def test_carried_rows_come_from_a_continue_link_only(monkeypatch):
    from nmos_sidecar import carry

    fact = {"subject": "{{user}}", "subject_type": "character", "predicate": "located_in", "object": "등대",
            "object_type": "place", "polarity": "positive", "modality": "actual", "source": "narration",
            "knowledge": "limited", "known_by": ["{{user}}"], "hidden_from": None, "from": None}
    link = {"id": str(uuid4()), "source_conversation_id": str(uuid4()), "mode": "continue",
            "snapshot": {"facts": [fact], "threads": [], "aliases": []}}
    monkeypatch.setattr(carry, "in_force", lambda conn, target_id: link)
    (out,) = X.carried_rows(None, {"conversation_id": CONV, "host_persona_name": "타쿠미"})
    assert out["subject"] == "타쿠미" and out["turn"] == -1 and out["carried"] == link["id"]
    assert out["known_by"] == ["타쿠미"] and fact["known_by"] == ["{{user}}"]
    monkeypatch.setattr(carry, "in_force", lambda conn, target_id: {**link, "mode": "regression"})
    assert X.carried_rows(None, {"conversation_id": CONV, "host_persona_name": None}) == []
    monkeypatch.setattr(carry, "in_force", lambda conn, target_id: None)
    assert X.carried_rows(None, {"conversation_id": CONV}) == []


# --- carry-on switch and the worker ----------------------------------------------------------------------------------

def test_switching_to_v20_from_v16_v18_or_v19_is_carry_on(migrated, db):
    settings = Settings(**BASE)
    v20 = X.extractor(settings, V20)
    assert sorted(v20.spec) == sorted(X.extractor(Settings(**BASE, extract_compiler="extract-v19")).spec)
    for earlier, kind in (("extract-v16", "adds"), ("extract-v18", "adds"), ("extract-v19", "adds"),
                          ("extract-v17", "version"), ("extract-v15", "version")):
        prev = X.extractor(Settings(**BASE, extract_compiler=earlier))
        generations.ensure(db, prev)
        assert generations.classify(db, prev.key, v20) == kind, earlier
    v19 = X.extractor(Settings(**BASE, extract_compiler="extract-v19"))
    generations.ensure(db, v20)
    assert generations.classify(db, v20.key, v19) == "adds"
    moved = X.extractor(Settings(**(BASE | {"llm_model": "model-b"})), V20)
    assert generations.classify(db, v19.key, moved) == "model"
    assert generations.ADDS == {"extract-v16", "extract-v18", "extract-v19", "extract-v20"}


TURN = "회사에서 하나는 카이토에게 '과장님'이라고 불렀다. 하나는 회복 물약 세 병을 챙겼다."


def stub(seen: list[str]):
    def complete(system: str, user: str) -> tuple[dict, str, dict]:
        seen.append(system)
        if "과장님" not in user.split("TARGET turn", 1)[-1]:
            return {"assertions": []}, "{}", {"calls": 1}
        return {"assertions": [
            {"subject": "하나", "subject_type": "character", "predicate": "addresses", "object": "카이토",
             "object_type": "character", "value": "존댓말, '과장님'이라고 부름", "modality": "actual",
             "source": "narration", "condition": {"in_public": True, "audience": ["회사 동료"]},
             "evidence": "하나는 카이토에게 '과장님'이라고 불렀다", "knowledge": "public"},
            {"subject": "하나", "subject_type": "character", "predicate": "possesses", "object": "회복 물약",
             "object_type": "item", "modality": "actual", "source": "narration", "item_kind": "fungible",
             "evidence": "회복 물약 세 병을 챙겼다", "knowledge": "public_except", "hidden_from": ["카이토"]},
        ], "speakers": {}}, "{}", {"calls": 1}
    return complete


def test_the_v20_worker_stores_the_marks_and_the_migration_guards_them(migrated):
    chat = SimChat()
    chat.user("장면 0.")
    chat.reply(TURN)
    chat.user("다음.")
    chat.reply("잔잔한 오후였다.")
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        cid = conv_id(c, chat)
    seen: list[str] = []
    with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
        gen = X.extractor(Settings(database_url=migrated, **LLM), V20)
        previous = generations.activate(conn, gen)
        assert generations.classify(conn, previous, gen) == "adds"
        X.schedule_generation(conn, gen.key, 50)
        jobs = {"extract": (gen.key, lambda cn, job: X.process_extract(cn, job, stub(seen), gen,
                                                                         gen.spec["context_turns"]))}
        while run_once(conn, jobs):
            pass
        rows = conn.execute(
            "SELECT a.predicate, a.condition, a.guise, a.item_kind, a.knowledge, a.knowledge_scope, a.status"
            " FROM assertion a JOIN extraction x ON x.id = a.extraction_id WHERE x.extractor_key = %s"
            " ORDER BY a.id", (gen.key,)).fetchall()
        assert conn.execute("SELECT count(*) AS n FROM job WHERE status = 'dead'").fetchone()["n"] == 0
    check_constraints(migrated)
    assert seen and all(X.V20_ONTOLOGY_RULE.split("\n", 1)[0] in s for s in seen)
    by = {r["predicate"]: r for r in rows}
    assert by["addresses"]["condition"] == {"in_public": True, "audience": ["회사 동료"]}
    assert by["addresses"]["knowledge_scope"] == "public" and by["addresses"]["status"] == "valid"
    assert by["possesses"]["item_kind"] == "fungible" and by["possesses"]["knowledge"] == "limited"
    assert by["possesses"]["knowledge_scope"] == "public_except"
    assert UUID(cid)


# --- the ontology's own rows through the hint lists, repairs, reveals and role endings ------------------------------

def guise_rows() -> list[dict[str, Any]]:
    return [
        row(2, "하나", "disguised_as", "카이", "남장", turn_hash="h2", knowledge="limited", known_by=["하나"],
            hidden_from=["카이토"], **CHAR),
        row(3, "세라", "vital_status", value="실종", subject_type="character", turn_hash="h3"),
        row(4, "열쇠", "contained_in", "보석함", subject_type="item", object_type="item", turn_hash="h4"),
        row(5, "백은 길드", "role_toward", "하나", "고용주", subject_type="group", object_type="character",
            turn_hash="h5"),
    ]


@pytest.mark.parametrize("note", ["남장", None])
def test_a_guise_kept_from_someone_is_a_listed_secret_a_reveal_closes(note):
    from nmos_sidecar.secrets import fold

    rows = guise_rows()
    rows[0]["value"] = note
    text = "카이토는 카이가 하나라는 걸 알아챘다."
    (listed,) = X.secret_hints(ctx(text), rows, turn_text=text, include_solo=True)
    assert listed["text"].startswith("하나 disguised as 카이") and listed["kept_from"] == ["카이토"]
    answer = {"secrets": [{"secret": "S1", "found_out_by": ["카이토"], "evidence": text}]}
    (learned,) = X.revealed(answer, [listed], text)
    reveal = {**row(8, "카이토", "learned", value=learned["value"], subject_type="character"), "turn_hash": "h8"}
    for listed_hash in ("h2", None):  # rule 1 (the listed turn as it was) and rule 2 (a reworded re-extraction)
        secrets, unmatched, _ = fold([dict(r) for r in rows] + [{**reveal, "listed_hash": listed_hash}], None)
        assert [s["open"] for s in secrets] == [[]] and unmatched == []


def test_ontology_rows_pass_the_hint_lists_and_the_owners_repairs():
    from nmos_sidecar.repairs import fact_target
    from test_tier1_extraction_bugs import owner

    rows = guise_rows()
    text = "카이토와 백은 길드의 하나, 세라는 보석함 속 열쇠를 찾았다."
    names = [h["name"] for h in X.entity_hints(None, ctx(text), "k", 30, rows)]
    assert {"하나", "카이", "세라", "열쇠", "보석함", "백은 길드"} <= set(names)
    assert [s["kept_from"] for s in X.secret_hints(ctx(text), rows)] == [["카이토"]]
    retract = owner("fact_retract", fact_target(rows[0]), 6)
    c = ctx(text)
    c["target"]["repairs"] = [retract]
    assert X.secret_hints(c, rows, turn_text=text, include_solo=True) == []
    assert [(r["by"], r.get("by_type")) for r in X.role_hints(c, rows)] == [("백은 길드", "group")]


def test_a_listed_group_role_ends_as_the_same_role():
    from nmos_sidecar.facts import _versions

    roles = X.role_hints(ctx("하나는 백은 길드를 떠났다."), guise_rows(), turn_text="하나는 백은 길드를 떠났다.")
    assert roles == [{"by": "백은 길드", "to": "하나", "role": "고용주", "turn": 5, "knowledge": None, "known_by": None,
                      "hidden_from": None, "by_type": "group"}]
    text = "하나는 길드 계약서를 찢고 백은 길드를 영영 떠났다."
    answer = {"roles_ended": [{"role": "R1", "when": "now", "evidence": "하나는 길드 계약서를 찢고 백은 길드를 영영 떠났다"}]}
    (ending,) = X.ended_roles(answer, [], roles, text)
    assert (ending["subject_type"], ending["object_type"], ending["polarity"]) == ("group", "character", "negative")
    (stored,) = X.normalize([{k: v for k, v in ending.items() if k != "listed"}], text, compiler=V20)
    assert stored["status"] == "valid", stored["reason"]
    held = guise_rows()[3]
    closed = {**held, **{k: stored[k] for k in ("subject_type", "object_type", "value", "polarity")}, "id": 9,
              "position": 9, "turn": 9}
    assert [f["polarity"] for f in _versions([held, closed])] == ["negative"]
    # a character's role hint is as before: no type keys
    plain = X.role_hints(ctx("하나는 카이토를 만났다."), [row(1, "하나", "role_toward", "카이토", "조수", turn_hash="h1",
                                                            **CHAR)])
    assert set(plain[0]) == {"by", "to", "role", "turn", "knowledge", "known_by", "hidden_from"}


GUISE_TURN = "하나는 남장을 하고 카이라는 이름으로 백은 길드에 들어갔다. 세라는 실종됐고 열쇠는 보석함에 있다."
REVEAL_TURN = "카이토는 카이가 하나라는 걸 알아챘다."
LATER_TURN = "카이토와 카이는 길드 앞에서 하나의 이야기를 했다."


def multi_stub(prompts: dict[str, str]):
    def complete(system: str, user: str) -> tuple[dict, str, dict]:
        target = user.split("TARGET turn", 1)[-1]
        for key in ("guise", "reveal", "later"):
            if {"guise": GUISE_TURN, "reveal": REVEAL_TURN, "later": LATER_TURN}[key] in target:
                prompts[key] = user
        if GUISE_TURN in target:
            return {"assertions": [
                {"subject": "하나", "subject_type": "character", "predicate": "disguised_as", "object": "카이",
                 "object_type": "character", "value": "남장", "modality": "actual", "source": "narration",
                 "knowledge": "limited", "known_by": ["하나"], "hidden_from": ["카이토"],
                 "evidence": "하나는 남장을 하고 카이라는 이름으로"},
                {"subject": "세라", "subject_type": "character", "predicate": "vital_status", "value": "실종",
                 "modality": "actual", "source": "narration", "evidence": "세라는 실종됐고"},
                {"subject": "열쇠", "subject_type": "item", "predicate": "contained_in", "object": "보석함",
                 "object_type": "item", "item_kind": "unique", "modality": "actual", "source": "narration",
                 "evidence": "열쇠는 보석함에 있다"},
                {"subject": "백은 길드", "subject_type": "group", "predicate": "role_toward", "object": "하나",
                 "object_type": "character", "value": "고용주", "modality": "actual", "source": "narration",
                 "evidence": "백은 길드에 들어갔다"},
            ]}, "{}", {"calls": 1}
        if REVEAL_TURN in target and "disguised as" in user.split("TARGET turn", 1)[0]:
            return {"assertions": [], "secrets": [{"secret": "S1", "found_out_by": ["카이토"],
                                                    "evidence": REVEAL_TURN}]}, "{}", {"calls": 1}
        return {"assertions": []}, "{}", {"calls": 1}
    return complete


def test_the_v20_worker_lists_reveals_and_then_closes_a_guise_across_turns(migrated):
    chat = SimChat()
    for i, text in enumerate(("장면 0.", GUISE_TURN, REVEAL_TURN, LATER_TURN)):
        chat.user(f"계속 {i}.")
        chat.reply(text)
    chat.user("끝.")
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
    prompts: dict[str, str] = {}
    with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
        gen = X.extractor(Settings(database_url=migrated, **LLM), V20)
        generations.activate(conn, gen)
        X.schedule_generation(conn, gen.key, 50)
        jobs = {"extract": (gen.key, lambda cn, job: X.process_extract(cn, job, multi_stub(prompts), gen,
                                                                         gen.spec["context_turns"]))}
        while run_once(conn, jobs):
            pass
        stored = {r["predicate"]: r for r in conn.execute(
            "SELECT a.predicate, a.subject, a.subject_type, a.status, a.item_kind, a.knowledge_scope FROM assertion a"
            " JOIN extraction x ON x.id = a.extraction_id WHERE x.extractor_key = %s", (gen.key,)).fetchall()}
        hints = [r["hints"] for r in conn.execute(
            "SELECT x.hints FROM extraction x WHERE x.extractor_key = %s AND x.hints->'secrets' <> '[]'::jsonb",
            (gen.key,)).fetchall()]
        assert conn.execute("SELECT count(*) AS n FROM job WHERE status = 'dead'").fetchone()["n"] == 0
    assert {p: stored[p]["status"] for p in ("disguised_as", "vital_status", "contained_in", "role_toward",
                                             "learned")} == dict.fromkeys(
        ("disguised_as", "vital_status", "contained_in", "role_toward", "learned"), "valid")
    assert stored["learned"]["subject"] == "카이토" and stored["contained_in"]["item_kind"] == "unique"
    assert stored["role_toward"]["subject_type"] == "group"
    assert "S1. 하나 disguised as 카이: 남장" in prompts["reveal"] and "kept from: 카이토" in prompts["reveal"]
    assert "disguised as" not in prompts["later"].split("TARGET turn", 1)[0]  # found out: no longer listed
    assert "CURRENT ROLES" in prompts["reveal"] and "R1. 백은 길드 → 하나: 고용주" in prompts["reveal"]
    assert any(h["secrets"][0]["text"] == "하나 disguised as 카이: 남장" for h in hints)
