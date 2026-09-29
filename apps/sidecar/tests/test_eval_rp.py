"""M0, the RP evaluation (PHASE-11 step 2): a case replays a recorded request, scores what its packet holds and
keeps out, and the report carries numbers only (the owner's cases stay outside the repository)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from uuid import UUID

from nmos_sidecar import audit
from nmos_sidecar.retrieval import RecallOptions
from test_packet_ledger import ask, db, full, story  # noqa: F401  (`full` is a fixture)

TOOL = Path(__file__).resolve().parents[3] / "tools/eval_rp.py"
_spec = importlib.util.spec_from_file_location("eval_rp", TOOL)
eval_rp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eval_rp)


def test_a_case_passes_on_every_gold_phrase_in_any_wording_and_no_forbidden_one():
    packet = "<Fact>Hana knows: the letter is FORGED</Fact>\n<Excerpt>Idle   chatter about clouds.</Excerpt>"
    both = {"gold": ["letter is forged", ["위조", "idle chatter"]], "forbidden": ["dragon", "  "]}
    assert eval_rp.score(both, packet) == {"gold": 2, "held": 2, "in_prompt": 0, "forbidden": 1, "placed": 0,
                                           "passed": True, "needs_memory": True}
    assert eval_rp.score({"gold": ["forged", "dragon"]}, packet)["passed"] is False
    assert eval_rp.score({"gold": ["forged"], "forbidden": ["clouds"]}, packet) == {
        "gold": 1, "held": 1, "in_prompt": 0, "forbidden": 1, "placed": 1, "passed": False, "needs_memory": True}
    # packet-v5 names what a standing fact replaced: past, not current (ADR 0038)
    v5 = '<Fact kind="addresses" turn="35">노엘 addresses 타쿠미: 반말; before, turn 16: 노엘 addresses 타쿠미: 존댓말</Fact>'
    assert eval_rp.score({"gold": ["존댓말"], "forbidden": ["존댓말"]}, v5) == {
        "gold": 1, "held": 1, "in_prompt": 0, "forbidden": 1, "placed": 0, "passed": True, "needs_memory": True}
    # packet-v8's summaries tell the past: an answer there counts, an ended goal or an old event there is not current
    v8 = '<Story>\n    <Summary kind="story" turns="0–63">둘은 등대 문을 고쳤다.</Summary>\n  </Story>'
    assert eval_rp.score({"gold": ["등대 문"], "forbidden": ["등대 문"]}, v8)["passed"] is True
    # a gold answer in the messages the prompt already held counts, and says so; forbidden ones are the packet's only
    window = "…하나는 위조된 편지를 숨겼다…"
    assert eval_rp.score({"gold": ["위조된 편지"], "forbidden": ["위조된"]}, "<NarrativeMemory/>", window) == {
        "gold": 1, "held": 1, "in_prompt": 1, "forbidden": 1, "placed": 0, "passed": True, "needs_memory": False}


def test_a_probe_replaces_the_requests_message_as_the_live_request_would_send_it(full):
    client, url = full
    chat = story(client, url)
    out = ask(client, chat, "Kaito, what do you know about the letter?")
    with db(url) as conn:
        recorded = audit.replay(conn, UUID(out["trace_id"]), RecallOptions())
        probe = audit.replay(conn, UUID(out["trace_id"]), RecallOptions(), query="What about the clouds?")
    assert recorded["reproduced"] is True and "forged" in recorded["text"] and "clouds" not in recorded["text"]
    assert probe["notes"] == ["query replaced"] and "reproduced" not in probe
    assert "Idle chatter 0 about clouds." in probe["text"] and "forged" not in probe["text"]


def test_cases_replay_their_request_and_the_report_holds_numbers_only(full):
    client, url = full
    chat = story(client, url)
    trace = ask(client, chat, "Kaito, what do you know about the letter?")["trace_id"]
    cases = [
        {"name": "kept", "category": "secret", "trace": trace, "gold": ["the letter is forged"],
         "forbidden": ["about clouds"]},
        {"name": "missing-fact", "category": "state", "trace": trace, "gold": ["dragon"]},
        {"name": "probe", "category": "irrelevant", "trace": trace, "query": "What about the clouds?",
         "gold": ["chatter 0"], "forbidden": ["forged"]},
        {"name": "gone", "category": "state", "trace": "0190f3a4-1b2c-7d3e-8f40-123456789abc", "gold": ["x"]},
    ]
    with db(url) as conn:
        report = eval_rp.evaluate(conn, cases, RecallOptions())
    by = {r["name"]: r for r in report["cases"]}
    assert by["kept"]["passed"] and by["probe"]["passed"] and not by["missing-fact"]["passed"]
    assert by["gone"]["status"] == "missing"
    assert report["summary"]["all"] | {"tokens_mean": None} == {
        "cases": 4, "skipped": 1, "passed": 2, "memory_cases": 3, "memory_passed": 2, "gold": 3, "held": 2,
        "in_prompt": 0, "forbidden": 2, "placed": 0, "tokens_mean": None, "vectors": 0}
    assert report["summary"]["state"]["passed"] == 0 and report["summary"]["secret"]["passed"] == 1
    text = eval_rp.table(report)
    assert text.splitlines()[-1].startswith("| all | 4 | 2 | 2/3 | 2/3 | 0 | 0/2 | 1 |")
    assert text.splitlines()[-1].endswith("| 0/3 |")  # no case ran with vectors (PHASE-15 Q6)
    for phrase in ("forged", "dragon", "chatter", "clouds"):
        assert phrase not in text


def test_a_newer_extractor_generation_is_read_as_of_now(monkeypatch):
    """`--extractor`: the request is compiled with that generation's facts as extracted by now, not as of the request
    (which predates the generation), like `eval_secrets.py build`."""
    from datetime import datetime, timezone

    seen: list[dict] = []

    def replay(conn, trace_id, options, policy=None, known_at=None, query=None, budget=None, projection=None,
               **overrides):
        seen.append({"known_at": known_at, "query": query, "budget": budget, **overrides})
        return {"status": "ok", "text": "", "tokens": 0, "policy": policy or "packet-v4", "vectors": "off"}

    monkeypatch.setattr(eval_rp.audit, "replay", replay)
    monkeypatch.setattr(eval_rp, "prompt_window", lambda conn, trace: "")
    case = [{"name": "c", "trace": "0190f3a4-1b2c-7d3e-8f40-123456789abc", "query": "probe"}]
    eval_rp.evaluate(None, case, RecallOptions())
    eval_rp.evaluate(None, case, RecallOptions(), extractor="extract-new", budget=800)
    assert seen[0] == {"known_at": None, "query": "probe", "budget": None}
    assert seen[1]["extractor_key"] == "extract-new" and seen[1]["query"] == "probe" and seen[1]["budget"] == 800
    assert abs((datetime.now(timezone.utc) - seen[1]["known_at"]).total_seconds()) < 60


def test_each_case_says_whether_vectors_ran_and_a_named_projection_is_searched(monkeypatch):
    """PHASE-15 Q6: `--projection` reaches every replay with a timeout for its query, and each case reports whether
    vector search ran."""
    seen: list[dict] = []

    def replay(conn, trace_id, options, policy=None, known_at=None, query=None, budget=None, projection=None,
               **overrides):
        seen.append({"projection": projection, **overrides})
        return {"status": "ok", "text": "", "tokens": 0, "policy": "packet-v8",
                "vectors": "on" if query == "a" else "fallback: timed out"}

    monkeypatch.setattr(eval_rp.audit, "replay", replay)
    monkeypatch.setattr(eval_rp, "prompt_window", lambda conn, trace: "")
    cases = [{"name": n, "trace": "0190f3a4-1b2c-7d3e-8f40-123456789abc", "query": n} for n in ("a", "b")]
    opts = RecallOptions(embedder=object(), embed_projection="embed-x")
    report = eval_rp.evaluate(None, cases, opts, projection="embed-x", embed_timeout_ms=5000)
    assert seen == [{"projection": "embed-x", "embed_timeout_ms": 5000}] * 2
    assert [c["vectors"] for c in report["cases"]] == [True, False] and report["summary"]["all"]["vectors"] == 1
    # without an embedder the timeout is not touched (a lexical run)
    seen.clear()
    eval_rp.evaluate(None, cases[:1], RecallOptions(), embed_timeout_ms=5000)
    assert seen == [{"projection": None}]
