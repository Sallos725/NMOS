"""PHASE-60 S5 (ADR 0084 items 1–2, A8): under packet-v20 a short message is embedded with the reply before it.

`retrieval.sem_query(query, previous_ai)` (both already `clean_text`-normalized) is `previous_ai[-400:] + "\\n" +
query` when the message is shorter than 40 characters and there is a previous reply, else None. Only the text the
query embedding reads changes: lexical and keyword recall still read the message alone. The trace records the value
as `recall_options["sem_query"]` (under `packet.SEM_QUERY_POLICIES` only); a replay embeds what was recorded, and a
trace without the key embeds the message alone. The sync-time prefetch builds the same text, so a short message's
retrieve still finds its embedding waiting.

Written before the code (the tests are the contract): the names this phase adds are reached inside each test, so a
test fails on its own missing name, not the whole module at collection.
"""

from __future__ import annotations

import time

import psycopg
from psycopg.rows import dict_row

from conftest import make_client
from memeval import StubEmbedder, settings_for
from nmos_sidecar import audit, packet, retrieval
from nmos_sidecar.packet import clean_text
from nmos_sidecar.retrieval import RecallOptions
from test_packet_ledger import story
from test_sidecar_integration import recall, sync

# A reply longer than 400 characters, plain text (normalization leaves it as it is on both the sync and request side)
REPLY = " ".join(f"{i}번째 밤, 세라는 등대 아래에서 카이토를 조용히 기다렸다." for i in range(1, 25))
SHORT = "그래서 그 다음엔?"  # 10 characters
LONG = "세라가 등대 아래에서 기다리던 그 밤에 카이토는 정말 어디에 있었는지 하나하나 자세히 말해줘."
INSTRUCTION = "Find the story moment the message is about"
PREFIX = retrieval.query_prefix("stub-embed", INSTRUCTION)  # "Instruct: …\nQuery: ": a prefix the test can see


class Counting(StubEmbedder):
    """The memeval stand-in embedder, recording every text it is asked to embed."""

    def __init__(self) -> None:
        self.texts: list[str] = []

    def embed(self, texts, timeout_s):
        self.texts += texts
        return super().embed(texts, timeout_s)


def settings(policy: str) -> dict:
    return {**settings_for("full"), "packet_policy": policy, "embed_query_instruction": INSTRUCTION}


def db(url: str) -> psycopg.Connection:
    return psycopg.connect(url, row_factory=dict_row, autocommit=True)


def with_reply(client, url: str):
    """The ledger test's story, then a turn whose reply is REPLY (synced: it is the head's stored reply)."""
    chat = story(client, url, vectors=True)
    chat.user("세라 이야기를 계속해줘.")
    chat.reply(REPLY)
    sync(client, chat)
    return chat


def ask_unsynced(client, chat, query: str, previous_ai: str) -> dict:
    """A retrieve of `query` that its sync did not precede: no prefetched embedding exists, so the only text embedded
    is the one this request asks for."""
    out = recall(client, chat, query, in_context=[m["chatId"] for m in chat.messages[-2:]], previous_ai=previous_ai)
    return client.get(f"/v1/trace/{out['trace_id']}").json()


def wait_for(emb: Counting, n: int) -> None:
    deadline = time.monotonic() + 2
    while len(emb.texts) < n and time.monotonic() < deadline:
        time.sleep(0.01)


# --- sem_query (pure) ------------------------------------------------------------------------------------------------

def test_the_policies_that_embed_a_short_message_with_the_reply():
    assert packet.SEM_QUERY_POLICIES == frozenset({"packet-v20", "packet-v21"})


def test_a_message_of_39_characters_is_short_and_one_of_40_is_not():
    q39, q40 = "가" * 39, "가" * 40
    assert retrieval.sem_query(q39, "세라가 웃었다.") == "세라가 웃었다.\n" + q39
    assert retrieval.sem_query(q40, "세라가 웃었다.") is None
    assert retrieval.sem_query(q40 + " 그리고 더", "세라가 웃었다.") is None


def test_the_length_is_the_stripped_message_s():
    q = "  " + "나" * 39 + "  "  # 43 characters, 39 once stripped
    assert retrieval.sem_query(q, "카이토가 말했다.") == "카이토가 말했다.\n" + q


def test_no_previous_reply_means_no_sem_query():
    assert retrieval.sem_query(SHORT, "") is None
    assert retrieval.sem_query(SHORT, "   \n ") is None


def test_a_reply_shorter_than_400_characters_is_taken_whole():
    reply = "하나가 문을 열고 들어왔다."
    assert retrieval.sem_query(SHORT, reply) == reply + "\n" + SHORT


def test_a_longer_reply_gives_exactly_its_last_400_characters():
    assert len(REPLY) > 400
    out = retrieval.sem_query(SHORT, REPLY)
    assert out == REPLY[-400:] + "\n" + SHORT
    assert len(out) == 400 + 1 + len(SHORT)
    exact = "유" * 400
    assert retrieval.sem_query(SHORT, exact) == exact + "\n" + SHORT
    assert retrieval.sem_query(SHORT, "앞" + exact) == exact + "\n" + SHORT  # the 401st character from the end is left out


# --- through /v1/retrieve -------------------------------------------------------------------------------------------

def test_v20_a_short_message_embeds_the_reply_tail_a_line_break_and_the_message(migrated):
    emb = Counting()
    with make_client(migrated, embedder=emb, **settings("packet-v20")) as client:
        chat = with_reply(client, migrated)
        before = len(emb.texts)
        trace = ask_unsynced(client, chat, SHORT, REPLY)
    sem = clean_text(REPLY)[-400:] + "\n" + SHORT
    assert trace["policy"] == "packet-v20" and trace["latency_ms"]["vector_mode"] == "on"
    assert emb.texts[before:] == [PREFIX + sem]  # options.query_prefix + sem, asked once
    assert trace["recall_options"]["sem_query"] == sem  # recorded without the prefix
    assert trace["query"] == SHORT  # the message itself is what the trace records as the query


def test_v20_a_message_of_40_characters_or_more_embeds_the_message(migrated):
    assert len(LONG.strip()) >= 40
    emb = Counting()
    with make_client(migrated, embedder=emb, **settings("packet-v20")) as client:
        chat = with_reply(client, migrated)
        before = len(emb.texts)
        trace = ask_unsynced(client, chat, LONG, REPLY)
    assert emb.texts[before:] == [PREFIX + LONG]
    assert "sem_query" in trace["recall_options"] and trace["recall_options"]["sem_query"] is None


def test_v20_a_short_message_without_a_previous_reply_embeds_the_message(migrated):
    emb = Counting()
    with make_client(migrated, embedder=emb, **settings("packet-v20")) as client:
        chat = with_reply(client, migrated)
        before = len(emb.texts)
        trace = ask_unsynced(client, chat, SHORT, "")
    assert emb.texts[before:] == [PREFIX + SHORT]
    assert "sem_query" in trace["recall_options"] and trace["recall_options"]["sem_query"] is None


def test_v19_always_embeds_the_message_and_records_no_sem_query(migrated):
    emb = Counting()
    with make_client(migrated, embedder=emb, **settings("packet-v19")) as client:
        chat = with_reply(client, migrated)
        before = len(emb.texts)
        trace = ask_unsynced(client, chat, SHORT, REPLY)
    assert trace["policy"] == "packet-v19"
    assert emb.texts[before:] == [PREFIX + SHORT]
    assert "sem_query" not in trace["recall_options"]


def test_lexical_and_keyword_candidates_are_the_same_under_v19_and_v20(migrated):
    """Only the embedding input changes: the candidates the message's words found (lexical at the bar, keyword hits)
    and both routes' modes are the same for the same short message, while v20 embedded the reply tail with it."""
    question = "Hana has the map?"  # short, with a lexical hit on "Hana has the map."
    assert len(question) < 40
    seen: dict[str, dict] = {}
    texts: dict[str, list[str]] = {}
    with make_client(migrated, embedder=StubEmbedder(), **settings("packet-v19")) as client:
        chat = with_reply(client, migrated)
    for policy in ("packet-v19", "packet-v20"):
        emb = Counting()
        with make_client(migrated, embedder=emb, **settings(policy)) as client:
            seen[policy] = ask_unsynced(client, chat, question, REPLY)
        texts[policy] = emb.texts

    def word_hits(trace: dict) -> list[tuple]:
        return sorted((c["revision_id"], c["user_score"], c["keyword_score"]) for c in trace["candidates"]
                      if c["user_score"] >= trace["recall_options"]["threshold"] or c["keyword_score"] > 0)

    v19, v20 = seen["packet-v19"], seen["packet-v20"]
    assert word_hits(v19) and word_hits(v19) == word_hits(v20)
    for mode in ("lexical_mode", "keyword_mode"):
        assert v19["latency_ms"][mode] == v20["latency_ms"][mode]
    assert texts["packet-v19"] == [PREFIX + question]
    assert texts["packet-v20"] == [PREFIX + clean_text(REPLY)[-400:] + "\n" + question]


def test_a_replay_embeds_the_recorded_sem_query_and_a_trace_without_it_the_message(migrated):
    emb = Counting()
    with make_client(migrated, embedder=emb, **settings("packet-v20")) as client:
        chat = with_reply(client, migrated)
        trace = ask_unsynced(client, chat, SHORT, REPLY)
    sem = clean_text(REPLY)[-400:] + "\n" + SHORT
    options = RecallOptions(embedder=emb, embed_projection=trace["embed_projection"])
    with db(migrated) as conn:
        before = len(emb.texts)
        out = audit.replay(conn, trace["id"], options)
        assert out["status"] == "ok" and out["vectors"] == "on"
        assert emb.texts[before:] == [PREFIX + sem]  # the recorded value, with the recorded prefix
        assert out.get("reproduced") is True
        # the replay embeds what the trace says, not a value it builds again
        recorded = "기록된 다른 문맥: 하나가 등대의 불을 켰다.\n" + SHORT
        conn.execute("UPDATE retrieval_trace SET recall_options = jsonb_set(recall_options, '{sem_query}',"
                     " to_jsonb(%s::text)) WHERE id = %s", (recorded, trace["id"]))
        before = len(emb.texts)
        audit.replay(conn, trace["id"], options)
        assert emb.texts[before:] == [PREFIX + recorded]
        # a trace recorded before sem_query replays with it off: the message alone
        conn.execute("UPDATE retrieval_trace SET recall_options = recall_options - 'sem_query' WHERE id = %s",
                     (trace["id"],))
        before = len(emb.texts)
        audit.replay(conn, trace["id"], options)
        assert emb.texts[before:] == [PREFIX + SHORT]


def test_the_sync_prefetches_the_same_text_so_a_short_message_finds_its_embedding_waiting(migrated):
    """ADR 0084 item 2: the prefetch (D70) builds the text from the head's stored reply with the same function; the
    retrieve that follows takes it (`embed_lead`) and asks nothing again, as tests/test_prefetch.py asserts a hit."""
    emb = Counting()
    with make_client(migrated, embedder=emb, **settings("packet-v20")) as client:
        chat = with_reply(client, migrated)  # the reply is stored by its own, earlier sync
        before = len(emb.texts)
        chat.user(SHORT)
        sync(client, chat)  # the bodies carry the short message: its embedding is asked for now
        wait_for(emb, before + 1)
        sem = clean_text(REPLY)[-400:] + "\n" + SHORT
        assert emb.texts[before:] == [PREFIX + sem]
        out = recall(client, chat, SHORT, in_context=[m["chatId"] for m in chat.messages[-2:]], previous_ai=REPLY)
        trace = client.get(f"/v1/trace/{out['trace_id']}").json()
    assert out["vectors"] == "on" and emb.texts[before:] == [PREFIX + sem]  # not asked again
    assert trace["latency_ms"]["embed_lead"] >= 0
    assert trace["recall_options"]["sem_query"] == sem
