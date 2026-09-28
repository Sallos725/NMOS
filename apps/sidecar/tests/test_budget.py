"""Phase 10, budget pressure (ADR 0036): packet-v4 leaves out restatements; a request reports the budget that
would hold every memory line it was offered."""

from __future__ import annotations

from nmos_sidecar.packet import FIT_CAP, Line, compile_lines, fits_at, restated
from test_packet_ledger import fact, full, story


def line(kind: str, n: int, head: str, value: str) -> Line:
    tag = "Claim" if kind == "claim" else "Fact"
    return Line(kind, f"    <{tag} turn=\"{n}\">{head}: {value}</{tag}>", {"assertion": n}, n, f"{head}: {value}", value)


def test_packet_v4_leaves_out_what_an_earlier_line_says_again():
    lines = [line("fact", 1, "{{user}} feels toward 블랑", "좋아함"),
             line("fact", 2, "블랑 feels toward {{user}}", "좋아함"),  # the other direction says something else
             line("claim", 3, "{{user}} feels toward 블랑", "정말 좋아함"),  # the narration already says it
             line("fact", 4, "{{user}} feels toward 블랑", "좋아함"),  # extracted again
             line("claim", 5, "라디아 goal", "온실 배양조 확인")]  # nothing states it
    assert {n: l.ref for n, l in restated(lines).items()} == {2: {"assertion": 1}, 3: {"assertion": 1}}
    v4 = compile_lines([], 600, facts=lines, policy="packet-v4")
    assert [(e["why"], e.get("restates")) for e in v4.ledger] == [
        ("placed", None), ("placed", None), ("restates", {"assertion": 1}), ("restates", {"assertion": 1}),
        ("placed", None)]
    assert v4.text.count("{{user}} feels toward 블랑") == 1
    v3 = compile_lines([], 600, facts=lines, policy="packet-v3")  # recorded traces replay as before
    assert all(e["placed"] for e in v3.ledger) and v3.text.count("{{user}} feels toward 블랑") == 3


def test_the_budget_that_holds_every_memory_line():
    facts = [fact(i) for i in range(12)]

    def at(budget: int):
        return compile_lines([], budget, facts=facts, policy="packet-v4")
    need = fits_at(at, 600)
    assert need is not None and need % 100 == 0 and need > 600
    assert all(e["placed"] for e in at(need).ledger) and not all(e["placed"] for e in at(need - 100).ledger)
    many = [fact(i) for i in range(200)]
    assert fits_at(lambda b: compile_lines([], b, facts=many, policy="packet-v4"), 600) is None  # beyond FIT_CAP
    assert FIT_CAP == 6000


def test_a_request_reports_memory_left_out_and_the_budget_for_it(full):
    client, url = full
    chat = story(client, url)
    chat.user("Hana, the map and the letter?")
    from memeval import _sync
    _sync(client, chat)
    small = client.post("/v1/retrieve", json={"chat_id": chat.id, "query": "Hana, the map and the letter?",
                                               "in_context_ids": [], "budget_tokens": 150}).json()
    assert small["memory"]["offered"] >= 2 and small["memory"]["cut"] >= 1
    fit = small["memory"]["fits_at"]
    assert fit is not None and fit > 150
    roomy = client.post("/v1/retrieve", json={"chat_id": chat.id, "query": "Hana, the map and the letter?",
                                               "in_context_ids": [], "budget_tokens": fit}).json()
    assert roomy["memory"] == {"offered": small["memory"]["offered"], "cut": 0, "fits_at": None}
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(url, row_factory=dict_row) as conn:
        traces = conn.execute("SELECT latency_ms FROM retrieval_trace ORDER BY created_at").fetchall()
    assert [(t["latency_ms"]["memory_cut"] > 0, t["latency_ms"]["fits_at"]) for t in traces[-2:]] == [(True, fit), (False, None)]
    conv = client.get("/v1/conversations").json()[0]["id"]
    assert f"(all at {fit})" in client.get(f"/inspector/c/{conv}", params={"lang": "en"}).text
