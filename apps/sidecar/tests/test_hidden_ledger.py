"""PHASE-34 Hidden: diagnostic provenance without changing offered memory or disclosing withheld text."""
from __future__ import annotations

from copy import deepcopy

import pytest

from nmos_sidecar import audit, overuse, retrieval, summaries
from nmos_sidecar.inspector import chip
from nmos_sidecar.packet import Excerpt, Line, kept_counts
from nmos_sidecar.retrieval import Gathered, RecallOptions, _moded, compile_gathered
from test_packet_ledger import full  # noqa: F401 (fixture)

SECRET = "private-original-body-should-not-be-copied"


def line(n: int, private: bool = False) -> Line:
    return Line("fact", f"<Fact>{SECRET if private else 'public memory'}</Fact>", {"assertion": n}, n,
                SECRET if private else "public memory", SECRET if private else "public memory",
                {"hidden_from": ["Kaito"]} if private else {}, private=private)


def dropped(monkeypatch, policy: str) -> Gathered:
    monkeypatch.setattr(retrieval.scene, "narrator_knows", lambda row, *_: row["id"] != 1)
    g = Gathered()
    g.facts = _moded([line(1, True), line(2)], [{"id": 1}, {"id": 2}], g, None,
                     RecallOptions(policy=policy, narrator="Kaito"))
    g.ranked = [Excerpt(turn=3, speaker="user", text="ordinary visible excerpt", score=1, revision_id="visible")]
    return g


@pytest.mark.parametrize("policy", ["packet-v14", "packet-v15", "packet-v16", "packet-v17", "packet-v18"])
@pytest.mark.parametrize("budget", [0, 10, 600])
def test_hidden_provenance_never_changes_packet_budget_or_rest(monkeypatch, policy, budget):
    g = dropped(monkeypatch, policy)
    baseline = Gathered(facts=g.facts, ranked=g.ranked)
    before = compile_gathered(baseline, budget, policy)
    result = compile_gathered(g, budget, policy)
    hidden = [e for e in result.ledger if e.get("label") == "hidden"]
    assert len(hidden) == 1
    assert hidden[0]["kind"] == "fact" and hidden[0]["ref"] == {"assertion": 1} and hidden[0]["turn"] == 1
    assert hidden[0]["why"] == "mode_withheld" and hidden[0]["tok"] == 0 and not hidden[0]["placed"]
    assert hidden[0]["text"] == "" and "content" not in hidden[0] and "marks" not in hidden[0]
    assert SECRET not in str(result.ledger) and SECRET not in result.text
    assert (result.text, result.tokens, result.excerpts) == (before.text, before.tokens, before.excerpts)
    assert kept_counts(result.ledger) == kept_counts(before.ledger)
    assert retrieval.rested(g, result) == retrieval.rested(baseline, before)
    assert retrieval.below_floor(g, result) == retrieval.below_floor(baseline, before)
    assert overuse.of_ledger(result.ledger, SECRET, ("", "")) == overuse.of_ledger(before.ledger, SECRET, ("", ""))
    assert compile_gathered(g, budget, policy).ledger == result.ledger  # fit compiles do not accumulate rows


@pytest.mark.parametrize("policy", ["packet-v12", "packet-v13"])
def test_pre_label_policies_keep_their_original_ledger(monkeypatch, policy):
    g = dropped(monkeypatch, policy)
    before = compile_gathered(Gathered(facts=g.facts, ranked=g.ranked), 600, policy)
    assert compile_gathered(g, 600, policy) == before


def test_strict_secret_placeholder_and_hidden_original_are_distinct(monkeypatch):
    monkeypatch.setattr(retrieval.scene, "missing", lambda *_: (["Hana"], ["Kaito"]))
    g = Gathered()
    g.facts = _moded([line(1, True)], [{"id": 1}], g, object(), RecallOptions(strict=True))
    result = compile_gathered(g, 600, "packet-v16")
    secret = next(e for e in result.ledger if e["kind"] == "secret")
    hidden = next(e for e in result.ledger if e.get("label") == "hidden")
    assert secret["placed"] and secret["label"] == "required"
    assert secret["ref"] == hidden["ref"] == {"assertion": 1}
    assert hidden["kind"] == "fact" and not hidden["placed"]
    assert "<Secret" in result.text and SECRET not in result.text and SECRET not in str(result.ledger)


def test_cast_preselection_does_not_duplicate_or_label_unoffered_private_rows():
    from uuid import uuid4
    from nmos_sidecar.entities import resolve
    from nmos_sidecar.facts import fact_entry
    from test_semantics import row

    offered = row(1, "Hana", "has_status", None, SECRET, subject_type="character",
                  knowledge="limited", known_by=["Hana"], hidden_from=["Kaito"])
    irrelevant = row(2, "Other", "has_status", None, "unoffered private state", subject_type="character",
                     knowledge="limited", known_by=["Other"], hidden_from=["Kaito"])
    public = row(3, "Kaito", "has_status", None, "awake", subject_type="character")
    r = resolve(uuid4(), [offered, irrelevant, public])
    cast = retrieval.scene.cast([offered, public], r, "Hana and Kaito", "", 3)
    options = RecallOptions(strict=True)
    groups, _ = retrieval.cast_groups({"facts": [offered, irrelevant, public], "threads": []}, cast, r,
                                      "Hana and Kaito", options)
    g = Gathered(cast=cast, cast_lines=groups)
    g.facts = _moded([fact_entry(offered, private=True)], [offered, irrelevant, public], g, r, options)
    result = compile_gathered(g, 600, options.policy)
    hidden = [e for e in result.ledger if e.get("label") == "hidden"]
    assert len(hidden) == 1 and hidden[0]["ref"] == {"assertion": offered["id"]}
    assert not any(e["ref"].get("assertion") == irrelevant["id"] for e in result.ledger)


def test_audit_hidden_rows_do_not_count_as_offers_echo_or_excerpt_candidates(monkeypatch):
    g = dropped(monkeypatch, "packet-v16")
    result = compile_gathered(g, 600, "packet-v16")
    visible = [e for e in result.ledger if e.get("label") != "hidden"]
    row = {"id": "t", "policy": "packet-v16", "budget_tokens": 600, "token_estimate": result.tokens,
           "lines": result.ledger, "query": "", "previous_ai": ""}
    monkeypatch.setattr(audit, "_trace", lambda *_: row)
    monkeypatch.setattr(audit, "reply_after", lambda *_: ("ok", "public memory and " + SECRET))
    got = audit.audit(None, "t")
    row["lines"] = visible
    baseline = audit.audit(None, "t")
    assert got["summary"] == baseline["summary"]
    hidden = next(e for e in got["lines"] if e.get("label") == "hidden")
    assert "echo" not in hidden and "echoed" not in hidden
    assert audit._same(result.ledger, deepcopy(result.ledger))
    assert not audit._same(result.ledger, visible)  # legacy ledger changed, not a different placed packet
    assert "숨김" in chip("ko", "lb", "hidden") and "hidden" in chip("en", "lb", "hidden")


def test_summary_diagnostics_preserve_selection_and_read_order(monkeypatch):
    rows = [{"id": n, "level": "scene", "first_turn": n, "last_turn": n,
             "window_last": n, "before": 10} for n in range(1, 5)]
    rows.append({"id": 5, "level": "story", "first_turn": 0, "last_turn": 4, "text": SECRET})
    monkeypatch.setattr(summaries, "_scene_grams", lambda *_: {n: {str(n)} for n in range(1, 5)})
    monkeypatch.setattr(summaries, "_overlap", lambda _, grams: {"1": .9, "2": .8, "3": .7, "4": 0}[next(iter(grams))])
    held_calls = []
    monkeypatch.setattr(summaries, "held", lambda row, *_: held_calls.append(row["id"]) or row["id"] in (1, 5))

    class Result:
        def __init__(self, value):
            self.value = value

        def fetchall(self):
            return deepcopy(self.value)

        def fetchone(self):
            return deepcopy(self.value)

    class Connection:
        def __init__(self):
            self.reads = []

        def execute(self, query, params):
            if query == summaries._CURRENT:
                return Result(rows)
            self.reads.append(params[0])
            return Result({"text": SECRET if params[0] == 1 else "ordinary summary", "coverage": []})

    before_conn, after_conn = Connection(), Connection()
    before = summaries.packet_lines(before_conn, None, "key", [{}], "query", set())
    before_held = list(held_calls)
    held_calls.clear()
    diagnostics = []
    after = summaries.packet_lines(after_conn, None, "key", [{}], "query", set(), hidden_entries=diagnostics)
    assert after == before and before_conn.reads == after_conn.reads == [1, 2]
    assert before_held == held_calls == [5, 1, 2]
    assert [e["ref"] for e in diagnostics] == [{"summary": "5"}, {"summary": "1"}]
    assert all(e["why"] == "secret_gate" and e["label"] == "hidden" for e in diagnostics)
    assert SECRET not in str(diagnostics)
    # After the first accepted scene (3) and irrelevant scenes (4) were never evaluated or labeled.
    assert after[0].ref == {"summary": "2"}


def test_mode_hidden_trace_replays_after_source_edit_and_mode_change(migrated, db):
    from conftest import make_client
    from test_generations import LLM, conv_id
    from test_scene import _complete, _secret_chat
    from test_sidecar_integration import recall, sync

    with make_client(migrated, **LLM) as client:
        chat = _secret_chat(migrated, client, _complete)
        cid = conv_id(client, chat)
        client.put(f"/v1/conversations/{cid}/memory-mode", json={"strict": True})
        out = recall(client, chat, "루카와 작전을 짠다", in_context=[])
        trace = client.get(f"/v1/trace/{out['trace_id']}").json()
        hidden = [e for e in trace["lines"] if e.get("label") == "hidden"]
        assert {e["kind"] for e in hidden} == {"thread", "excerpt"}  # a goal is offered as a thread
        assert len(hidden) == trace["latency_ms"]["memory_mode_withheld"]
        assert all(e["why"] == "mode_withheld" and not e["placed"] and e["tok"] == 0 for e in hidden)
        assert "엄마 몰래 수업 보기" not in str(hidden)
        assert len({(e["kind"], str(e["ref"])) for e in hidden}) == len(hidden)
        placeholder = next(e for e in trace["lines"] if e["kind"] == "secret")
        assert placeholder["placed"] and any(e["ref"] == placeholder["ref"] for e in hidden)
        from nmos_sidecar.packet import MEMORY_KINDS
        assert out["memory"]["offered"] == sum(1 for e in trace["lines"] if e["kind"] in MEMORY_KINDS
                                              and e["why"] != "restates" and e.get("label") != "hidden")
        page = client.get(f"/inspector/c/{cid}", params={"lang": "ko"}).text
        assert "숨김" in page and "기억 모드로 제외" in page
        assert client.get(f"/v1/trace/{out['trace_id']}/replay").json()["reproduced"] is True
        # Later host text and the current mode change, but the recorded prefix and mode still replay exactly.
        chat.reply("루카는 방으로 들어갔다.")
        sync(client, chat)
        chat.messages[-1]["data"] = "노엘이 방으로 들어갔다."
        sync(client, chat)
        client.put(f"/v1/conversations/{cid}/memory-mode", json={"strict": False, "narrator": "{{user}}"})
        replay = client.get(f"/v1/trace/{out['trace_id']}/replay").json()
        assert replay.get("reproduced") is True and replay["lines"] == trace["lines"], replay
        # An old ledger lacking diagnostics is honestly different, while its packet remains identical.
        legacy = [e for e in trace["lines"] if e.get("label") != "hidden"]
        from psycopg.types.json import Jsonb
        db.execute("UPDATE retrieval_trace SET lines = %s WHERE id = %s", (Jsonb(legacy), out["trace_id"]))
        old = client.get(f"/v1/trace/{out['trace_id']}/replay").json()
        assert old["reproduced"] is False and old["text"] == replay["text"]
        # Editing the recorded prefix keeps the existing refusal contract; it must not pretend to reproduce.
        chat.messages[0]["data"] = "루카와 공개 계획을 짠다."
        sync(client, chat)
        changed = client.get(f"/v1/trace/{out['trace_id']}/replay").json()
        assert changed["status"] == "changed" and "reproduced" not in changed


def test_narrator_hidden_only_response_offers_no_memory(migrated):
    from conftest import make_client
    from test_generations import LLM, conv_id
    from test_scene import _complete, _secret_chat
    from test_sidecar_integration import recall

    with make_client(migrated, **LLM) as client:
        chat = _secret_chat(migrated, client, _complete)
        cid = conv_id(client, chat)
        client.put(f"/v1/conversations/{cid}/memory-mode", json={"narrator": "노엘"})
        out = recall(client, chat, "루카, 수업 작전 기억나?", in_context=[])
        trace = client.get(f"/v1/trace/{out['trace_id']}").json()
        assert out["packet"]["text"] == "" and out["packet"]["token_estimate"] == 0
        assert out["memory"] == {"offered": 0, "cut": 0, "fits_at": None}
        assert trace["lines"] and all(e["label"] == "hidden" for e in trace["lines"])
        assert client.get(f"/v1/trace/{out['trace_id']}/replay").json()["reproduced"] is True


def test_real_summary_secret_gate_records_redacted_provenance(migrated, db):
    from conftest import make_client
    from test_summaries import ON, ask, lighthouse_chat, story_setup, stub
    from test_sidecar_integration import sync

    def leaky(system, user):
        if system == summaries.STORY_PROMPT:
            return {"summary": "Hana read it: the letter is forged."}, "{}"
        return stub(system, user)

    with make_client(migrated, **ON, extract_backfill=100) as client:
        chat = lighthouse_chat()
        sync(client, chat)
        story_setup(migrated, chat, leaky)
        packet = ask(client, chat, "Kaito, anything new?")
        assert '<Summary kind="story"' not in packet["text"]
        trace_id = db.execute("SELECT id FROM retrieval_trace ORDER BY created_at DESC LIMIT 1").fetchone()["id"]
        trace = client.get(f"/v1/trace/{trace_id}").json()
        hidden = [e for e in trace["lines"] if e.get("label") == "hidden" and e["kind"] == "summary"]
        assert hidden and all(e["why"] == "secret_gate" and "summary" in e["ref"] for e in hidden)
        assert "forged" not in str(hidden)
        assert client.get(f"/v1/trace/{trace_id}/replay").json()["reproduced"] is True


def test_keyword_secret_gate_records_only_redacted_excluded_excerpt(full):
    from test_packet_ledger import ask, story

    client, url = full
    chat = story(client, url)
    out = ask(client, chat, "Kaito, anything new?")
    trace = client.get(f"/v1/trace/{out['trace_id']}").json()
    hidden = [e for e in trace["lines"] if e.get("label") == "hidden"]
    assert len(hidden) == trace["latency_ms"]["keyword_withheld"] >= 1
    assert all(e["kind"] == "excerpt" and e["why"] == "secret_gate" and "revision" in e["ref"] for e in hidden)
    assert "forged" not in str(hidden)
    assert client.get(f"/v1/trace/{out['trace_id']}/replay").json()["reproduced"] is True


def test_quote_secret_gate_records_redacted_quote(migrated):
    from conftest import make_client
    from memeval import RECENT, _sync, settings_for
    from simchat import SimChat
    from test_packet_ledger import extract

    settings = ({k: v for k, v in settings_for("full").items() if not k.startswith("embed_")}
                | {"embed_backfill": 0, "packet_policy": "packet-v16"})
    with make_client(migrated, **settings) as client:
        chat = SimChat()
        chat.reply("Welcome to the story.")
        chat.user("Hana keeps a secret from Kaito: the letter is forged.")
        chat.reply("Noted.")
        chat.user('Hana whispered "burn it, the letter is forged".')
        chat.reply("Noted.")
        for i in range(RECENT + 2):
            chat.user(f"Idle chatter {i} about clouds.")
            chat.reply("Noted.")
        _sync(client, chat)
        extract(migrated)
        question = "Kaito here. What was said on turn 2?"
        chat.user(question)
        _sync(client, chat)
        out = client.post("/v1/retrieve", json={"chat_id": chat.id, "query": question, "previous_ai": "",
                                                "budget_tokens": 600,
                                                "in_context_ids": [m["chatId"] for m in chat.messages[-RECENT:]]}).json()
        trace = client.get(f"/v1/trace/{out['trace_id']}").json()
        hidden = [e for e in trace["lines"] if e.get("label") == "hidden" and e["kind"] == "quote"]
        assert len(hidden) == trace["latency_ms"]["quote_withheld"] >= 1
        assert all(e["why"] == "secret_gate" and e["text"] == "" for e in hidden)
        assert "forged" not in str(hidden)
        assert client.get(f"/v1/trace/{out['trace_id']}/replay").json()["reproduced"] is True
