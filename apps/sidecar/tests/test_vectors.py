"""Phase 3: embeddings, vector recall within head membership, RRF fusion, fail-open fallback."""

from __future__ import annotations

import math

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import active_generation, make_client
from nmos_sidecar.llm import LLMError
from nmos_sidecar.vectors import chunks, process_embed
from nmos_sidecar.worker import run_once
from simchat import SimChat
from test_sidecar_integration import recall, sync

CONCEPTS = [
    ("열쇠", "key", "은빛"), ("등대", "lighthouse", "불빛"), ("검", "sword", "칼날"), ("빵", "bread", "오븐"),
    ("비", "rain", "우산"), ("편지", "letter", "봉투"), ("숨기", "hid", "감추"), ("잃어", "lost", "사라"),
]


class FakeEmbedder:
    """Concept-bag embeddings: paraphrases sharing a concept are close, unrelated text is orthogonal."""

    def __init__(self, fail: bool = False):
        self.fail = fail

    def embed(self, texts, timeout_s):
        if self.fail:
            raise LLMError("embedding service down")
        out = []
        for t in texts:
            v = [1.0 if any(w in t.lower() for w in group) else 0.0 for group in CONCEPTS] + [0.05]
            norm = math.sqrt(sum(x * x for x in v))
            out.append([x / norm for x in v])
        return out


def drain_embeddings(url: str, emb=None) -> int:
    emb = emb or FakeEmbedder()
    n = 0
    with psycopg.connect(url, row_factory=dict_row, autocommit=True) as conn:
        gen = active_generation(conn, "embed")
        while run_once(conn, {"embed": (gen.key, lambda c, job: process_embed(c, job, emb, gen))}):
            n += 1
    return n


def build_chat() -> SimChat:
    chat = SimChat()
    chat.user("하나는 은빛 열쇠를 등대 지하에 숨겼다.")
    chat.reply("그 비밀은 아무도 모른다.")
    for i in range(8):
        chat.user(f"잡담 {i}: 오늘 날씨 이야기.")
        chat.reply(f"응답 {i}: 그렇네.")
    chat.user("그 물건 어디다 감췄더라? 열쇠 말이야.")
    return chat


@pytest.fixture
def vec_client(migrated):
    with make_client(migrated, embedder=FakeEmbedder(), embed_url="http://fake/v1", embed_model="fake-embed") as c:
        yield c


def test_chunks_cover_text():
    text = "가나다. " * 300
    spans = chunks(text)
    assert spans[0][0] == 0 and all(e - s <= 700 for s, e in spans) and len(spans) <= 8


def test_paraphrase_recalled_through_vectors(vec_client, migrated, db):
    chat = build_chat()
    sync(vec_client, chat)
    assert db.execute("SELECT count(*) AS n FROM job WHERE kind = 'embed'").fetchone()["n"] == len(chat.messages)
    drain_embeddings(migrated)
    query = "혹시 그 반짝이는 은빛 물건은 어디 숨겼지?"  # little lexical overlap with the fact
    out = recall(vec_client, chat, query, in_context=[m["chatId"] for m in chat.messages[-3:]])
    assert "등대 지하에 숨겼다" in out["packet"]["text"]
    trace = vec_client.get(f"/v1/trace/{out['trace_id']}").json()
    assert trace["latency_ms"]["vector_mode"] == "on"
    assert any(c["sim"] and c["user_score"] < 0.4 for c in trace["candidates"])  # vector-only hit


def test_vector_path_never_returns_inactive(vec_client, migrated):
    chat = build_chat()
    sync(vec_client, chat)
    drain_embeddings(migrated)
    chat.delete(0)
    sync(vec_client, chat)
    out = recall(vec_client, chat, "은빛 열쇠를 숨긴 곳", in_context=[])
    assert "등대 지하" not in out["packet"]["text"]


def test_embedding_outage_falls_back_to_lexical(migrated):
    chat = build_chat()
    with make_client(migrated, embedder=FakeEmbedder(), embed_url="http://fake/v1", embed_model="fake-embed") as ok:
        sync(ok, chat)
    drain_embeddings(migrated)
    with make_client(migrated, embedder=FakeEmbedder(fail=True), embed_url="http://fake/v1",
                     embed_model="fake-embed") as down:
        out = recall(down, chat, "은빛 열쇠를 등대에 숨겼지?", in_context=[m["chatId"] for m in chat.messages[-3:]])
        trace = down.get(f"/v1/trace/{out['trace_id']}").json()
    assert trace["latency_ms"]["vector_mode"].startswith("fallback")
    assert "등대 지하에 숨겼다" in out["packet"]["text"]  # lexical still works
