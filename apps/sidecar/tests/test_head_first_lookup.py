"""ADR 0052 amendment 1: a short head's lexical lookups recheck only its own revisions, with the same matches."""
from __future__ import annotations

import psycopg
import pytest
from psycopg.rows import dict_row

from nmos_sidecar import retrieval
from simchat import SimChat
from test_sidecar_integration import recall, sync

LONG = " ".join(["바람이 등대 너머로 불었다."] * 60)


def two_chats(client) -> tuple[SimChat, SimChat]:
    """Another chat with many long messages holding the keyword, and a short chat holding it once."""
    other = SimChat()
    for n in range(40):
        other.user(f"등대지기가 불을 켰다. {n}")
        other.reply(f"등대지기는 계단을 올랐다. {LONG} {n}")
    other.user("계속")
    sync(client, other)
    short = SimChat()
    short.user("항구에 도착했다.")
    short.reply("등대지기는 낡은 열쇠를 건넸다.")
    for n in range(3):
        short.user(f"부두를 걷는다. {n}")
        short.reply("갈매기가 울었다.")
    short.user("계속")
    sync(client, short)
    return other, short


def head_of(conn, chat: SimChat):
    return conn.execute("SELECT head_commit_id FROM conversation WHERE host_chat_ref=%s",
                        (chat.id,)).fetchone()["head_commit_id"]


def nodes(plan):
    yield plan
    for child in plan.get("Plans", []):
        yield from nodes(child)


@pytest.mark.parametrize("sql", ["_MATCHES", "_PARTICLE_MATCHES"])
def test_head_first_replaces_only_the_lookup_source(sql):
    original = getattr(retrieval, sql)
    restricted = retrieval._head_first(original)
    fence = "FROM (SELECT * FROM revision_text WHERE source_revision_id = ANY(%(ids)s::uuid[]) OFFSET 0) AS revision_text"
    assert restricted.count(fence) == 1
    assert " ".join(restricted.replace(fence, "FROM revision_text", 1).split()) == " ".join(original.split())


def test_short_head_rechecks_only_its_revisions_with_the_same_matches(client, migrated):
    other, short = two_chats(client)
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        retrieval._apply(conn, {"pg_trgm.word_similarity_threshold": str(retrieval.KEYWORD_THRESHOLD),
                                "enable_seqscan": "off", "enable_indexscan": "off"})
        head = head_of(conn, short)
        ids = retrieval._head_ids(conn, head, -1)
        assert ids is not None and len(ids) == len(short.messages)
        for word in ["등대지기", "열쇠"]:
            assert retrieval._lexical_matches(conn, head, word, -1, 201, None, ids) == \
                retrieval._lexical_matches(conn, head, word, -1, 201)
        rechecked = {}
        for name, sql in [("index", retrieval._MATCHES), ("head", retrieval._head_first(retrieval._MATCHES))]:
            plan = conn.execute("EXPLAIN (ANALYZE, FORMAT JSON) " + sql,
                                retrieval._matches_params(head, "등대지기", -1, 201, None, ids),
                                prepare=False).fetchone()["QUERY PLAN"][0]["Plan"]
            rechecked[name] = sum(n["Actual Rows"] for n in nodes(plan) if n.get("Relation Name") == "revision_text")
        assert rechecked["index"] > 40 and rechecked["head"] <= len(short.messages)


def test_keyword_route_and_packet_are_unchanged_by_the_head_first_lookup(client, migrated, monkeypatch):
    other, short = two_chats(client)
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        head = head_of(conn, short)
        ids = retrieval._head_ids(conn, head, -1)
        for particles in (False, True):
            restricted = retrieval._keyword_lexical(conn, head, ["등대지기", "열쇠"], -1, 300,
                                                    particles=particles, head_ids=ids)
            assert restricted == retrieval._keyword_lexical(conn, head, ["등대지기", "열쇠"], -1, 300,
                                                            particles=particles)
    statements = []
    execute = psycopg.Connection.execute

    def watched(conn, query, params=None, **kwargs):
        statements.append(query if isinstance(query, str) else "")
        return execute(conn, query, params, **kwargs)

    monkeypatch.setattr(psycopg.Connection, "execute", watched)
    first = recall(client, short, "등대지기가 건넨 것은?", budget=4000)
    monkeypatch.undo()
    # The word lookups are kept to the head; the particle supplement stays index-first (its slice ran out otherwise).
    assert any("<%" in q and "ANY(%(ids)s" in q for q in statements)
    assert any("LIKE ANY" in q for q in statements)
    assert all("ANY(%(ids)s" not in q for q in statements if "LIKE ANY" in q)
    monkeypatch.setattr(retrieval, "HEAD_FIRST_MAX", 0)  # every head index-first, as before
    again = recall(client, short, "등대지기가 건넨 것은?", budget=4000)
    assert "낡은 열쇠" in first["packet"]["text"] and first["packet"]["text"] == again["packet"]["text"]


def test_a_head_past_the_limit_keeps_the_index_first_lookup(client, migrated, monkeypatch):
    other, _ = two_chats(client)
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        head = head_of(conn, other)
        monkeypatch.setattr(retrieval, "HEAD_FIRST_CHARS", 20_000)
        assert retrieval._head_ids(conn, head, -1) is None  # its long messages pass the character limit
        monkeypatch.setattr(retrieval, "HEAD_FIRST_CHARS", 10**9)
        monkeypatch.setattr(retrieval, "HEAD_FIRST_MAX", 80)
        assert retrieval._head_ids(conn, head, -1) is None  # 81 messages, past the limit
        monkeypatch.setattr(retrieval, "HEAD_FIRST_MAX", 81)
        assert len(retrieval._head_ids(conn, head, -1)) == 81
        assert len(retrieval._head_ids(conn, head, 40)) == 40  # only what a lookup may find: after the cut
