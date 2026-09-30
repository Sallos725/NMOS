"""PHASE-18 step 3 (ADR 0052): the keyword route beside whole-message lexical recall."""

from __future__ import annotations

from uuid import UUID

from nmos_sidecar import audit
from nmos_sidecar.retrieval import RecallOptions
from simchat import SimChat
from test_packet_ledger import ask, db, full, story  # noqa: F401  (`full` is a fixture)
from test_sidecar_integration import recall, sync


# A question whose other words dilute the whole-message score under the 0.4 bar (D15); "parrot" alone matches.
QUESTION = "Hey, I forgot something from way back when we first met: what did everyone call that old bird on the ship, the parrot?"


def parrot_chat() -> SimChat:
    chat = SimChat()
    chat.user("Let us begin.")
    chat.reply("Captain Mujin keeps a green parrot. The parrot is named Pepper.")
    for i in range(8):
        chat.user(f"Idle chatter {i} about the harbor.")
        chat.reply(f"Idle reply {i} about the harbor.")
    chat.user("next")
    return chat


def trace(client, out) -> dict:
    return client.get(f"/v1/trace/{out['trace_id']}").json()


def test_a_keyword_finds_what_the_whole_question_misses_without_vectors(client):
    chat = parrot_chat()
    sync(client, chat)
    out = recall(client, chat, QUESTION, in_context=[])
    t = trace(client, out)
    assert t["latency_ms"]["keyword_mode"] == "on" and "Pepper" in out["packet"]["text"]
    hit = next(c for c in t["candidates"] if c["keyword_score"] > 0)
    assert hit["user_score"] < 0.4 and hit["sim"] is None  # under the whole-message bar, no vectors: kept all the same


def test_a_word_in_most_messages_is_too_broad(client):
    chat = parrot_chat()
    sync(client, chat)
    out = recall(client, chat, "harbor", in_context=[])
    assert trace(client, out)["latency_ms"]["keyword_mode"] == "too_broad"


def test_a_message_found_by_both_routes_is_one_candidate(client):
    chat = parrot_chat()
    sync(client, chat)
    out = recall(client, chat, "The parrot is named Pepper?", in_context=[])
    ids = [c["revision_id"] for c in trace(client, out)["candidates"]]
    assert len(ids) == len(set(ids)) and out["packet"]["text"].count("named Pepper") == 1


def test_a_trace_from_before_the_keyword_route_replays_without_it(client, migrated):
    chat = parrot_chat()
    sync(client, chat)
    out = recall(client, chat, QUESTION, in_context=[])
    with db(migrated) as conn:
        now = audit.replay(conn, UUID(out["trace_id"]), RecallOptions())
        assert now["keywords"] == "on" and "Pepper" in now["text"]
        conn.execute("UPDATE retrieval_trace SET recall_options = recall_options - 'lexical_keywords' WHERE id = %s",
                     (out["trace_id"],))
        old = audit.replay(conn, UUID(out["trace_id"]), RecallOptions())
    assert old["keywords"] == "off" and "Pepper" not in old["text"]


def test_an_excerpt_only_a_keyword_found_is_left_out_when_it_repeats_a_secret(full):
    client, url = full
    chat = story(client, url)  # "Hana keeps a secret from Kaito: the letter is forged."
    out = ask(client, chat, "Kaito, anything new?")
    t = client.get(f"/v1/trace/{out['trace_id']}").json()
    assert t["latency_ms"]["keyword_withheld"] >= 1
    assert not any("forged" in line for line in out["packet"]["text"].splitlines() if "<Excerpt" in line)
