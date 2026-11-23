"""PHASE-60 step 2 (A1, A3): permanent pins for what Phase 60 must not move.

No later slice may change the expected literals in this module.
"""

from __future__ import annotations

from nmos_sidecar import canonfacts, extraction, packet, reveals, summaries, vectors
from nmos_sidecar.config import Settings

BASE = dict(
    database_url="postgresql://x",
    llm_url="http://llm.test/v1",
    llm_model="model-a",
    embed_url="http://embed.test/v1",
    embed_model="embed-a",
    llm_json_mode=True,
    extract_turns=3,
    extract_hints=40,
    embed_max_chunks=8,
    summaries=True,
    canon_facts=True,
)

# Computed at 1b16ef6 for BASE. Literal strings, never recomputed.
PINNED = {
    "extract-v15": "extract-8ed39e6a2cf25ffae903b29d7ac9acd9",
    "extract-v16": "extract-029fac9f22f705a5130c70505c98ba49",
    "extract-v17": "extract-c98f66fc178127c0e3126c8503e4b8e9",
    "extract-v18": "extract-15d6e23accadb12ba64df5040859fc22",
    "default": "extract-029fac9f22f705a5130c70505c98ba49",  # extract_compiler="" is extract-v16
    "canon": "canon-5fb6b7fb622106e4949b20ab6e422366",
    "summarize": "summarize-9ff98c40c22744e5ec947542b77f9125",
    "reveal": "reveal-9b682161681128f8a06f7db566d54899",
    "embed": "embed-281e4c64319dfb23143ecedc3e2602a3",
}

PINNED_EXTRACT_SPEC_FIELDS = {
    "extract-v15": [
        "compiler", "context_chars", "context_turns", "endpoint", "hints", "json_mode",
        "kind", "model", "normalizer", "predicates", "prompt", "target_chars", "temperature", "unit",
    ],
    "extract-v16": [
        "aliases", "compiler", "confirm", "context_chars", "context_turns", "endpoint", "hints", "json_mode",
        "kind", "model", "normalizer", "predicates", "prompt", "target_chars", "temperature", "unit",
    ],
    "extract-v17": [
        "aliases", "compiler", "confirm", "context_chars", "context_turns", "endpoint", "hints", "json_mode",
        "kind", "model", "normalizer", "predicates", "prompt", "speakers", "target_chars", "temperature", "unit",
    ],
    "extract-v18": [
        "aliases", "compiler", "confirm", "context_chars", "context_turns", "endpoint", "hints", "json_mode",
        "kind", "model", "normalizer", "predicates", "prompt", "target_chars", "temperature", "unit",
    ],
}


def test_pinned_generation_keys_spec_fields_and_defaults():
    """A1: extractor keys (v15..v18), canon/summarize/reveal/embed keys, spec field sets, and code defaults."""
    base = Settings(**BASE)
    for compiler in ("extract-v15", "extract-v16", "extract-v17", "extract-v18"):
        gen = extraction.extractor(Settings(**BASE, extract_compiler=compiler))
        assert gen.key == PINNED[compiler], compiler
        assert sorted(gen.spec) == PINNED_EXTRACT_SPEC_FIELDS[compiler], compiler

    assert extraction.extractor(Settings(**BASE, extract_compiler="")).key == PINNED["default"]
    assert canonfacts.generation(base).key == PINNED["canon"]
    assert summaries.summarizer(base).key == PINNED["summarize"]
    assert reveals.generation(base).key == PINNED["reveal"]
    assert vectors.projection(base).key == PINNED["embed"]

    assert packet.DEFAULT_POLICY == "packet-v19"
    assert extraction.DEFAULT_COMPILER == "extract-v16"
