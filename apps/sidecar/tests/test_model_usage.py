"""Phase 17 (ADR 0051, D61): what NMOS's own model calls used, as the provider reported it, kept with each row."""

from __future__ import annotations

import httpx
import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import make_client
from nmos_sidecar import llm
from simchat import SimChat
from test_canon import push
from test_canon_facts import Model, canon_texts, story
from test_canon_facts import drain as drain_canon
from test_extraction import drain as drain_extract
from test_extraction import fake_complete, llm_client  # noqa: F401  (a fixture)
from test_generations import LLM
from test_sidecar_integration import sync
from test_summaries import ON, story_chat, stub
from test_summaries import drain as drain_summaries
from test_vectors import FakeEmbedder, build_chat, drain_embeddings

OPENAI = {"prompt_tokens": 1200, "completion_tokens": 80, "total_tokens": 1280,
          "prompt_tokens_details": {"cached_tokens": 1024}, "completion_tokens_details": {"reasoning_tokens": 30}}


def reply(content: str = '{"assertions": []}', usage=OPENAI, model="gemma4:31b-cloud") -> dict:
    out = {"model": model, "choices": [{"message": {"content": content}}]}
    return {**out, "usage": usage} if usage is not None else out


def metered(complete, usage: dict):
    """A two-value stand-in turned into `complete_metered`: same reply, the given usage."""
    return lambda system, user: (*complete(system, user), {"calls": 1, "ms": 5, **usage})


class MeteredEmbedder(FakeEmbedder):
    def embed_metered(self, texts, timeout_s):
        return self.embed(texts, timeout_s), {"calls": 1, "ms": 2, "input": 7 * len(texts)}


def test_usage_is_what_the_provider_reported(monkeypatch):
    monkeypatch.setattr(llm.httpx, "post", lambda url, json, headers, timeout: httpx.Response(200, json=reply()))
    model = llm.ChatModel("http://fake-llm/v1", "gemma4:31b-cloud")
    parsed, text, usage = model.complete_metered("s", "u")
    assert parsed == {"assertions": []} and text == '{"assertions": []}'
    assert {k: v for k, v in usage.items() if k != "ms"} == {
        "calls": 1, "model": "gemma4:31b-cloud", "input": 1200, "output": 80, "cached": 1024, "reasoning": 30}
    assert isinstance(usage["ms"], int) and usage["ms"] >= 0
    assert llm.reported(usage)
    assert model.complete_json("s", "u") == (parsed, text)  # unchanged for its other callers


@pytest.mark.parametrize("usage, kept", [
    (None, {}),  # no `usage`: "not reported", never estimated
    ({}, {}),
    ({"prompt_tokens": 10}, {"input": 10}),  # only what is there
    ({"prompt_tokens": True, "completion_tokens": -1, "prompt_tokens_details": None}, {}),  # not counts
    ({"prompt_tokens": "10", "completion_tokens": 3.5}, {}),
    ({"prompt_tokens": 5, "completion_tokens": 0, "completion_tokens_details": {"reasoning_tokens": None}},
     {"input": 5, "output": 0}),
])
def test_only_counts_the_provider_gave_are_kept(usage, kept):
    out = llm.usage_of(reply(usage=usage), 0.0)
    tokens = {k: v for k, v in out.items() if k in ("input", "output", "cached", "reasoning")}
    assert tokens == kept and out["calls"] == 1
    assert llm.reported(out) == bool(kept)


def test_a_reply_that_is_not_an_object_still_counts_the_call():
    assert set(llm.usage_of([], 0.0)) == {"calls", "ms"}
    assert not llm.reported(None) and not llm.reported({"calls": 0})


def test_embedding_usage_is_input_tokens(monkeypatch):
    body = {"model": "qwen3-embedding:8b", "data": [{"index": 0, "embedding": [0.1, 0.2]}],
            "usage": {"prompt_tokens": 9, "total_tokens": 9}}
    monkeypatch.setattr(llm.httpx, "post", lambda url, json, headers, timeout: httpx.Response(200, json=body))
    emb = llm.Embedder("http://fake/v1", "qwen3-embedding:8b")
    vectors, usage = emb.embed_metered(["a"], timeout_s=1)
    assert vectors == [[0.1, 0.2]] and usage["input"] == 9 and "output" not in usage
    assert emb.embed(["a"], timeout_s=1) == [[0.1, 0.2]]


def usages(url: str, sql: str) -> list:
    with psycopg.connect(url, row_factory=dict_row) as conn:
        return [r["usage"] for r in conn.execute(sql).fetchall()]


def test_an_extraction_keeps_its_call_and_a_rebuild_keeps_the_old_rows(llm_client, migrated):
    chat = SimChat()
    chat.user("Hi.")
    chat.reply("Ok.")  # too little text: stored without asking the model
    chat.user("Where is Mina?")
    chat.reply("Mina is in the library.")
    chat.user("And then?")  # the tail reply stays provisional until the user goes on (D5)
    sync(llm_client, chat)
    drain_extract(migrated, metered(fake_complete, {"input": 900, "output": 40}))
    rows = usages(migrated, "SELECT usage FROM extraction ORDER BY usage->>'calls'")
    assert rows[0] == {"calls": 0}
    assert [(u["calls"], u["input"], u["output"]) for u in rows[1:]] == [(1, 900, 40)]
    conv = llm_client.get("/v1/conversations").json()[0]["id"]
    assert llm_client.post(f"/v1/conversations/{conv}/rebuild").status_code == 200
    drain_extract(migrated, metered(fake_complete, {"input": 950, "output": 41}))
    old = usages(migrated, "SELECT usage FROM extraction WHERE discarded_at IS NOT NULL ORDER BY usage->>'calls'")
    new = usages(migrated, "SELECT usage FROM extraction WHERE discarded_at IS NULL ORDER BY usage->>'calls'")
    assert old == rows  # each row keeps the usage of the call that produced it
    assert [u.get("input") for u in new] == [None, 950]


def test_a_stand_in_without_usage_and_a_row_before_the_migration_record_none(llm_client, migrated):
    chat = SimChat()
    chat.user("Where is Mina?")
    chat.reply("Mina is in the library.")
    chat.user("And then?")  # the tail reply stays provisional until the user goes on (D5)
    sync(llm_client, chat)
    drain_extract(migrated)  # a two-value `complete`: usage unknown
    assert usages(migrated, "SELECT usage FROM extraction") == [None]


def test_summaries_keep_their_calls(migrated):
    chat = story_chat(30)
    with make_client(migrated, **ON) as c:
        sync(c, chat)
        drain_summaries(migrated, metered(stub, {"input": 300, "output": 60}))
    rows = usages(migrated, "SELECT level, usage FROM summary ORDER BY created_at")
    assert len(rows) == 4 and all(u["calls"] == 1 and u["input"] == 300 for u in rows)


def test_canon_reads_keep_their_calls(migrated):
    chat, model = story(), Model()
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        push(c, chat, canon_texts())
        drain_canon(migrated, metered(model, {"input": 500, "output": 20}))
    rows = usages(migrated, "SELECT x.usage FROM extraction x WHERE x.window_hash LIKE 'canon:%'")
    assert len(rows) == 2 and all(u["input"] == 500 for u in rows)


def test_each_embedded_chunk_keeps_its_call(migrated):
    with make_client(migrated, embedder=FakeEmbedder(), embed_url="http://fake/v1", embed_model="fake-embed") as c:
        sync(c, build_chat())
        drain_embeddings(migrated, MeteredEmbedder())
    rows = usages(migrated, "SELECT usage FROM revision_embedding")
    assert rows and all(u == {"calls": 1, "ms": 2, "input": 7} for u in rows)


def test_usage_goes_out_and_comes_back_with_the_archive(migrated, database_url_factory, tmp_path):
    from nmos_sidecar import archive

    chat = story_chat(30)
    with make_client(migrated, **ON, embedder=FakeEmbedder(), embed_url="http://fake/v1", embed_model="fake-embed") as c:
        sync(c, chat)
        drain_extract(migrated, metered(fake_complete, {"input": 900, "output": 40}))
        drain_summaries(migrated, metered(stub, {"input": 300, "output": 60}))
        drain_embeddings(migrated, MeteredEmbedder())
    path = tmp_path / f"a{archive.SUFFIX}"
    archive.export_file(migrated, str(path), embeddings=True)
    target = database_url_factory()
    archive.restore_file(target, str(path))
    for sql in ("SELECT usage FROM extraction ORDER BY id", "SELECT usage FROM summary ORDER BY id",
                "SELECT usage FROM revision_embedding ORDER BY source_revision_id, projection, chunk"):
        rows = usages(migrated, sql)
        assert rows and any(u and u.get("input") for u in rows) and usages(target, sql) == rows


def test_a_call_that_reported_nothing_is_kept_as_a_call(llm_client, migrated):
    chat = SimChat()
    chat.user("Where is Mina?")
    chat.reply("Mina is in the library.")
    chat.user("And then?")
    sync(llm_client, chat)
    drain_extract(migrated, lambda s, u: (*fake_complete(s, u), llm.usage_of({"model": "local"}, 0.0)))
    (usage,) = usages(migrated, "SELECT usage FROM extraction")
    assert set(usage) == {"calls", "ms", "model"} and usage["calls"] == 1 and not llm.reported(usage)


def test_the_chat_totals_per_generation_and_the_inspector(migrated):
    chat = story_chat(30)
    with make_client(migrated, **ON, embedder=FakeEmbedder(), embed_url="http://fake/v1", embed_model="fake-embed") as c:
        sync(c, chat)
        drain_extract(migrated, metered(fake_complete, {"input": 900, "output": 40, "cached": 100}))
        drain_summaries(migrated, metered(stub, {"input": 300, "output": 60}))
        drain_embeddings(migrated, MeteredEmbedder())
        with psycopg.connect(migrated, autocommit=True) as conn:  # one result from before usage was recorded
            conn.execute("UPDATE summary SET usage = NULL WHERE id = (SELECT id FROM summary WHERE level = 'scene' ORDER BY id LIMIT 1)")
        conv = c.get("/v1/conversations").json()[0]["id"]
        assert "usage" not in c.get(f"/v1/conversations/{conv}/coverage").json()  # the HUD's polls stay cheap
        usage = c.get(f"/v1/conversations/{conv}/coverage", params={"usage": True}).json()["usage"]
        by = {g["kind"]: g for g in usage["generations"]}
        assert set(by) == {"extract", "summarize", "embed"} and all(g["active"] for g in by.values())
        ex = by["extract"]
        assert ex["calls"] == ex["reported"] == ex["rows"] and ex["input"] == 900 * ex["calls"]
        assert ex["cached"] == 100 * ex["calls"] and ex["not_recorded"] == 0
        sm = by["summarize"]
        assert (sm["rows"], sm["not_recorded"], sm["calls"], sm["input"]) == (4, 1, 3, 900)
        assert by["embed"]["input"] == 7 * by["embed"]["calls"] and by["embed"]["output"] == 0
        assert usage["total"]["calls"] == sum(g["calls"] for g in by.values())
        page = c.get(f"/inspector/c/{conv}", params={"lang": "en"}).text
        assert "Model usage" in page and f"{ex['input']:,}" in page and "1 results from before recording" in page
        page = c.get(f"/inspector/c/{conv}", params={"lang": "ko"}).text
        assert "모델 사용량" in page and "기록 이전 결과 1개" in page


def test_a_chat_without_model_work_says_so(llm_client, migrated):
    chat = SimChat()
    chat.user("Where is Mina?")
    sync(llm_client, chat)
    conv = llm_client.get("/v1/conversations").json()[0]["id"]
    usage = llm_client.get(f"/v1/conversations/{conv}/coverage", params={"usage": True}).json()["usage"]
    assert usage == {"generations": [], "total": {k: 0 for k in usage["total"]}}
    assert "No model calls recorded yet." in llm_client.get(f"/inspector/c/{conv}", params={"lang": "en"}).text


def test_older_rows_count_under_their_kind_and_unreported_fields_are_not_zeros(migrated):
    chat = story_chat(30)
    with make_client(migrated, **ON, embedder=FakeEmbedder(), embed_url="http://fake/v1", embed_model="fake-embed") as c:
        sync(c, chat)
        drain_extract(migrated, metered(fake_complete, {"input": 900, "output": 40}))  # no `cached` reported
        drain_embeddings(migrated, MeteredEmbedder())
        with psycopg.connect(migrated, autocommit=True) as conn:  # as rows from before generations would be
            conn.execute("UPDATE extraction SET extractor_key = NULL, usage = NULL WHERE id = (SELECT id FROM extraction"
                         " ORDER BY id LIMIT 1)")
            conn.execute("UPDATE revision_embedding SET projection = 'legacy:old-embed', usage = NULL WHERE"
                         " (source_revision_id, chunk) = (SELECT source_revision_id, chunk FROM revision_embedding LIMIT 1)")
        conv = c.get("/v1/conversations", params={"host_chat_ref": chat.id}).json()
        assert [x["host_chat_ref"] for x in conv] == [chat.id]
        assert c.get("/v1/conversations", params={"host_chat_ref": "no-such-chat"}).json() == []
        conv = conv[0]["id"]
        usage = c.get(f"/v1/conversations/{conv}/coverage", params={"usage": True}).json()["usage"]
        old = [g for g in usage["generations"] if g["key"] in (None, "legacy:old-embed")]
        assert sorted((g["kind"], g["rows"], g["not_recorded"], g["calls"]) for g in old) == [
            ("embed", 1, 1, 0), ("extract", 1, 1, 0)]
        assert usage["generations"][-2:] == sorted(old, key=lambda g: g["key"] is None)  # without a generation: last
        ex = next(g for g in usage["generations"] if g["kind"] == "extract" and g["key"])
        assert ex["input_reported"] == ex["calls"] and ex["cached_reported"] == 0
        emb = next(g for g in usage["generations"] if g["kind"] == "embed" and g["active"])
        assert emb["output_reported"] == 0 and emb["input_reported"] == emb["calls"]
        page = c.get(f"/inspector/c/{conv}", params={"lang": "en"}).text
        section = page[page.index('id="s-usage"'):]
        assert "no generation (older version)" in section and "legacy:old-embed" in section
        embed_row = section[section.index("Embeddings"):].split("</tr>")[0]
        assert embed_row.count("<td>—</td>") == 2  # output and cached input: not reported, not 0
