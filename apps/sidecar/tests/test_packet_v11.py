"""PHASE-27 step 2 (ADR 0063): packet-v11's excerpt lands on the answer. One deterministic case per branch of Q1–Q3
and Q1b (`docs/phases/PHASE-27.md`, In scope 2). The embedder is the concept-bag fake of `test_vectors.py`: texts
sharing a concept word are close, texts sharing none are far, so which chunk a vector finds is chosen by the words."""

from __future__ import annotations

import psycopg
from psycopg.rows import dict_row

from conftest import make_client
from nmos_sidecar import audit
from nmos_sidecar.packet import CONTENTS, CUE_GROW_CHARS, GROW_MAX_SENTENCES, grown_excerpt
from nmos_sidecar.facts import WHY
from nmos_sidecar.retrieval import RecallOptions
from nmos_sidecar.vectors import CHUNK_CHARS, chunks
from simchat import SimChat
from test_sidecar_integration import recall, sync
from test_vectors import FakeEmbedder, drain_embeddings

EMB = {"embed_url": "http://fake/v1", "embed_model": "fake-embed"}

# The first chunk: the parrot story (no concept word but "sword", so the chunk has a vector of its own) …
FIRST = [
    "The captain named the parrot Pepper on the first morning.",
    "The parrot sat on the mast and watched the gulls circle.",
    "The cook fed the parrot a slice of apple at noon.",
    "The captain kept an old sword above the galley door.",
    "The tide came in slowly and the ropes creaked.",
    "Two boys from the village sold figs on the pier.",
    "The mate counted the barrels twice and frowned.",
    "A grey cat slept on the coiled rope by the wheel.",
    "The captain wrote the day's log in a steady hand.",
    "Nobody spoke of the storm that had passed the week before.",
    "The parrot repeated the cook's whistle until dusk.",
    "The lamps were lit one by one along the quay.",
    "The cook scrubbed the pots and hummed an old tune.",
    "The captain checked the charts and went to bed early.",
]
# … and the second: where the key went (the "key" concept, nothing of the parrot).
SECOND = [
    "Later that week the cook found the brass key behind the stove and hung it on a nail.",
    "Nobody asked where it had come from.",
    "The captain shrugged and poured more coffee.",
]
LONG = " ".join(FIRST + SECOND)


def chat_with(reply: str, *, filler: str = "Idle chatter {i} about the pier.",
              idle: str = "Idle reply {i}.") -> SimChat:
    chat = SimChat()
    chat.user("Let us begin.")
    chat.reply(reply)
    for i in range(6):
        chat.user(filler.format(i=i))
        chat.reply(idle.format(i=i))
    chat.user("next")
    return chat


def client_for(url: str, policy: str, **overrides):
    return make_client(url, embedder=FakeEmbedder(), packet_policy=policy, **EMB, **overrides)


def packet_and_candidate(client, url: str, chat: SimChat, query: str, **extra) -> tuple[str, dict, dict]:
    """The packet text and the long reply's candidate as the trace recorded it, and the trace."""
    sync(client, chat)
    drain_embeddings(url)
    out = recall(client, chat, query, in_context=[], budget=600, **extra)
    trace = client.get(f"/v1/trace/{out['trace_id']}").json()
    reply = chat.messages[1]["chatId"]
    cand = next(c for c in trace["candidates"] if c["host_logical_id"] == reply)
    return out["packet"]["text"], cand, trace


def test_the_story_splits_where_the_cases_expect():
    spans = chunks(LONG, CHUNK_CHARS, 8)
    assert len(spans) == 2 and SECOND[0] in LONG[spans[1][0]:]  # the key sentence is in the second chunk …
    assert " ".join(FIRST[:4]) in LONG[: spans[0][1]]  # … the parrot's naming, and the sword, in the first


# ---- Q1: a message found by a word route and by vectors --------------------------------------------------------------

Q1_QUESTION = "Captain Pepper parrot: where is the key?"  # keywords captain, pepper, parrot (chunk one), key (chunk two)


def test_a_keyword_hit_with_a_qualifying_vector_excerpts_within_its_chunk_under_v11_and_the_whole_message_under_v10(
        migrated):
    texts = {}
    for policy in ("packet-v11", "packet-v10"):
        with client_for(migrated, policy) as c:
            text, cand, _ = packet_and_candidate(c, migrated, chat_with(LONG), Q1_QUESTION)
            assert cand["keyword_score"] > 0 and cand["sim"] is not None and cand["sim"] >= 0.42, cand
            texts[policy] = text
    # packet-v10: the whole message, grown from the sentence holding most keywords (three, in the first chunk)
    assert "named the parrot Pepper" in texts["packet-v10"] and "behind the stove" not in texts["packet-v10"]
    # packet-v11: the vector chunk, the part of the message the question is about
    assert "behind the stove" in texts["packet-v11"] and "named the parrot Pepper" not in texts["packet-v11"]


def test_a_lexical_hit_with_a_qualifying_vector_excerpts_within_its_chunk_too(migrated):
    """The keyword route drops a word found in more than half of the messages (ADR 0052), so with every keyword broad
    the message is found by the whole-message trigram route alone — and by vectors."""
    broad = "The captain watched the harbor in the morning weather, {i} times."  # 13 of the 15 messages hold them
    story = LONG.replace("The captain named the parrot Pepper on the first morning.",
                         "The captain watched the harbor in the morning weather and named the parrot Pepper.")
    question = "captain harbor morning weather key"  # four broad keywords (the longest four); "key" is not looked up
    texts = {}
    for policy in ("packet-v11", "packet-v10"):
        # Every message ties on the trigram route, and the fillers on vectors too, so their order (and with it which
        # five reach the packet) is whatever order the database returns ties in: Windows' differs from Linux's. Room
        # for every candidate keeps the case about the story's excerpt, not about tie order.
        with client_for(migrated, policy, recall_top_k=20) as c:
            text, cand, trace = packet_and_candidate(c, migrated, chat_with(story, filler=broad, idle=broad), question)
            assert trace["latency_ms"]["keyword_mode"] == "too_broad" and cand["keyword_score"] == 0, trace["latency_ms"]
            assert cand["user_score"] >= 0.4 and cand["sim"] >= 0.42, cand
            assert trace["latency_ms"]["placed"]["excerpt"] == len(trace["candidates"]), trace["latency_ms"]["placed"]
            texts[policy] = text
    assert "named the parrot Pepper" in texts["packet-v10"] and "behind the stove" not in texts["packet-v10"]
    assert "behind the stove" in texts["packet-v11"] and "named the parrot Pepper" not in texts["packet-v11"]


def test_a_word_hit_whose_vector_is_below_the_bar_keeps_the_whole_message(migrated):
    question = "Captain Pepper parrot: did it rain that day?"  # the "rain" concept is in neither chunk
    for policy in ("packet-v11", "packet-v10"):
        with client_for(migrated, policy) as c:
            text, cand, _ = packet_and_candidate(c, migrated, chat_with(LONG), question)
            assert cand["keyword_score"] > 0 and cand["sim"] is not None and cand["sim"] < 0.42, cand
            assert "named the parrot Pepper" in text and "behind the stove" not in text, policy


def test_a_vector_only_hit_excerpts_its_chunk_under_both(migrated):
    question = "은빛 물건은 어디에 있지?"  # the "key" concept, no word of the message
    for policy in ("packet-v11", "packet-v10"):
        with client_for(migrated, policy) as c:
            text, cand, _ = packet_and_candidate(c, migrated, chat_with(LONG), question)
            assert cand["keyword_score"] == 0 and cand["user_score"] < 0.4 and cand["sim"] >= 0.42, cand
            assert "behind the stove" in text and "named the parrot Pepper" not in text, policy


# ---- Q2: a why or contents question grows by characters ----------------------------------------------------------

PUMP = ["The pump stopped at noon.", "The valve had jammed.", "Pressure rose fast.", "The fuse opened.",
        "The crew left the deck.", "Nobody came back until dusk.", "The cook kept his stew warm."]
MEMO = ["The memo was short.", "It said to close the gate.", "It said to count the boxes.", "It said to log the tide.",
        "It said to wake the cook.", "It ended with a smile."]


def test_a_why_question_takes_every_short_sentence_within_320_characters_under_v11_and_four_under_v10(migrated):
    texts = {}
    for policy in ("packet-v11", "packet-v10"):
        with client_for(migrated, policy) as c:
            texts[policy], _, _ = packet_and_candidate(c, migrated, chat_with(" ".join(PUMP)), "Why did the pump stop?")
    assert all(s in texts["packet-v11"] for s in PUMP)  # seven sentences, 160 characters: the whole explanation
    assert " ".join(PUMP[:4]) in texts["packet-v10"] and PUMP[4] not in texts["packet-v10"]  # four, as ADR 0053


def test_a_contents_question_grows_the_same_way(migrated):
    texts = {}
    for policy in ("packet-v11", "packet-v10"):
        with client_for(migrated, policy) as c:
            texts[policy], _, _ = packet_and_candidate(c, migrated, chat_with(" ".join(MEMO)),
                                                       "What were the contents of the memo?")
    assert all(s in texts["packet-v11"] for s in MEMO)
    assert MEMO[4] not in texts["packet-v10"] and MEMO[5] not in texts["packet-v10"]


def test_an_ordinary_question_keeps_four_sentences_under_v11(migrated):
    with client_for(migrated, "packet-v11") as c:
        text, _, _ = packet_and_candidate(c, migrated, chat_with(" ".join(PUMP)), "Who stopped the pump?")
    assert " ".join(PUMP[:4]) in text and PUMP[4] not in text


def test_the_cues():
    assert WHY.search("Why did it stop?") and WHY.search("펌프가 왜 멈췄어?") and not WHY.search("Who stopped it?")
    assert CONTENTS.search("What were the contents of the memo?") and CONTENTS.search("그 기록의 내용은?")
    assert CONTENTS.search("What is the content of the memo?") and not CONTENTS.search("Who is contented?")
    assert not CONTENTS.search("Is she content?") and not CONTENTS.search("The content was moved.")  # the adjective, a noun alone


def test_the_cue_growth_stays_within_its_length_and_cuts_a_long_sentence():
    many = " ".join(f"Short line {i}." for i in range(40))  # 40 sentences of 13–14 characters
    text, _ = grown_excerpt(many, "line", ["line"], CUE_GROW_CHARS, max_sentences=None)
    assert len(text.strip("…")) <= CUE_GROW_CHARS and text.count("Short line") > GROW_MAX_SENTENCES
    text, _ = grown_excerpt(many, "line", ["line"], 60, max_sentences=None)
    assert len(text.strip("…")) <= 60  # the budget's length wins when it is the smaller
    long = "The pump " + "shook and " * 50 + "stopped."
    text, short = grown_excerpt(f"Before. {long} After.", "pump", ["pump"], CUE_GROW_CHARS, max_sentences=None)
    assert text == short and len(text.strip("…")) <= CUE_GROW_CHARS - 1  # cut, as ADR 0053 cuts
    assert grown_excerpt(many, "line", ["line"], 1000) == grown_excerpt(many, "line", ["line"], 1000, GROW_MAX_SENTENCES)


# ---- Q1b: the tie-break anchor (step 3: packet-v11's is the question's keywords; "focus" is packet-v10's) -----------

TWELVE = [
    "The parrot sat on the mast all morning and watched the gulls.",
    "The cook scrubbed the pots and hummed an old tune.",
    "The mate counted the barrels twice and frowned.",
    "A grey cat slept on the coiled rope by the wheel.",
    "The captain wrote the day's log in a steady hand.",
    "Two boys from the village sold figs in the rain.",
    "The tide came in slowly and the ropes creaked.",
    "The lamps were lit one by one along the quay.",
    "Nobody spoke of the storm that had passed the week before.",
    "The captain checked the charts and yawned.",
    "When the bell rang the parrot screamed and flew to the galley.",
    "The cook laughed and went back to his stew.",
]
BELL = "The bell rang and everyone froze on the deck."  # the previous reply: trigrams of the eleventh sentence


def test_packet_v11_anchors_on_the_questions_keywords_and_packet_v10_on_the_previous_reply(migrated):
    """Two sentences hold the keyword. Under packet-v11 the question's keywords alone break the tie (the earlier
    sentence; Q1b, decided by measurement in step 3), and the trace records `excerpt_anchor: "keywords"`; a replay with
    `excerpt_anchor="focus"` (`eval_rp.py --anchor focus`) lets the previous reply decide, as packet-v10 always does."""
    with client_for(migrated, "packet-v11") as c:
        chat = chat_with(" ".join(TWELVE))
        text, _, trace = packet_and_candidate(c, migrated, chat, "what did the parrot do", previous_ai=BELL)
        assert "watched the gulls" in text and "flew to the galley" not in text  # the first, on a tie
        assert trace["recall_options"]["excerpt_anchor"] == "keywords"
        assert c.get(f"/v1/trace/{trace['id']}/replay").json()["reproduced"] is True
        with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
            opts = RecallOptions(embedder=FakeEmbedder(), embed_projection=trace["embed_projection"])
            assert audit.replay(conn, trace["id"], opts)["text"] == text  # the recorded anchor replays as it was
            focused = audit.replay(conn, trace["id"], opts, excerpt_anchor="focus")  # as `eval_rp.py --anchor focus`
        assert "flew to the galley" in focused["text"] and "watched the gulls" not in focused["text"]  # the eleventh
        # a trace from before the option existed records no anchor: it replays with "focus", the anchor every request
        # had then (`audit.replay`), even under packet-v11
        with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
            conn.execute("UPDATE retrieval_trace SET recall_options = recall_options - 'excerpt_anchor' WHERE id = %s",
                         (trace["id"],))
            legacy = audit.replay(conn, trace["id"], opts)
        assert "flew to the galley" in legacy["text"] and "watched the gulls" not in legacy["text"]
        assert c.get(f"/v1/trace/{trace['id']}").json()["recall_options"].get("excerpt_anchor") is None
        # a question without keywords ("비", one syllable, is none; it is the embedder's rain concept, which finds the
        # message by vectors alone): the keywords anchor is the question itself, never the previous reply
        text, cand, trace = packet_and_candidate(c, migrated, chat, "비?", previous_ai=BELL)
        assert cand["keyword_score"] == 0 and cand["user_score"] < 0.4 and cand["sim"] >= 0.42, cand
        assert "watched the gulls" in text and "flew to the galley" not in text
        with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
            focused = audit.replay(conn, trace["id"], opts, excerpt_anchor="focus")
        assert "flew to the galley" in focused["text"] and "watched the gulls" not in focused["text"]
    with client_for(migrated, "packet-v10") as c:
        chat = chat_with(" ".join(TWELVE))
        text, _, trace = packet_and_candidate(c, migrated, chat, "what did the parrot do", previous_ai=BELL)
        assert "flew to the galley" in text
        with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
            opts = RecallOptions(embedder=FakeEmbedder(), embed_projection=trace["embed_projection"])
            assert audit.replay(conn, trace["id"], opts, excerpt_anchor="keywords")["text"] == text  # v10: today's


# ---- Q3: the policy, the default since step 3; packet-v10 selected by the setting; both recorded and replayed -------

def test_packet_v18_is_the_default_and_packet_v11_and_v10_stay_available_by_the_setting(migrated):
    with make_client(migrated, embedder=FakeEmbedder(), **EMB) as c:  # NMOS_PACKET_POLICY unset (owner, PHASE-40)
        text, _, trace = packet_and_candidate(c, migrated, chat_with(LONG), Q1_QUESTION)
        assert trace["policy"] == "packet-v18" and "behind the stove" in text
        assert c.get(f"/v1/trace/{trace['id']}/replay").json()["reproduced"] is True
    with client_for(migrated, "packet-v11") as c:
        text, _, trace = packet_and_candidate(c, migrated, chat_with(LONG), Q1_QUESTION)
        assert trace["policy"] == "packet-v11" and "behind the stove" in text
        assert c.get(f"/v1/trace/{trace['id']}/replay").json()["reproduced"] is True
    with client_for(migrated, "packet-v10") as c:
        text, _, trace = packet_and_candidate(c, migrated, chat_with(LONG), Q1_QUESTION)
        assert trace["policy"] == "packet-v10" and "named the parrot Pepper" in text
        assert c.get(f"/v1/trace/{trace['id']}/replay").json()["reproduced"] is True
