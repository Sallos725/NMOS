"""PHASE-61 A2: every call made with the extraction model sends the extra body (and no temperature with the switch),
and the embedder's and the reranker's requests are what they were. Stub transports only; synthetic names only."""

from __future__ import annotations

import json
from typing import Any

import httpx
import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import make_client
from nmos_sidecar import llm, notes, rerank, runtime, worker
from nmos_sidecar.config import Settings
from nmos_sidecar.runtime import effective, stored
from test_generations import LLM
from test_phase61_pins import BASE, capture
from test_sidecar_integration import sync
from test_summaries import story_chat

EFFORT = {"reasoning": {"effort": "low"}, "provider": {"order": ["a"]}}
ON = {"llm_extra_body": EFFORT, "llm_no_temperature": True}


def models_in(handler: Any) -> list[llm.ChatModel]:
    """The ChatModel a worker handler calls (its closure holds it, whose `complete_metered` the handler passes)."""
    return [c.cell_contents for c in handler.__closure__ or () if isinstance(c.cell_contents, llm.ChatModel)]


def assert_sent(call: dict[str, Any], json_mode: bool = True, switch: bool = True) -> None:
    body = call["json"]
    assert {k: body[k] for k in EFFORT} == EFFORT
    assert ("temperature" not in body) if switch else body["temperature"] == 0
    assert body.get("response_format") == ({"type": "json_object"} if json_mode else None)
    assert json.loads(call["content"]) == body


@pytest.mark.parametrize("json_mode", [True, False])
def test_every_worker_handler_of_the_extraction_model_sends_the_body(monkeypatch, json_mode):
    jobs = worker.handlers(Settings(**(BASE | ON | {"llm_json_mode": json_mode})))
    assert {"extract", "reveal", "summarize", "canon"} <= set(jobs)
    for kind in ("extract", "reveal", "summarize", "canon"):
        (model,) = models_in(jobs[kind][1])
        sent = capture(monkeypatch)
        model.complete_metered("SYS", "사용자")
        assert_sent(sent[0], json_mode=json_mode)


def test_the_switch_alone_and_the_body_alone(monkeypatch):
    for overrides, switch in (({"llm_extra_body": EFFORT}, False), ({"llm_no_temperature": True}, True)):
        jobs = worker.handlers(Settings(**(BASE | overrides)))
        for kind in ("extract", "reveal", "summarize", "canon"):
            (model,) = models_in(jobs[kind][1])
            sent = capture(monkeypatch)
            model.complete_metered("SYS", "사용자")
            body = sent[0]["json"]
            assert ("temperature" not in body) is switch, kind
            assert ("reasoning" in body) is (not switch), kind


def test_at_the_defaults_every_worker_handler_sends_the_pinned_body(monkeypatch):
    from test_phase61_pins import PINNED_BODY_JSON

    jobs = worker.handlers(Settings(**BASE))
    for kind in ("extract", "reveal", "summarize", "canon"):
        (model,) = models_in(jobs[kind][1])
        model.api_key, model.timeout_s = "sk-test", 42.0
        sent = capture(monkeypatch)
        model.complete_metered("SYS", "사용자")
        assert sent[0]["content"] == PINNED_BODY_JSON, kind


def test_an_extract_job_run_by_the_worker_sends_the_saved_body(migrated, monkeypatch):
    """End to end: a body saved in the panel reaches the request of a real extraction job (the worker reads it back
    with `effective`, as it does every 30 s)."""
    with make_client(migrated, **LLM, summaries=False, canon_facts=False) as c:
        assert c.put("/v1/config", json=ON).status_code == 200
        sync(c, story_chat(3))
    sent = capture(monkeypatch)
    with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
        current = effective(Settings(database_url=migrated, **LLM, summaries=False, canon_facts=False), stored(conn))
        jobs = worker.handlers(current)
        for _ in range(3):
            if not worker.run_once(conn, jobs):
                break
    assert sent and all(call["url"] == "http://fake-llm/v1/chat/completions" for call in sent)
    for call in sent:
        assert_sent(call)


def test_the_authors_note_model_sends_the_body(monkeypatch):
    complete = notes.model_for(Settings(**(BASE | ON)))
    sent = capture(monkeypatch)
    complete("SYS", "사용자")
    assert_sent(sent[0])


def test_the_settings_test_sends_the_body(monkeypatch):
    sent = capture(monkeypatch)
    out = runtime.test_llm("http://llm.test/v1", "model-a", "", True, extra_body=EFFORT, no_temperature=True)
    assert out["ok"] is True
    assert_sent(sent[0])


# --- the embedder and the reranker are not the extraction model ------------------------------------------------------

def embed_requests(monkeypatch, settings: Settings) -> list[dict[str, Any]]:
    seen: list[dict[str, Any]] = []

    def post(url, json, headers, timeout):
        seen.append({"url": url, "json": json, "headers": headers})
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.0, 1.0]}]})

    monkeypatch.setattr(llm.httpx, "post", post)
    (embedder,) = [c.cell_contents for c in worker.handlers(settings)["embed"][1].__closure__
                   if isinstance(c.cell_contents, llm.Embedder)]
    embedder.embed_metered(["하나 keeps the brass key."], timeout_s=5)
    return seen


def test_the_embedders_request_is_unchanged(monkeypatch):
    plain = embed_requests(monkeypatch, Settings(**BASE))
    with_body = embed_requests(monkeypatch, Settings(**(BASE | ON)))
    assert with_body == plain
    assert plain[0]["json"] == {"model": "embed-a", "input": ["하나 keeps the brass key."]}


def test_the_rerankers_request_is_unchanged():
    def requests(settings: Settings) -> list[bytes]:
        seen: list[bytes] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.content)
            return httpx.Response(200, json={"results": [{"index": 0, "relevance_score": 0.5}]})

        reranker = runtime.reranker(settings)
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            assert rerank.score(reranker, "Where is the key?", ["하나 keeps the brass key."], client=client) == [0.5]
        return seen

    keyed = {"rerank_url": "http://rerank.test/v1", "rerank_model": "rerank-a"}
    plain = requests(Settings(**(BASE | keyed)))
    assert plain and requests(Settings(**(BASE | keyed | ON))) == plain
    assert b"reasoning" not in plain[0] and b"temperature" not in plain[0]
