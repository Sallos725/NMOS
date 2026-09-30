"""PHASE-18 step 4 (ADR 0053): packet-v10's excerpts grow to the length the budget gives them."""

from __future__ import annotations

import pytest

from conftest import make_client
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


@pytest.mark.parametrize("content, words, max_chars, expected", [
    ("", ["parrot"], 40, ("", "")),  # nothing to excerpt
    ("The parrot sleeps.", [], 40, ("The parrot sleeps.", "The parrot sleeps.")),  # one sentence, no ellipsis
    ("Alpha beta. Gamma delta.", [], 15, ("Alpha beta.…", "Alpha beta.…")),  # a tie keeps the earlier sentence
])
def test_edge_cases(content, words, max_chars, expected):
    assert grown_excerpt(content, "unrelated", words, max_chars=max_chars) == expected


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


@pytest.mark.parametrize("before_keywords", [False, True])
def test_a_request_recorded_with_packet_v9_replays_as_it_was(migrated, monkeypatch, before_keywords):
    """Requests recorded while packet-v9 was the default keep compiling with it (ADR 0027, 0053), also those recorded
    before the keyword route, whose options do not name it (ADR 0052)."""
    from uuid import UUID

    from nmos_sidecar import audit, retrieval
    from nmos_sidecar.retrieval import RecallOptions
    from test_packet_ledger import db

    with make_client(migrated, packet_policy="packet-v9") as c:
        chat = parrot_chat()
        sync(c, chat)
        if before_keywords:
            monkeypatch.setattr(retrieval, "keywords", lambda query: [])
        out = recall(c, chat, QUESTION, in_context=[])
        monkeypatch.undo()
    with db(migrated) as conn:
        if before_keywords:
            conn.execute("UPDATE retrieval_trace SET recall_options = recall_options - 'lexical_keywords' "
                         "WHERE id = %s", (out["trace_id"],))
        again = audit.replay(conn, UUID(out["trace_id"]), RecallOptions())
    assert again["policy"] == again["recorded_policy"] == "packet-v9"
    assert again["reproduced"] is True and again["text"] == out["packet"]["text"]


def test_a_vector_only_hit_grows_within_its_chunk_only(migrated):
    """A lexical or keyword hit is the whole message; a vector-only hit stays in the chunk the vector matched."""
    from nmos_sidecar.vectors import chunks
    from test_vectors import FakeEmbedder, drain_embeddings

    filler = " ".join(f"Plain filler line {i:02d}." for i in range(31))
    long = f"{filler} The lighthouse beam sweeps the dark bay tonight. Tail words 01. Tail words 02."
    spans = chunks(long)
    assert long[spans[1][0]:].startswith("The lighthouse")  # the sentence before it is in another chunk
    chat = SimChat()
    chat.user("Let us begin.")
    chat.reply(long)
    for i in range(8):
        chat.user(f"Idle chatter {i}.")
        chat.reply(f"Idle reply {i}.")
    chat.user("next")
    with make_client(migrated, embedder=FakeEmbedder(), embed_url="http://fake/v1", embed_model="fake-embed") as c:
        sync(c, chat)
        drain_embeddings(migrated)
        out = recall(c, chat, "등대 불빛 기억나?", in_context=[])  # no word of it is in the message
    text = out["packet"]["text"]
    assert "The lighthouse beam" in text and "Tail words 01." in text  # grown after, inside the chunk
    assert "filler line 30" not in text  # not before it, across the chunk's start
