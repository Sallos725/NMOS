"""extract-v19 (PHASE-60 S7, S8, ADR 0086): the `told` per-compiler extension, prompt, generation key and settings.

Synthetic names only (세라, 카이토, 하나, 유나).
"""

from __future__ import annotations

import dataclasses
import hashlib

import pytest

from nmos_sidecar import entities, extraction as X, generations, predicates as P
from nmos_sidecar.config import Settings
from test_phase60_pins import BASE, PINNED_EXTRACT_SPEC_FIELDS

REGISTRY_PROMPT_SHA256 = "9cd57478151107025e53b7f29a38f5d7154ee57c66a5a92b8b3cfeb2e894084b"
REGISTRY_PROMPT_ONLY_SHA256 = "4eac87e6574ab18970f8c236a774a47c8eb9749c2699ef1a7f210c76a3d72c63"


def _told_item(**extra):
    return {
        "subject": "세라",
        "subject_type": "character",
        "predicate": "told",
        "object": "카이토",
        "object_type": "character",
        "value": "하나가 열쇠를 숨겼다는 사실",
        "with": [{"name": "하나", "type": "character"}],
        **extra,
    }


def test_told_extension_keeps_registry_and_default_prompt_unchanged():
    assert "told" not in P.REGISTRY
    assert P.EXTENSIONS == {"extract-v19": {"told": P.TOLD}}
    assert P.EXTENSION_PARTICIPANTS == {"extract-v19": frozenset({"told"})}
    assert P.registry_for(None) is P.REGISTRY
    assert P.registry_for("extract-v18") is P.REGISTRY
    assert "told" in P.registry_for("extract-v19")

    assert hashlib.sha256(P.registry_prompt().encode()).hexdigest() == REGISTRY_PROMPT_SHA256
    assert (
        hashlib.sha256(P.registry_prompt(frozenset({"has_trait", "identity"})).encode()).hexdigest()
        == REGISTRY_PROMPT_ONLY_SHA256
    )
    assert P.registry_prompt(compiler="extract-v18") == P.registry_prompt()
    assert (
        P.registry_prompt(compiler="extract-v19")
        == P.registry_prompt() + "\n- told (subject: character, object: character, value: text) — " + P.TOLD.description
    )


def test_validate_and_participants_accept_told_only_with_extension():
    item = _told_item()
    assert P.validate(item) == ("pending", "unknown predicate")
    assert P.validate(item, registry=P.registry_for("extract-v19")) == ("valid", None)
    assert P.participants(item) is None
    assert P.participants(item, also=frozenset({"told"})) == [{"name": "하나", "type": "character"}]


def test_v19_prompt_extends_v18_and_joins_only_v18_compiler_sets():
    assert X.DEFAULT_COMPILER == "extract-v16" and "extract-v19" in X.COMPILERS
    assert X.HAPPENED == {"extract-v19"}
    assert X.HAPPENED_MAX == 80 and X.CLOCK_MAX == 80
    assert X.CLOCK_LINE == "STORY CLOCK at the TARGET turn (the chat's status window): {clock}"
    v18, v19 = X.prompt_of("extract-v18"), X.prompt_of("extract-v19")
    assert X.HAPPENED_RULE not in v18 and X.TOLD_RULE not in v18 and '"when_happened"' not in v18
    assert v19 == X._v19(v18) and X.HAPPENED_RULE in v19 and X.TOLD_RULE in v19
    assert '"when_happened": "... or null (event and promised only)",' in v19
    assert v19.replace(X.HAPPENED_RULE + X.TOLD_RULE, "").replace(X._HAPPENED_ANSWER, X._FEELING_ANSWER) == v18
    assert X.FEELING_RULE + X.HAPPENED_RULE + X.TOLD_RULE + X._BECAUSE_AT in v19
    assert X.prompt_of("extract-v19", roles=False) == X.SYSTEM_V19 and X.ROLE_ENDINGS not in X.SYSTEM_V19
    assert X.SYSTEM_V19 == X._v19(X.SYSTEM_V18) and X.PROMPTS["extract-v19"] == X.SYSTEM_V19_ROLES
    assert v19.format(registry=P.registry_prompt(compiler="extract-v19"))
    assert "extract-v19" in X.ROLES & X.PARTS_APART & X.CONFIRMS & X.FEELINGS & entities.PART_EDGES
    assert "extract-v19" not in X.HORIZONS | X.SPEAKERS


def test_v19_key_keeps_v18_fields_and_differs_only_in_compiler_and_prompt():
    v18 = X.extractor(Settings(**BASE, extract_compiler="extract-v18"))
    v19 = X.extractor(Settings(**BASE, extract_compiler="extract-v19"))
    assert sorted(v19.spec) == PINNED_EXTRACT_SPEC_FIELDS["extract-v18"]
    assert {k for k in v18.spec if v18.spec[k] != v19.spec[k]} == {"compiler", "prompt"}
    assert v19.key != v18.key
    assert v19.spec["prompt"] != generations.fingerprint(X.prompt_of("extract-v19"))  # the extension is in it
    assert v18.spec["prompt"] == generations.fingerprint(X.prompt_of("extract-v18"))


def test_the_told_definition_is_in_the_v19_key_only(monkeypatch):
    settings = {c: Settings(**BASE, extract_compiler=c) for c in ("extract-v18", "extract-v19")}
    before = {c: X.extractor(s).key for c, s in settings.items()}
    reworded = dataclasses.replace(P.TOLD, description="the subject passed something on to the object")
    monkeypatch.setitem(P.EXTENSIONS, "extract-v19", {"told": reworded})
    after = {c: X.extractor(s).key for c, s in settings.items()}
    assert after["extract-v18"] == before["extract-v18"] and after["extract-v19"] != before["extract-v19"]
    monkeypatch.setitem(P.EXTENSIONS, "extract-v19", {"told": P.TOLD})
    monkeypatch.setitem(P.EXTENSION_PARTICIPANTS, "extract-v19", frozenset())
    assert X.extractor(settings["extract-v19"]).key != before["extract-v19"]


def test_settings_accept_v19_and_refuse_a_later_name():
    assert Settings(database_url="", extract_compiler="extract-v19").extract_compiler == "extract-v19"
    with pytest.raises(ValueError, match="extract-v19"):
        Settings(database_url="", extract_compiler="extract-v20")
