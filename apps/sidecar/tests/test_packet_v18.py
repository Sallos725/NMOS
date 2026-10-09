"""PHASE-40: the opt-in persona route through sync, fact selection, trace and replay."""
from __future__ import annotations

import uuid

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import make_client
from nmos_sidecar import packet
from nmos_sidecar.entities import resolve
from nmos_sidecar.retrieval import persona_question_names
from simchat import SimChat
from test_semantics import row
from test_sidecar_integration import sync


def test_v18_inherits_v17_without_changing_the_default():
    assert packet.DEFAULT_POLICY == "packet-v16"
    assert "packet-v18" in packet.POLICIES
    for name, policies in vars(packet).items():
        if name.endswith("_POLICIES") and "packet-v17" in policies:
            assert "packet-v18" in policies, name
    # State history and hidden provenance must survive the new policy registration.
    old = packet.compile_lines([], 600, state=[packet.StateItem(
        key="Level", value="3", turn=2, history=((1, "2"), (2, "3")))], policy="packet-v17")
    new = packet.compile_lines([], 600, state=[packet.StateItem(
        key="Level", value="3", turn=2, history=((1, "2"), (2, "3")))], policy="packet-v18")
    assert (new.text, new.tokens, new.ledger) == (old.text, old.tokens, old.ledger)


@pytest.mark.parametrize("other,kind", [(None, "character"), ("김서윤", "character"),
                                       ("서윤", "character"), ("서윤", "place")])
def test_question_only_given_name_abstains_on_another_owner(other, kind):
    rows = [row(1, "한서윤", "identity", None, "astronomer", subject_type="character")]
    if other:
        rows.append(row(2, other, "has_trait", None, "quiet", subject_type=kind))
    resolution = resolve(uuid.uuid4(), rows, persona=["한서윤"])
    original = resolution.persona_names
    assert ("서윤" in persona_question_names(resolution)) is (other is None)
    assert resolution.persona_names == original  # no ordinary mention or stored alias expansion


@pytest.mark.parametrize("policy,expected", [("packet-v17", False), ("packet-v18", True)])
@pytest.mark.parametrize("source_kind,persona,query,value", [
    ("narration", "타쿠미", "타쿠미는 무슨 일을 해?", "astronomer"),
    ("character_claim", "한서윤", "서윤이 다니는 회사 이름이 뭐였더라?", "Aster 회사 직원"),
])
def test_persona_question_reaches_a_provenanced_fact_and_replays(migrated, policy, expected,
                                                               source_kind, persona, query, value):
    with make_client(migrated, packet_policy=policy, llm_url="http://unused.invalid/v1",
                     llm_model="synthetic", summaries=False, canon_facts=False) as client:
        chat = SimChat()
        chat.user("Begin the story.")
        chat.reply("The persona works as an astronomer.")
        for _ in range(5):
            chat.user("Continue.")
            chat.reply("Clouds pass above the mountains.")
        chat.user(query)
        sync(client, chat, persona_name=persona)
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            gen = conn.execute("SELECT key FROM projection_generation WHERE kind='extract'").fetchone()
            source = conn.execute(
                "SELECT am.source_revision_id AS rid, am.turn_hash, sr.content"
                " FROM active_membership am JOIN source_revision sr ON sr.id=am.source_revision_id"
                " JOIN conversation c ON c.head_commit_id=am.commit_id"
                " WHERE c.host_chat_ref=%s AND sr.content=%s",
                (chat.id, "The persona works as an astronomer.")).fetchone()
            extraction = uuid.uuid4()
            conn.execute("INSERT INTO extraction(id,source_revision_id,window_hash,compiler_version,model,raw,"
                         "extractor_key) VALUES(%s,%s,%s,'extract-v16','synthetic','{}',%s)",
                         (extraction, source["rid"], source["turn_hash"], gen["key"]))
            assertion = conn.execute(
                "INSERT INTO assertion(extraction_id,source_revision_id,subject,subject_type,predicate,value,"
                "evidence,status,source,asserted_by) VALUES(%s,%s,'{{user}}','character','identity',%s,%s,"
                "'valid',%s,%s) RETURNING id",
                (extraction, source["rid"], value, source["content"], source_kind,
                 "{{user}}" if source_kind == "character_claim" else None)).fetchone()["id"]
        out = client.post("/v1/retrieve", json={"chat_id": chat.id, "query": query, "previous_ai": "",
                          "budget_tokens": 1200, "in_context_ids": []})
        assert out.status_code == 200
        trace_id = out.json()["trace_id"]
        trace = client.get(f"/v1/trace/{trace_id}").json()
        kind = "claim" if source_kind == "character_claim" else "fact"
        picked = [e for e in trace["lines"] if e["kind"] == kind
                  and e["ref"].get("assertion") == assertion and e["placed"]]
        assert bool(picked) is expected
        if expected:
            assert picked[0]["label"] == "required"
        assert trace["policy"] == policy
        again = client.get(f"/v1/trace/{trace_id}/replay").json()
        assert again["reproduced"] is True
        # Editing away the evidence invalidates the new route synchronously too.
        chat.edit(1, "The earlier statement was replaced by unrelated scenery.")
        sync(client, chat, persona_name=persona)
        fresh = client.post("/v1/retrieve", json={"chat_id": chat.id, "query": query, "previous_ai": "",
                            "budget_tokens": 1200, "in_context_ids": []}).json()
        after = client.get(f"/v1/trace/{fresh['trace_id']}").json()
        assert not any(e["ref"].get("assertion") == assertion for e in after["lines"])
