"""extract-v19 (PHASE-60 S7, S8, ADR 0086): the `told` per-compiler extension, prompt, generation key and settings.

Synthetic names only (세라, 카이토, 하나, 유나).
"""

from __future__ import annotations

import hashlib

from nmos_sidecar import predicates as P

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
