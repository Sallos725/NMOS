"""K42 (ADR 0038 amendment 1): a standing fact's earlier versions are printed only under knowledge marks that cover them.

Since packet-v5 a relationship, feeling or form of address line names what it replaced and how it started, under the
current version's marks. A version kept from someone printed under a public line read as public. The rows are synthetic.
"""

from __future__ import annotations

from uuid import UUID

from memeval import _sync
from nmos_sidecar import audit
from nmos_sidecar.facts import fact_line, relevant_facts
from nmos_sidecar.retrieval import RecallOptions
from simchat import SimChat
from test_packet_ledger import db, extract, full  # noqa: F401  (`full` is a fixture)

PUBLIC = {"knowledge": "public", "known_by": None, "hidden_from": None}
SECRET = {"knowledge": "limited", "known_by": None, "hidden_from": ["리아"]}


def version(position, value, marks):
    return {"position": position, "turn": position // 2, "predicate": "relationship", "subject": "유이", "object": "하나",
            "value": value, "polarity": "positive", **marks}


def pair(*versions, current=PUBLIC, host="x"):
    """유이 and 하나's relationship: the given earlier versions, then '친구' at position 100 with `current` marks."""
    now = version(100, "친구", current)
    return {**now, "subject_type": "character", "object_type": "character", "epistemic": "stated", "salience": None,
            "host_logical_id": host, "history": [*versions, now]}


def test_a_version_kept_from_someone_is_not_printed_under_a_public_line():
    f = pair(version(10, "연인", SECRET))
    assert "연인" in fact_line(f, before=True)  # as before (packet-v5): it read as public
    line = fact_line(f, before=True, marks=True)
    assert "연인" not in line and 'knowledge="public"' in line


def test_a_version_with_the_line_marks_or_none_kept_is_printed():
    same = pair(version(10, "연인", SECRET), current=SECRET)
    assert "before, turn 5: 유이 relationship 하나: 연인" in fact_line(same, before=True, marks=True)
    wider = pair(version(10, "연인", PUBLIC), current=SECRET)  # a public version under a narrower line leaks nothing
    assert "연인" in fact_line(wider, before=True, marks=True)


def test_before_and_first_skip_a_version_the_line_does_not_cover():
    f = pair(version(4, "같은 반", PUBLIC), version(10, "연인", SECRET), version(20, "절교", PUBLIC))
    line = fact_line(f, before=True, marks=True)
    assert "before, turn 10: 유이 relationship 하나: 절교" in line and "first, turn 2: 유이 relationship 하나: 같은 반" in line
    assert "연인" not in line
    only = pair(version(4, "같은 반", PUBLIC), version(10, "연인", SECRET))
    line = fact_line(only, before=True, marks=True)
    assert "before, turn 2: 유이 relationship 하나: 같은 반" in line and "first," not in line and "연인" not in line


def test_the_first_cue_brings_a_fact_back_when_a_version_it_prints_started_before_the_window():
    # an earlier public version under a limited current one: printed with marks, so it counts (ADR 0056 item 3)
    known = {"knowledge": "limited", "known_by": ["리아"], "hidden_from": None}
    f = pair(version(10, "같은 반", PUBLIC), current=known, host="in-window")
    q = "유이랑 하나는 처음에 어떤 사이였지?"
    assert relevant_facts([f], q, "", {"in-window"}, 8, first_cue=True, window_start=50, marks=True) == [f]
    assert relevant_facts([f], q, "", {"in-window"}, 8, first_cue=True, window_start=50) == []  # recorded before
    hidden = pair(version(10, "연인", SECRET), host="in-window")
    assert relevant_facts([hidden], q, "", {"in-window"}, 8, first_cue=True, window_start=50, marks=True) == []


# --- through a request, and its replay ------------------------------------------------------------------------------

def secret_then_public(client, url) -> SimChat:
    chat = SimChat()
    chat.reply("Welcome to the story.")
    for user in ("Hana and Kaito secretly start dating, kept from Mina.", "Hana is Kaito's classmate.",
                 *[f"Idle chatter {i} about clouds." for i in range(3)]):
        chat.user(user)
        chat.reply("Noted.")
        _sync(client, chat)
    extract(url)
    return chat


def ask(client, chat: SimChat, text: str) -> dict:
    chat.user(text)
    _sync(client, chat)
    return client.post("/v1/retrieve", json={"chat_id": chat.id, "query": text, "previous_ai": "",
                                             "in_context_ids": [chat.messages[-1]["chatId"]],
                                             "budget_tokens": 1500}).json()


def test_a_request_leaves_out_the_secret_version_and_an_older_trace_replays_as_it_was(full):
    client, url = full
    chat = secret_then_public(client, url)
    out = ask(client, chat, "Hana and Kaito, how are they?")
    text = out["packet"]["text"]
    assert "classmate" in text and "lovers" not in text
    assert client.get(f"/v1/trace/{out['trace_id']}").json()["recall_options"]["history_marks"] is True
    with db(url) as conn:
        on = audit.replay(conn, UUID(out["trace_id"]), RecallOptions())
        conn.execute("UPDATE retrieval_trace SET recall_options = recall_options - 'history_marks' WHERE id = %s",
                     (out["trace_id"],))
        old = audit.replay(conn, UUID(out["trace_id"]), RecallOptions())
    assert on["reproduced"] is True and on["text"] == text
    assert "lovers" in old["text"]  # a request recorded before printed it, and replays so
