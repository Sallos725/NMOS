"""Synthetic isolation tests for K43; these are not the owner's S3 live evidence."""
from dataclasses import asdict, replace
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import UUID
from datetime import datetime, timezone

import pytest

from nmos_sidecar import facts, retrieval
from nmos_sidecar.packet import Excerpt
from test_semantics import row

spec = importlib.util.spec_from_file_location("diagnose_k43", Path(__file__).resolve().parents[3] /
                                              "tools/diagnose_k43.py")
diag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diag)
BOOK = "『북해 조류 일지』"
QUERY = "이안이 빌려준 책 제목이 뭐였지?"


def held(position, subject):
    return row(position, subject, "possesses", BOOK, subject_type="character", object_type="item",
               knowledge="public", known_by=[], hidden_from=[])


def test_historical_holder_is_not_an_independent_ranker_input():
    old, new = held(1, "백이안"), held(4, "서도윤")
    assert facts.version_key(old) == facts.version_key(new)
    (current,) = facts._versions([old, new])
    assert current["subject"] == "서도윤"
    assert current["history"][0]["subject"] == "백이안"
    assert current["history"][0]["outcome"] == "superseded"
    current["names"] = ["서도윤", BOOK]
    # A unique given-name variant can bring the old holder's fact before transfer.
    aliases = {"백이안": frozenset({"이안"})}
    assert facts.relevant_facts([old], QUERY, "", set(), 8, aliases=aliases) == [old]
    assert facts.relevant_facts([current], QUERY, "", set(), 8, aliases=aliases) == []


def test_admitting_current_holder_does_not_print_the_old_holder():
    (current,) = facts._versions([held(1, "백이안"), held(4, "서도윤")])
    assert facts.relevant_facts([current], BOOK, "", set(), 8) == [current]
    xml = facts.fact_line(current, before=True, marks=True)
    assert BOOK in xml and "서도윤" in xml and "백이안" not in xml
    assert facts.earlier(current, True) is None
    # Even an explicit first cue does not make possesses a STANDING history renderer.
    assert "possesses" not in facts.STANDING


def candidate(i, clean=None, **extra):
    return {"id": str(UUID(int=i)), "host_logical_id": f"m{i}", "position": i, "turn": i,
            "role": "char", "name": "백이안", "clean": clean or f"이안의 다른 장면 {i}.",
            "user_score": .8, "score": .8, **extra}


def gather(lexical, vector=(), top_k=5, in_context=()):
    opts = retrieval.RecallOptions(top_k=top_k, facts_limit=0, threads_limit=0, policy="packet-v11")
    with patch.object(retrieval, "_head_last", return_value=None), \
         patch.object(retrieval, "_cut", return_value=-1), \
         patch.object(retrieval, "_lexical", return_value=(lexical, "on")), \
         patch.object(retrieval, "_keyword_lexical", return_value=([], "none")), \
         patch.object(retrieval, "QueryEmbedding") as pending, \
         patch.object(retrieval, "vector_candidates", return_value=list(vector)):
        if vector:
            opts = replace(opts, embedder=object(), embed_projection="synthetic")
            pending.return_value.result.return_value = [1.0]
            pending.return_value.call_ms = 0
        return retrieval.gather(None, UUID(int=999), QUERY, "", set(in_context), opts), opts


def test_fusion_bar_is_separate_from_top_k():
    low = candidate(1, BOOK, user_score=.1)
    assert retrieval.fuse([low], [], .4, .42) == []
    assert retrieval.fuse([low], [], .4, .42, [{**low, "keyword_score": .8}])
    g, _ = gather([candidate(i) for i in range(2, 12)] + [candidate(1, BOOK)], top_k=10)
    assert any(c["id"] == candidate(1)["id"] for c in g.candidates)
    assert all(BOOK not in e.text for e in g.ranked)


def test_qualifying_vector_chunk_can_exclude_title_before_fitter():
    text = "이안은 책 이야기를 했습니다. " + BOOK + "를 도윤에게 빌려줬습니다."
    c = candidate(1, text)
    vector = {**c, "sim": .9, "text_start": 0, "text_end": text.index(BOOK)}
    g, _ = gather([c], [vector])
    assert BOOK in g.candidates[0]["clean"] and BOOK not in g.ranked[0].text
    assert BOOK not in retrieval.compile_gathered(g, 4000, "packet-v11").text


def test_correct_excerpt_can_be_cut_only_by_fitter():
    g, _ = gather([candidate(1, f"이안이 {BOOK}를 빌려줬습니다.")])
    assert BOOK in g.ranked[0].text
    small = retrieval.compile_gathered(g, 1, "packet-v11")
    assert small.ledger[0]["why"] == "budget" and not small.ledger[0]["placed"]
    assert BOOK in retrieval.compile_gathered(g, 4000, "packet-v11").text


def snapshot(g, opts, lexical, budget=4000, vector=()):
    c = retrieval.compile_gathered(g, budget, opts.policy)
    return {"mode": "synthetic", "trace": {"lines": []}, "stages": {
        "lexical": [lexical, "on"], "vector": list(vector), "effective_options": asdict(opts),
        "gathered": asdict(g)}, "replay": {"status": "ok", "text": c.text, "lines": c.ledger}}


@pytest.mark.parametrize("stage", ["fusion", "top_k", "span", "budget", "placed", "context", "absent"])
def test_report_separates_loss_stages(stage):
    c = candidate(1, f"이안이 {BOOK}를 빌려줬습니다.")
    lexical = [c]
    vector = []
    budget, top_k, context = 4000, 5, []
    expected = {"fusion": "fusion abstention", "top_k": "excerpt top_k", "span": "excerpt span/anchor/growth",
                "budget": "fitter: budget", "placed": "gold reached packet", "context": "already in host context",
                "absent": "absent from route outputs"}[stage]
    if stage == "fusion":
        lexical = [{**c, "user_score": .1}]
    elif stage == "top_k":
        lexical = [candidate(2), c]
        top_k = 1
    elif stage == "span":
        c = candidate(1, "이안은 다른 이야기를 했습니다. " + BOOK)
        lexical = [c]
        vector = [{**c, "sim": .9, "text_start": 0, "text_end": c["clean"].index(BOOK)}]
    elif stage == "budget":
        budget = 1
    elif stage == "context":
        context = [c["host_logical_id"]]
    elif stage == "absent":
        lexical = []
    g, opts = gather(lexical, vector, top_k, context)
    # Do not serialize a synthetic embedder object in the snapshot.
    opts = replace(opts, embedder=None)
    snap = snapshot(g, opts, lexical, budget, vector)
    snap["stages"]["gold_sources"] = [c]
    assert diag.report(snap)["passage_paths"][0]["stage"].startswith(expected)


def test_frozen_vector_refuses_wrong_generation_or_query():
    trace = {"query": QUERY, "embed_projection": "p", "recall_options": {"query_prefix": "prefix "}}
    payload = {"text": "prefix " + QUERY, "projection": "p", "vector": [1., 0.]}
    embedder = diag.FrozenEmbedder(payload, trace)
    assert embedder.embed([payload["text"]]) == [[1., 0.]]
    for bad in ({**payload, "projection": "other"}, {**payload, "text": QUERY},
                {**payload, "vector": [float("nan")]}):
        with pytest.raises(ValueError):
            diag.FrozenEmbedder(bad, trace)
    with pytest.raises(ValueError):
        embedder.embed(["different question"])


def test_invalid_replay_does_not_produce_a_cause():
    assert diag.report({"replay": {"status": "changed"}})["status"] == "changed"


def test_value_text_is_not_ignored():
    assert diag.contains({"object": None, "value": "이안이 " + BOOK + "를 빌려줬다"}, diag.GOLD)


def test_capture_uses_frozen_vector_and_records_actual_gather_and_fitter_without_http():
    c = candidate(1, f"이안이 {BOOK}를 도윤에게 빌려줬습니다.")
    vector_row = {**c, "sim": .9, "text_start": 0, "text_end": len(c["clean"])}
    trace = {"id": UUID(int=99), "conversation_id": UUID(int=98),
             "query": QUERY, "previous_ai": "", "in_context": [],
             "embed_projection": "p", "extractor_key": None, "rules_version": "none",
             "policy": "packet-v11", "budget_tokens": 4000, "upto_position": 8,
             "head_commit_id": UUID(int=999), "commit_id": UUID(int=999), "lines": [],
             "created_at": datetime.now(timezone.utc),
             "recall_options": {"facts_limit": 0, "threads_limit": 0, "query_prefix": "prefix "}}

    class Reader:
        def execute(self, sql, params):
            assert sql.startswith("SELECT ")
            return self

        def fetchall(self):
            return []

    with patch.object(diag.audit, "_trace", return_value=trace), \
         patch.object(retrieval, "_head_last", return_value=None), \
         patch.object(retrieval, "_cut", return_value=-1), \
         patch.object(retrieval, "_lexical", return_value=([c], "on")), \
         patch.object(retrieval, "_keyword_lexical", return_value=([], "none")), \
         patch.object(retrieval, "vector_candidates", return_value=[vector_row]), \
         patch("nmos_sidecar.llm.httpx.post", side_effect=AssertionError("no HTTP model calls")):
        snap = diag.capture(Reader(), trace["id"],
                            {"projection": "p", "text": "prefix " + QUERY, "vector": [1., 0.]})
        assert diag.report(snap)["packet_gold"]
        assert snap["stages"]["vector"] == [vector_row]
        assert snap["stages"]["gathered"]["ranked"]
        assert snap["stages"]["compiled"]["ledger"]
        # This deliberate different original ledger is correctly not claimed reproduced.
        assert snap["replay"]["reproduced"] is False
        with pytest.raises(ValueError, match="explicitly"):
            diag.capture(Reader(), trace["id"])


def test_a_probe_the_harness_deleted_is_replayed_as_the_probe():
    """The live gate sends each probe and deletes it: the plain replay reads `changed`; the capture then replays the
    trace's own query in its place (audit.replay's probe path), as on the gate's S3 database."""
    calls = []

    def replay(conn, trace_id, options, **kwargs):
        calls.append(kwargs)
        return {"status": "changed"} if not kwargs else {"status": "ok", "notes": ["query replaced"], "lines": [],
                                                         "text": ""}

    trace = {"id": "t", "query": QUERY, "head_commit_id": None, "upto_position": 0}
    with patch.object(diag.audit, "_trace", return_value=trace), patch.object(diag.audit, "replay", replay):
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = []
        snap = diag.capture(conn, UUID(int=1), lexical_only=True)
    assert calls == [{}, {"query": QUERY}] and snap["replay"]["status"] == "ok"

