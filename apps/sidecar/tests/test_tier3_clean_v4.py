"""PHASE-66 part 3: `clean-v4` as an opt-in normalizer (`NMOS_NORMALIZER`) that costs nothing to turn on.

Under the default every key, row and text is the base's. A switch either way is a carry-on for every model projection
(`generations.classify`: `carry`): only embeddings are made again, locally. Both normalizers' text is kept side by
side, a replay reads the normalizer its request was served from, and no excerpt is cut with another text's offsets.
"""

from __future__ import annotations

from uuid import UUID

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import active_generation, make_client
from nmos_sidecar import audit, config, generations, normtext, rebuild, retention, vectors
from nmos_sidecar.config import Settings
from nmos_sidecar.packet import clean_text, clean_text_v4
from nmos_sidecar.retrieval import RecallOptions
from simchat import SimChat
from test_canon import push
from test_canon_facts import Model, canon_texts
from test_generations import EMB, LLM, conv_id
from test_phase57_carry_on import drain, queued, served
from test_sidecar_integration import recall, sync
from test_vectors import FakeEmbedder, drain_embeddings

V4 = {"normalizer": "clean-v4"}
# Text the two normalizers read apart: Korean angle-bracket prose (clean-v3 drops it, clean-v4 keeps it), so every
# offset after it differs between the two texts.
ORACLE = "<신탁: 북쪽 등대로 가라> 하나는 은빛 열쇠를 등대 지하에 숨겼다. 그 비밀은 아무도 모른다."


@pytest.fixture(autouse=True)
def default_normalizer():
    """A client sets the process's normalizer; every test leaves the default behind it."""
    yield
    normtext.use(normtext.DEFAULT_NORMALIZER)


def kinds(db) -> dict[str, int]:
    return queued(db)


def oracle_chat(turns: int = 30) -> SimChat:
    chat = SimChat()
    chat.user("하나가 등대에 왔다.")
    chat.reply(ORACLE)
    for i in range(1, turns):
        chat.user(f"Turn {i} begins.")
        chat.reply(f"Reply {i} follows. More words here.")
    return chat


def played(migrated, c, chat: SimChat, model: Model | None = None) -> SimChat:
    sync(c, chat)
    push(c, chat, canon_texts())
    drain(migrated, model)
    drain_embeddings(migrated)
    return chat


def text_rows(db) -> dict[str, int]:
    return {r["normalizer"]: r["n"] for r in db.execute(
        "SELECT normalizer, count(*) AS n FROM revision_text GROUP BY normalizer").fetchall()}


def embedded_by(db, key: str) -> int:
    return db.execute("SELECT count(DISTINCT source_revision_id) AS n FROM revision_embedding WHERE projection = %s",
                      (key,)).fetchone()["n"]


def coverage(c, chat) -> dict:
    return c.get(f"/v1/conversations/{conv_id(c, chat)}/coverage").json()["extraction"]


# --- the setting ------------------------------------------------------------------------------------------------------


def test_the_setting_defaults_to_clean_v3_and_refuses_another_name(monkeypatch):
    monkeypatch.delenv("NMOS_NORMALIZER", raising=False)
    assert Settings().normalizer == "clean-v3"
    monkeypatch.setenv("NMOS_NORMALIZER", "")  # as the compose files pass an unset variable
    assert Settings().normalizer == "clean-v3"
    monkeypatch.setenv("NMOS_NORMALIZER", "clean-v4")
    assert Settings().normalizer == "clean-v4"
    monkeypatch.setenv("NMOS_NORMALIZER", "clean-v5")
    with pytest.raises(ValueError, match="NMOS_NORMALIZER"):
        Settings()
    assert config.NORMALIZERS == normtext.NORMALIZERS and normtext.NORMALIZERS[0] == normtext.DEFAULT_NORMALIZER
    with pytest.raises(ValueError):
        normtext.use("clean-v5")


def test_under_the_default_the_text_is_clean_text_and_every_key_is_the_base_key():
    normtext.use("clean-v3")
    for text in (ORACLE, "<table><tr><th>위치</th><td>북부 성채</td></tr></table>", "<reasoning>plan</reasoning>답",
                 "<think>생각\n\n본문", "<Quote>q</Quote>x", "plain text"):
        assert normtext.clean(text) == clean_text(text)
    s = Settings(**LLM, **EMB)
    pj = vectors.projection(s)
    # the key the base wrote: chunk-v1, no overlap field (as test_long_messages pins it)
    assert pj.key == generations.make("embed", EMB["embed_url"], EMB["embed_model"], normalizer="clean-v3",
                                      chunker="chunk-v1", chunk_chars=700, max_chunks=8, document_profile="plain").key
    assert "chunk_overlap" not in pj.spec


def test_under_clean_v4_the_projection_says_what_cut_its_chunks():
    normtext.use("clean-v4")
    assert normtext.clean(ORACLE) == clean_text_v4(ORACLE) != clean_text(ORACLE)
    pj = vectors.projection(Settings(**EMB))
    assert pj.spec["normalizer"] == "clean-v4" and pj.spec["chunker"] == "chunk-v2"
    assert pj.spec["chunk_overlap"] == vectors.CHUNK_OVERLAP == 100
    normtext.use("clean-v3")
    assert vectors.projection(Settings(**EMB)).key != pj.key


def test_the_config_says_which_normalizer_is_active(migrated):
    with make_client(migrated) as c:
        assert c.get("/v1/config").json()["extraction"]["normalizer"] == "clean-v3"
    with make_client(migrated, **V4) as c:
        assert c.get("/v1/config").json()["extraction"]["normalizer"] == "clean-v4"


# --- classify -------------------------------------------------------------------------------------------------------


def test_a_normalizer_only_change_is_its_own_carry_on_class(db, monkeypatch):
    def gen(normalizer="clean-v3", **spec):
        base = {"compiler": "extract-v20", "prompt": "p20", "normalizer": normalizer, "temperature": 0,
                "target_chars": 6000, "context_turns": 3}
        return generations.make("extract", LLM["llm_url"], spec.pop("model", "m"), **{**base, **spec})

    old = gen()
    generations.ensure(db, old)
    assert generations.classify(db, old.key, gen("clean-v4")) == "carry"
    assert generations.classify(db, old.key, gen("clean-v4", compiler="extract-v21", prompt="p21")) == "adds"
    assert generations.classify(db, old.key, gen("clean-v4", target_chars=36000)) == "reads"
    assert generations.classify(db, old.key, gen("clean-v4", model="m2")) == "model"
    # controls: a prompt or version change, another setting, or a normalizer outside the pair is still a version
    assert generations.classify(db, old.key, gen("clean-v4", prompt="p20b")) == "version"
    assert generations.classify(db, old.key, gen("clean-v4", context_turns=4)) == "version"
    assert generations.classify(db, old.key, gen("clean-v2")) == "version"
    assert generations.classify(db, old.key, gen("clean-v4", compiler="extract-v15", prompt="p15")) == "version"
    # a second carry-on field is one more entry (any value: None), absent from every earlier key
    assert generations.classify(db, old.key, gen(revision="r1")) == "version"
    monkeypatch.setitem(generations.CARRY_FIELDS, "revision", None)
    assert generations.classify(db, old.key, gen(revision="r1")) == "carry"
    assert generations.classify(db, old.key, gen("clean-v4", revision="r1")) == "carry"
    assert generations.classify(db, old.key, gen(revision="r1", prompt="p20b")) == "version"


# --- the switch, end to end -----------------------------------------------------------------------------------------


def test_switching_to_clean_v4_and_back_queues_embed_jobs_only(migrated, db):
    model = Model()
    with make_client(migrated, embedder=FakeEmbedder(), **LLM, **EMB) as c:
        chat = played(migrated, c, oracle_chat(), model)
        assert kinds(db) == {}
        before_cov, before_sum = coverage(c, chat), served(migrated, c, chat)
        assert before_sum["done"] == before_sum["due"] == 3 and before_sum["story_current"]
        old = {k: active_generation(db, k).key for k in ("extract", "summarize", "canon", "reveal", "embed")}
        texts = text_rows(db)["clean-v3"]
        embedded = embedded_by(db, old["embed"])
        calls = len(model.calls)

    with make_client(migrated, embedder=FakeEmbedder(), **LLM, **EMB, **V4) as c:
        now = {k: active_generation(db, k) for k in old}
        assert all(now[k].key != old[k] and now[k].spec["normalizer"] == "clean-v4" for k in old)
        assert kinds(db) == {"embed": embedded}  # every message embedded again, locally; nothing for a model
        assert text_rows(db) == {"clean-v3": texts, "clean-v4": texts}  # written beside, both kept
        cov = coverage(c, chat)  # every turn still served by what clean-v3 text gave, as after any carry-on
        assert before_cov["compiled"] == before_cov["eligible"] > 0 and before_cov["complete"]
        assert (cov["compiled"], cov["historical_only"], cov["pending"], cov["failed"]) == (0, cov["eligible"], 0, 0)
        assert cov["eligible"] == before_cov["eligible"]
        after = served(migrated, c, chat)
        assert [x["summary"]["id"] for x in after["scenes"]] == [x["summary"]["id"] for x in before_sum["scenes"]]
        assert after["story"]["id"] == before_sum["story"]["id"] and after["story_current"]
        assert drain(migrated, model) == 0 and len(model.calls) == calls

        # new work reads clean-v4 text
        chat.user("<시스템: 등대 불이 꺼졌다> 하나가 계단을 내려간다.")
        chat.reply("하나는 <마검 발뭉>을 들었다.")
        chat.user("그리고?")  # turn 30's reply is accepted once a message follows it
        sync(c, chat)
        assert set(kinds(db)) == {"extract", "embed"} and kinds(db)["extract"] == 2  # turns 29 and 30, no more
        drain(migrated, model)
        drain_embeddings(migrated)
        turns = [u for k, u in model.calls[calls:] if k == "turn"]
        assert len(model.calls) == calls + 2 and len(turns) == 2
        assert "TARGET turn 30" in turns[-1] and "<시스템: 등대 불이 꺼졌다>" in turns[-1] and "<마검 발뭉>" in turns[-1]
        texts = text_rows(db)["clean-v4"]
        unseen = embedded_by(db, now["embed"].key) - embedded_by(db, old["embed"])
        assert unseen > 0

    with make_client(migrated, embedder=FakeEmbedder(), **LLM, **EMB) as c:  # and back: clean-v3 serves again
        assert {k: active_generation(db, k).key for k in old} == old
        assert text_rows(db) == {"clean-v3": texts, "clean-v4": texts}
        assert kinds(db) == {"embed": unseen}  # the messages clean-v3's projection never saw, and nothing else
        assert drain(migrated, model) == 0 and len(model.calls) == calls + 2


def test_a_version_change_with_the_switch_still_re_extracts(migrated, db):
    with make_client(migrated, embedder=FakeEmbedder(), **LLM, **EMB) as c:
        played(migrated, c, oracle_chat(12))
    with make_client(migrated, embedder=FakeEmbedder(), **LLM, **EMB, **V4, extract_turns=4) as c:
        got = kinds(db)
        assert got.get("extract", 0) > 0  # context_turns is a version: the latest turns are read again


# --- mixed-normalizer chats and replays -----------------------------------------------------------------------------


def head_of(db) -> UUID:
    return db.execute("SELECT head_commit_id FROM conversation").fetchone()["head_commit_id"]


def test_a_vector_span_is_never_cut_from_the_other_normalizers_text(migrated, db):
    with make_client(migrated, embedder=FakeEmbedder(), **EMB) as c:
        sync(c, oracle_chat(3))
        drain_embeddings(migrated)
        v3 = active_generation(db, "embed").key
    qvec = FakeEmbedder().embed(["열쇠 숨기"], 1)[0]
    normtext.use("clean-v3")
    rows = vectors.vector_candidates(db, head_of(db), qvec, v3, -1)
    hit = next(r for r in rows if "열쇠" in r["clean"])
    assert hit["clean"] == clean_text(ORACLE) and "열쇠" in hit["clean"][hit["text_start"]:hit["text_end"]]
    normtext.backfill(db)
    normtext.use("clean-v4")
    normtext.backfill(db)
    assert vectors.vector_candidates(db, head_of(db), qvec, v3, -1) == []  # its spans index clean-v3's text
    with normtext.reading("clean-v3"):  # as a replay of a request served under clean-v3 reads
        assert vectors.vector_candidates(db, head_of(db), qvec, v3, -1) == rows


def test_clean_v4_chunks_overlap_and_index_clean_v4_text(migrated, db):
    long = "\n".join(f"<신탁: {i}번째 계시> 문장 {i}은 등대와 열쇠에 대한 이야기를 길게 이어간다." for i in range(60))
    chat = SimChat()
    chat.user("시작.")
    chat.reply(long)
    chat.user("다음.")  # the reply is accepted once the next message follows it
    with make_client(migrated, embedder=FakeEmbedder(), **EMB, **V4) as c:
        sync(c, chat)
        drain_embeddings(migrated)
        gen = active_generation(db, "embed")
    spans = db.execute("SELECT text_start, text_end FROM revision_embedding WHERE projection = %s AND chunk >= 0"
                       " AND source_revision_id = (SELECT source_revision_id FROM revision_text WHERE normalizer ="
                       " 'clean-v4' ORDER BY clean_chars DESC LIMIT 1) ORDER BY chunk", (gen.key,)).fetchall()
    text = clean_text_v4(long)
    assert [(r["text_start"], r["text_end"]) for r in spans] == vectors.chunks(text, overlap=100)
    assert len(spans) > 1 and all(b["text_start"] < a["text_end"] for a, b in zip(spans, spans[1:]))  # overlapped


def test_a_request_replays_as_the_normalizer_it_was_served_from(migrated, db):
    chat = oracle_chat(3)
    chat.user("그 열쇠 어디다 숨겼더라?")
    emb = FakeEmbedder()
    with make_client(migrated, embedder=emb, **EMB) as c:
        sync(c, chat)
        drain_embeddings(migrated)
        v3_key = active_generation(db, "embed").key
        served_v3 = recall(c, chat, "그 열쇠 어디다 숨겼더라?")
        assert "열쇠" in served_v3["packet"]["text"] and "신탁" not in served_v3["packet"]["text"]
    with make_client(migrated, embedder=emb, **EMB, **V4) as c:
        drain_embeddings(migrated)
        v4_key = active_generation(db, "embed").key
        served_v4 = recall(c, chat, "그 열쇠 어디다 숨겼더라?")
        assert "신탁" in served_v4["packet"]["text"]  # clean-v4 keeps the angle-bracket prose
        trace_v4 = db.execute("SELECT recall_options FROM retrieval_trace WHERE id = %s",
                              (served_v4["trace_id"],)).fetchone()["recall_options"]
        assert trace_v4["normalizer"] == "clean-v4"
        # a request served under clean-v3, replayed while clean-v4 is active, reads clean-v3 as it was served
        old = audit.replay(db, UUID(served_v3["trace_id"]), RecallOptions(embedder=emb, embed_projection=v3_key))
        assert old["reproduced"] is True and old["text"] == served_v3["packet"]["text"]
    with make_client(migrated, embedder=emb, **EMB) as c:  # and the other way around
        trace_v3 = db.execute("SELECT recall_options FROM retrieval_trace WHERE id = %s",
                              (served_v3["trace_id"],)).fetchone()["recall_options"]
        assert "normalizer" not in trace_v3  # the default is not recorded: its traces are the base's
        new = audit.replay(db, UUID(served_v4["trace_id"]), RecallOptions(embedder=emb, embed_projection=v4_key))
        assert new["reproduced"] is True and new["text"] == served_v4["packet"]["text"]
        assert normtext.active() == "clean-v3"


def test_excerpts_and_quotes_come_from_the_active_normalizers_text(migrated, db):
    chat = SimChat()
    chat.user("하나가 등대에 왔다.")
    chat.reply('<신탁: 북쪽 등대로 가라> 하나가 말했다. "열쇠는 등대 지하에 있어." 그리고 떠났다.')
    for i in range(1, 4):
        chat.user(f"Turn {i} begins.")
        chat.reply(f"Reply {i} follows.")
    chat.user("하나가 열쇠에 대해 뭐라고 말했지?")
    with make_client(migrated, embedder=FakeEmbedder(), **EMB, **V4, packet_policy="packet-v21") as c:
        sync(c, chat)
        drain_embeddings(migrated)
        out = recall(c, chat, "하나가 열쇠에 대해 뭐라고 말했지?")
    rows = db.execute("SELECT clean_content FROM revision_text WHERE normalizer = 'clean-v4'").fetchall()
    texts = [r["clean_content"] for r in rows]
    lines = [e for e in db.execute("SELECT lines FROM retrieval_trace WHERE id = %s",
                                   (out["trace_id"],)).fetchone()["lines"] if e["placed"]]
    cut = [e for e in lines if e["kind"] in ("excerpt", "quote")]
    assert cut, lines
    for e in cut:
        body = e.get("text") or ""
        words = [w for w in body.replace("…", " ").split() if len(w) > 1]
        assert any(all(w in t for w in words) for t in texts), (e, texts)


# --- retention and rebuild ------------------------------------------------------------------------------------------


def test_retention_keeps_both_normalizers_and_prunes_older_ones(migrated, db):
    with make_client(migrated) as c:
        sync(c, oracle_chat(2))
    n = text_rows(db)["clean-v3"]
    rid = db.execute("SELECT source_revision_id FROM revision_text LIMIT 1").fetchone()["source_revision_id"]
    db.execute("INSERT INTO revision_text (source_revision_id, normalizer, clean_content, original_chars, clean_chars)"
               " VALUES (%s, 'clean-v2', 'old', 3, 3)", (rid,))
    normtext.use("clean-v4")
    normtext.backfill(db)
    assert retention.prune_text(db) == 1  # clean-v2 only
    assert text_rows(db) == {"clean-v3": n, "clean-v4": n}
    normtext.use("clean-v3")
    assert retention.prune_text(db) == 0 and text_rows(db) == {"clean-v3": n, "clean-v4": n}


def test_rebuild_rewrites_both_normalizers_text(migrated, db):
    with make_client(migrated) as c:
        sync(c, oracle_chat(2))
    n = text_rows(db)["clean-v3"]
    db.execute("UPDATE revision_text SET clean_content = 'stale'")
    assert rebuild.rebuild_text(db) == {"clean-v3": n}  # no clean-v4 rows: none written
    normtext.use("clean-v4")
    normtext.backfill(db)
    db.execute("UPDATE revision_text SET clean_content = 'stale'")
    assert rebuild.rebuild_text(db) == {"clean-v4": n, "clean-v3": n}
    assert db.execute("SELECT count(*) AS n FROM revision_text WHERE clean_content = 'stale'").fetchone()["n"] == 0
    got = {r["normalizer"]: r["clean_content"] for r in db.execute(
        "SELECT normalizer, clean_content FROM revision_text rt JOIN source_revision sr ON sr.id = rt.source_revision_id"
        " WHERE sr.content = %s", (ORACLE,)).fetchall()}
    assert got == {"clean-v3": clean_text(ORACLE), "clean-v4": clean_text_v4(ORACLE)}

