"""AGE-76: frozen independent stories through sync, PostgreSQL, selection and replay.

The stories, assertions and cosine similarities are authored test fixtures. They test
packet selection and its guards, not a provider's extraction/embedding quality or
PocketRisu UI behavior. The pronoun case preserves observed selection only; it does
not establish semantic pronoun resolution. Oracles were fixed before the correction.
"""
from __future__ import annotations

import json
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import make_client
from nmos_sidecar import audit, retrieval
from nmos_sidecar.llm import ChatModel, Embedder
from nmos_sidecar.retrieval import RecallOptions
from simchat import SimChat
from test_extraction import drain
from test_sidecar_integration import sync
from test_vectors import drain_embeddings

FIXTURE = Path(__file__).resolve().parents[3] / "fixtures/recall/age76-particles.json"
STORIES = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]


class LocalVectors:
    """Fixed synthetic cosine scores; never contacts an embedding provider."""

    def __init__(self, story: dict[str, Any]) -> None:
        self.scores = {story["messages"][int(i)]: score
                       for i, score in story["vector_similarities"].items()}

    def embed(self, texts: list[str], timeout_s: float) -> list[list[float]]:
        out = []
        for text in texts:
            score = self.scores.get(text)
            if score is not None:
                out.append([score, math.sqrt(1 - score * score)])
            else:
                out.append([1.0, 0.0] if "?" in text else [0.0, 1.0])
        return out


def _extractor(story: dict[str, Any]) -> Callable[[str, str], tuple[dict[str, Any], str]]:
    """Return only the fixture's explicit assertions whose source is in TARGET.

    Ordinary action cases intentionally extract nothing: their raw source must
    still be recalled, as in the original P01 failure.
    """
    def complete(system: str, user: str) -> tuple[dict[str, Any], str]:
        target = user.split("TARGET", 1)[1]
        assertions = []
        for seed in story["seed_assertions"]:
            evidence = story["messages"][seed["message_index"]]
            if evidence in target:
                item = {k: v for k, v in seed.items() if k != "message_index"}
                item.update(subject_type="character", evidence=evidence, epistemic="stated",
                            confidence=0.95, modality="actual")
                assertions.append(item)
        return {"assertions": assertions, "secrets": [], "roles_ended": [], "same_names": []}, "{}"
    return complete


def _assert_packet(run: dict[str, Any], query: dict[str, Any], revisions: dict[int, str]) -> None:
    """Require source attribution as well as text; forbid violations independently."""
    case_id = query["id"]
    placed = [line for line in run["lines"] if line.get("placed")]
    assert run["tokens"] <= query.get("budget", 4000), case_id
    assert all(not line.get("text") and not line.get("tok") and not line.get("placed")
               and "content" not in line and "marks" not in line
               for line in run["lines"] if line.get("label") == "hidden"), case_id
    if query["expected"] == "associated_source_placed":
        assert any(line.get("ref", {}).get("revision") == revisions[query["answer_index"]]
                   and query["expected_quote"] in line.get("text", "") for line in placed), \
            f"{case_id}: asked actor/action/source must be placed; diagnostics={run.get('diagnostics')}"
    if "forbid_source_index" in query:
        assert all(line.get("ref", {}).get("revision") != revisions[query["forbid_source_index"]]
                   for line in placed), f"{case_id}: excluded source was placed"
    assert all(value in run["text"] for value in query.get("required", [])), case_id
    assert all(value not in run["text"] for value in query.get("forbidden", [])), case_id
    assert all(value not in run["text"] for value in query.get("forbidden_associations", [])), case_id
    if query["expected"] == "hidden":
        assert any(line.get("label") == "hidden" for line in run["lines"]), case_id
    if query["expected"] == "no_persona_question_bonus":
        assert not any(line.get("kind") in ("fact", "claim") and line.get("label") == "required"
                       and any(kind in line.get("text", "") for kind in ("identity", "member_of"))
                       for line in placed), case_id


@pytest.mark.parametrize("story", STORIES, ids=lambda story: story["id"])
def test_frozen_particle_stories_preserve_source_association_and_guards(
        migrated: str, monkeypatch: pytest.MonkeyPatch, story: dict[str, Any]) -> None:
    def no_provider(*args: Any, **kwargs: Any) -> None:
        pytest.fail("The AGE-76 fixture must not call a model provider")

    for cls, methods in ((ChatModel, ("complete", "complete_metered")),
                         (Embedder, ("embed", "embed_metered"))):
        for method in methods:
            if hasattr(cls, method):
                monkeypatch.setattr(cls, method, no_provider)
    # These fixtures assert source association and isolation, not sub-25ms scheduling.
    # Real cancellation and late-result admission keep the production budget in test_keyword_particles.py.
    monkeypatch.setattr(retrieval, "KEYWORD_SLICE_MS", 1000)
    embedder = LocalVectors(story)
    with make_client(migrated, packet_policy="packet-v18", llm_url="http://unused.invalid/v1",
                     llm_model="synthetic-age76", embedder=embedder, embed_url="http://unused.invalid/v1",
                     embed_model="deterministic-age76", vector_min_sim=0.3, summaries=False,
                     canon_facts=False, parsers_file="", lexical_timeout_ms=1000) as client:
        chat = SimChat()
        for i, text in enumerate(story["messages"]):
            (chat.user if i % 2 == 0 else chat.reply)(text)
        chat.user("계속.")  # Accept the final reply before compiling the fixture.
        labels = {"persona_name": story["persona_name"]} if story.get("persona_name") else {}
        sync(client, chat, **labels)
        drain(migrated, _extractor(story))
        drain_embeddings(migrated, embedder)
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            conversation = conn.execute("SELECT id, head_commit_id FROM conversation WHERE host_chat_ref=%s",
                                        (chat.id,)).fetchone()
            rows = conn.execute("SELECT position, source_revision_id FROM active_membership WHERE commit_id=%s",
                                (conversation["head_commit_id"],)).fetchall()
            revisions = {row["position"]: str(row["source_revision_id"]) for row in rows}
        for query in story["queries"]:
            if "disable_index" in query:
                chat.disable(query["disable_index"])
                sync(client, chat, **labels)
            mode = query.get("mode", {"strict": False, "narrator": None})
            changed = client.put(f"/v1/conversations/{conversation['id']}/memory-mode", json=mode)
            assert changed.status_code == 200, changed.text
            response = client.post("/v1/retrieve", json={
                "chat_id": chat.id, "query": query["query"],
                "previous_ai": query.get("previous_ai", story["messages"][-1]),
                "budget_tokens": query.get("budget", 4000),
                "in_context_ids": [chat.messages[i]["chatId"] for i in query.get("in_context_indices", [])],
            })
            assert response.status_code == 200, response.text
            payload = response.json()
            trace = client.get(f"/v1/trace/{payload['trace_id']}").json()
            assert trace["recall_options"]["keyword_particles"] is True
            _assert_packet({"text": payload["packet"]["text"], "tokens": trace["token_estimate"],
                            "lines": trace["lines"], "diagnostics": trace["latency_ms"]}, query, revisions)
            # Repeat the exact recorded request, without changing its prompt, flags or source window.
            for _ in range(3):
                with psycopg.connect(migrated, row_factory=dict_row,
                                     options="-c default_transaction_read_only=on") as conn:
                    replay = audit.replay(conn, UUID(payload["trace_id"]),
                                          RecallOptions(embedder=embedder,
                                                        embed_projection=trace["embed_projection"]))
                assert replay and replay["status"] == "ok"
                _assert_packet(replay, query, revisions)
