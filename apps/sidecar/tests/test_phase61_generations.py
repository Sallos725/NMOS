"""PHASE-61 S2 (A1, A1b, A3; ADR 0088 items 2-3): the extra body and the temperature switch in the generations built
from the model settings, `classify`, and what a save of them queues. Stub models only; synthetic names only."""

from __future__ import annotations

import pytest

from base_rules import base_rules  # noqa: F401 -- autouse: the base's keys, without the revision marker (PHASE-66 part 5)
from conftest import active_generation, make_client
from nmos_sidecar import canonfacts, extraction, generations, reveals, summaries
from nmos_sidecar.config import Settings
from test_generations import LLM
from test_phase57_carry_on import drain, played, queued
from test_phase61_pins import BASE, PINNED

EFFORT = {"reasoning": {"effort": "low"}}
BUILDERS = {
    "extract": extraction.extractor, "reveal": reveals.generation,
    "summarize": summaries.summarizer, "canon": canonfacts.generation,
}
DEFAULT_KEYS = {"extract": PINNED[("", True)], "reveal": PINNED[("reveal", True)],
                "summarize": PINNED[("summarize", True)], "canon": PINNED[("canon", True)]}


def gens(**overrides) -> dict[str, generations.Generation]:
    settings = Settings(**(BASE | overrides))
    return {kind: build(settings) for kind, build in BUILDERS.items()}


def diff(a: dict, b: dict) -> set[str]:
    return {k for k in a.keys() | b.keys() if a.get(k, "absent") != b.get(k, "absent")}


def test_the_request_spec_at_the_defaults_is_todays_temperature():
    assert generations.request_spec({}, False) == {"temperature": 0}
    assert generations.request_spec({}, True) == {"temperature": None}
    assert generations.request_spec(EFFORT, False) == {"temperature": 0, "request": EFFORT}


def test_the_defaults_and_an_explicit_empty_body_keep_every_pinned_key():
    for overrides in ({}, {"llm_extra_body": {}, "llm_no_temperature": False}):
        assert {k: g.key for k, g in gens(**overrides).items()} == DEFAULT_KEYS


def test_a_body_changes_every_key_and_each_spec_in_request_only():
    base, with_body = gens(), gens(llm_extra_body=EFFORT)
    for kind in BUILDERS:
        assert with_body[kind].key != base[kind].key, kind
        assert diff(base[kind].spec, with_body[kind].spec) == {"request"}, kind
        assert with_body[kind].spec["request"] == EFFORT and with_body[kind].spec["temperature"] == 0


def test_the_switch_changes_every_key_and_each_spec_in_temperature_only():
    base, off = gens(), gens(llm_no_temperature=True)
    for kind in BUILDERS:
        assert off[kind].key != base[kind].key, kind
        assert diff(base[kind].spec, off[kind].spec) == {"temperature"}, kind
        assert off[kind].spec["temperature"] is None and "request" not in off[kind].spec


def test_every_extractor_compiler_takes_the_body_the_same_way():
    for compiler in ("extract-v15", "extract-v16", "extract-v17", "extract-v18", "extract-v19"):
        plain = extraction.extractor(Settings(**BASE, extract_compiler=compiler))
        both = extraction.extractor(Settings(**BASE, extract_compiler=compiler, llm_extra_body=EFFORT,
                                             llm_no_temperature=True))
        assert plain.key == PINNED[(compiler, True)]
        assert diff(plain.spec, both.spec) == {"request", "temperature"}, compiler


def test_the_request_is_order_insensitive():
    """The panel sends the object in the owner's key order: two orders of one body are one generation."""
    one = {"reasoning": {"effort": "low", "exclude": True}, "provider": {"order": ["b", "a"], "sort": "price"}}
    two = {"provider": {"sort": "price", "order": ["b", "a"]}, "reasoning": {"exclude": True, "effort": "low"}}
    a, b = gens(llm_extra_body=one), gens(llm_extra_body=two)
    for kind in BUILDERS:
        assert a[kind].key == b[kind].key, kind
        assert list(a[kind].spec["request"]) == ["provider", "reasoning"]  # stored canonical: sorted keys
        assert list(a[kind].spec["request"]["reasoning"]) == ["effort", "exclude"]
    # a list's order is the provider's meaning: it stays, and it is a different body
    assert gens(llm_extra_body={"provider": {"order": ["a", "b"]}})["extract"].key != gens(
        llm_extra_body={"provider": {"order": ["b", "a"]}})["extract"].key


def test_the_model_fields_are_the_specs():
    assert generations.MODEL_FIELDS == ("model", "endpoint", "request", "temperature")


# --- classify ---------------------------------------------------------------------------------------------------------

def extractor(compiler: str = "", **overrides) -> generations.Generation:
    return extraction.extractor(Settings(**(LLM | overrides), extract_compiler=compiler))


@pytest.mark.parametrize("change", [
    {"llm_extra_body": EFFORT}, {"llm_no_temperature": True}, {"llm_extra_body": EFFORT, "llm_no_temperature": True},
    {"llm_extra_body": EFFORT, "llm_model": "fake-9"},
])
def test_a_body_or_switch_change_is_a_model_change_in_both_directions(migrated, db, change):
    with make_client(migrated, **LLM):
        pass
    v16 = active_generation(db, "extract").key
    assert v16 == extractor("extract-v16").key
    changed = extractor("extract-v16", **change)
    assert generations.classify(db, v16, changed) == "model"
    generations.activate(db, changed)
    assert generations.classify(db, changed.key, extractor("extract-v16")) == "model"  # back: the rollback step
    assert generations.classify(db, changed.key, changed) == "same"


@pytest.mark.parametrize("change", [{"llm_extra_body": EFFORT}, {"llm_no_temperature": True},
                                    {"llm_extra_body": EFFORT, "llm_no_temperature": True}])
def test_with_an_adds_compiler_change_it_is_model_never_adds_or_version(migrated, db, change):
    with make_client(migrated, **LLM):
        pass
    v16 = active_generation(db, "extract").key
    assert generations.classify(db, v16, extractor("extract-v19")) == "adds"  # as before
    assert generations.classify(db, v16, extractor("extract-v19", **change)) == "model"
    v18 = extractor("extract-v18")
    generations.activate(db, v18)
    assert generations.classify(db, v18.key, extractor("extract-v19", **change)) == "model"
    v19 = extractor("extract-v19", **change)
    generations.activate(db, v19)
    assert generations.classify(db, v19.key, extractor("extract-v18")) == "model"
    assert generations.classify(db, v19.key, extractor("extract-v16", **change)) == "adds"
    # a setting the key hashes is still a version change, with or without the body
    assert generations.classify(db, v19.key, extractor("extract-v19", **change, extract_turns=2)) == "version"
    assert generations.classify(db, v19.key, extractor("extract-v17", **change)) == "version"


def test_the_other_generations_classify_the_same_way(migrated, db):
    with make_client(migrated, **LLM):
        pass
    for kind in ("summarize", "canon"):
        prev = active_generation(db, kind).key
        build = BUILDERS[kind]
        assert generations.classify(db, prev, build(Settings(**LLM, llm_extra_body=EFFORT))) == "model", kind
        assert generations.classify(db, prev, build(Settings(**LLM, llm_no_temperature=True))) == "model", kind
        assert generations.classify(db, prev, build(Settings(**LLM))) == "same", kind


# --- through the API: the preview, carry on, recent, the stored spec -------------------------------------------------

def same_llm(c) -> dict:
    """The llm fields as the panel sends them when the section is dirty: present, unchanged."""
    view = c.get("/v1/config").json()["llm"]
    return {"llm_url": view["url"], "llm_model": view["model"]}


@pytest.mark.parametrize("change", [{"llm_extra_body": EFFORT}, {"llm_no_temperature": True},
                                    {"llm_extra_body": EFFORT, "llm_no_temperature": True}])
def test_the_panels_save_previews_as_a_model_change_and_carry_on_queues_nothing(migrated, db, change):
    with make_client(migrated, **LLM) as c:
        played(migrated, c)
        before = {k: active_generation(db, k).key for k in ("extract", "summarize", "canon")}
        update = same_llm(c) | change
        out = c.post("/v1/config/preview", json=update | {"extract_backfill": 10})
        assert out.status_code == 200, out.text
        out = out.json()
        assert out["model_change"] is True
        assert out["changes"] == {"extract": "model", "summarize": "model", "canon": "model"}
        assert out["queued"]["continue"] == {"extract": 0, "summarize": 0, "canon": 0}
        assert out["queued"]["recent"] == {"extract": 9, "summarize": 1, "canon": 0}
        assert out["queued"]["canon"] == {"extract": 0, "summarize": 0, "canon": 2}
        assert queued(db) == {} and {k: active_generation(db, k).key for k in before} == before  # nothing saved

        res = c.put("/v1/config", json=update | {"on_model_change": {"mode": "continue"}})
        assert res.status_code == 200, res.text
        assert res.json()["queued_jobs"] == 0 and queued(db) == {}
        spec = active_generation(db, "extract").spec
        assert spec.get("request") == change.get("llm_extra_body")
        assert spec["temperature"] == (None if change.get("llm_no_temperature") else 0)
        for kind in ("summarize", "canon"):
            assert active_generation(db, kind).key != before[kind]
            assert active_generation(db, kind).spec.get("request") == change.get("llm_extra_body")

        # back to the defaults (the rollback rehearsal's first step): a model change again, nothing queued
        back = c.put("/v1/config", json=same_llm(c) | {"llm_extra_body": {}, "llm_no_temperature": False,
                                                       "on_model_change": {"mode": "continue"}})
        assert back.status_code == 200 and back.json()["queued_jobs"] == 0 and queued(db) == {}
        assert {k: active_generation(db, k).key for k in before} == before


def test_recent_queues_the_latest_turns(migrated, db):
    with make_client(migrated, **LLM) as c:
        played(migrated, c)
        res = c.put("/v1/config", json=same_llm(c) | {"llm_extra_body": EFFORT, "extract_backfill": 10,
                                                      "on_model_change": {"mode": "recent"}})
        assert res.status_code == 200, res.text
        assert queued(db) == {"extract": 9, "summarize": 1}
        assert active_generation(db, "extract").spec["request"] == EFFORT
        assert drain(migrated) >= 10 and queued(db) == {}


def test_a_reordered_body_is_no_change(migrated, db):
    with make_client(migrated, **LLM) as c:
        played(migrated, c)
        body = {"reasoning": {"effort": "low"}, "provider": {"sort": "price"}}
        c.put("/v1/config", json=same_llm(c) | {"llm_extra_body": body})
        key = active_generation(db, "extract").key
        reordered = {"provider": {"sort": "price"}, "reasoning": {"effort": "low"}}
        out = c.post("/v1/config/preview", json=same_llm(c) | {"llm_extra_body": reordered}).json()
        assert out["model_change"] is False and out["queued"]["recent"] == {}
        assert c.put("/v1/config", json=same_llm(c) | {"llm_extra_body": reordered}).json()["queued_jobs"] == 0
        assert active_generation(db, "extract").key == key


def test_a_refused_body_is_a_422_on_the_preview_in_the_panels_shape(migrated, db):
    with make_client(migrated, **LLM) as c:
        res = c.post("/v1/config/preview", json=same_llm(c) | {"llm_extra_body": {"temperature": 0.2}})
        assert res.status_code == 422
        assert res.json()["detail"] == ["llm_extra_body: may not set 'temperature': the request sets it itself"]


def test_a_restart_with_the_saved_body_queues_nothing(migrated, db):
    with make_client(migrated, **LLM) as c:
        played(migrated, c)
        c.put("/v1/config", json=same_llm(c) | {"llm_extra_body": EFFORT, "llm_no_temperature": True})
        key = active_generation(db, "extract").key
    with make_client(migrated, **LLM):
        assert queued(db) == {} and active_generation(db, "extract").key == key
