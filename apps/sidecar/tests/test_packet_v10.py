"""PHASE-18 step 4 (ADR 0053): packet-v10's excerpts grow to the length the budget gives them."""

from __future__ import annotations

from nmos_sidecar.packet import MAX_EXCERPT_CHARS, excerpt, grown_excerpt
from simchat import SimChat
from test_sidecar_integration import recall, sync

S = ["One.", "Two two.", "The parrot squawks.", "The captain calls it Pepper.", "Five five.", "Six six six."]
MSG = " ".join(S)


def test_it_starts_from_the_sentence_holding_most_keywords_and_adds_after_then_before():
    text, short = grown_excerpt(MSG, "what is the parrot called", ["parrot"], max_chars=len(" ".join(S[2:4])))
    assert short == "…The parrot squawks.…" and text == "…The parrot squawks. The captain calls it Pepper.…"
    text, _ = grown_excerpt(MSG, "what is the parrot called", ["parrot"], max_chars=len(" ".join(S[1:4])))
    assert text == "…Two two. The parrot squawks. The captain calls it Pepper.…"  # after, then before


def test_it_stops_at_a_sentence_within_its_length_and_at_four_sentences():
    text, _ = grown_excerpt(MSG, "parrot", ["parrot"], max_chars=len(" ".join(S[1:4])) + 3)
    assert len(text.strip("…")) <= len(" ".join(S[1:4])) + 3 and text.endswith("Pepper.…")
    four, _ = grown_excerpt(MSG, "parrot", ["parrot"], max_chars=1000)
    assert four == "…" + " ".join(S[1:5]) + "…"  # at most GROW_MAX_SENTENCES, however long it may be
    whole, _ = grown_excerpt(" ".join(S[:4]), "parrot", ["parrot"], max_chars=1000)
    assert whole == " ".join(S[:4])  # no ellipsis: nothing left out


def test_a_best_sentence_longer_than_the_length_is_cut_there():
    long = "The parrot " + "squawks and " * 30 + "sleeps."
    text, short = grown_excerpt(f"Before. {long} After.", "parrot", ["parrot"], max_chars=40)
    assert text == short and text.startswith("…The parrot") and text.count("…") == 2 and len(text.strip("…")) <= 39


def test_keywords_choose_the_sentence_before_shared_trigrams():
    msg = "The captain talks about the weather and the harbor. The parrot sleeps."
    assert grown_excerpt(msg, "captain harbor weather parrot", ["parrot"], max_chars=20)[1] == "…The parrot sleeps."


def parrot_chat() -> SimChat:
    chat = SimChat()
    chat.user("Let us begin.")
    chat.reply(MSG)
    for i in range(8):
        chat.user(f"Idle chatter {i} about the harbor.")
        chat.reply(f"Idle reply {i} about the harbor.")
    chat.user("next")
    return chat


QUESTION = "Hey, I forgot something from way back when we first met: what did everyone call the old parrot?"


def test_packet_v10_grows_the_excerpt_and_packet_v9_keeps_two_sentences(migrated):
    from conftest import make_client

    texts = {}
    for policy in ("packet-v10", "packet-v9"):
        with make_client(migrated, packet_policy=policy) as c:
            chat = parrot_chat()
            sync(c, chat)
            texts[policy] = recall(c, chat, QUESTION, in_context=[])["packet"]["text"]
    assert "Pepper" in texts["packet-v10"] and "Two two." in texts["packet-v10"]  # grown around the parrot sentence
    two = excerpt(MSG, QUESTION, max_chars=MAX_EXCERPT_CHARS)  # packet-v9's rule, unchanged
    assert two in texts["packet-v9"] and "Two two." not in texts["packet-v9"]


def test_a_grown_excerpt_never_takes_the_packet_past_its_budget(client):
    chat = SimChat()
    chat.user("Let us begin.")
    chat.reply(" ".join(f"The parrot said word {i}." for i in range(80)))
    chat.user("next")
    sync(client, chat)
    out = recall(client, chat, "what did the parrot say?", in_context=[], budget=200)
    assert out["packet"]["token_estimate"] <= 200


def test_a_request_recorded_with_packet_v9_replays_as_it_was(migrated):
    """Requests recorded while packet-v9 was the default keep compiling with it (ADR 0027, 0053)."""
    from uuid import UUID

    from conftest import make_client
    from nmos_sidecar import audit
    from nmos_sidecar.retrieval import RecallOptions
    from test_packet_ledger import db

    with make_client(migrated, packet_policy="packet-v9") as c:
        chat = parrot_chat()
        sync(c, chat)
        out = recall(c, chat, QUESTION, in_context=[])
    with db(migrated) as conn:
        again = audit.replay(conn, UUID(out["trace_id"]), RecallOptions())
    assert again["policy"] == again["recorded_policy"] == "packet-v9"
    assert again["reproduced"] is True and again["text"] == out["packet"]["text"]
