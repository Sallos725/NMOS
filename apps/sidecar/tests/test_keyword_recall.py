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


def test_a_trace_from_before_the_keyword_route_replays_without_it(client, migrated, monkeypatch):
    from nmos_sidecar import retrieval

    chat = parrot_chat()
    sync(client, chat)
    monkeypatch.setattr(retrieval, "keywords", lambda query: [])  # recorded as a request before the route
    out = recall(client, chat, QUESTION, in_context=[])
    monkeypatch.undo()
    with db(migrated) as conn:
        conn.execute("UPDATE retrieval_trace SET recall_options = recall_options - 'lexical_keywords' WHERE id = %s",
                     (out["trace_id"],))
        old = audit.replay(conn, UUID(out["trace_id"]), RecallOptions())
        forced = audit.replay(conn, UUID(out["trace_id"]), RecallOptions(), lexical_keywords=True)
    assert old["keywords"] == "off" and old["reproduced"] is True and old["text"] == out["packet"]["text"]
    assert forced["keywords"] == "on" and "Pepper" in forced["text"] and "Pepper" not in old["text"]


def test_a_word_no_message_holds_is_not_too_broad(client):
    chat = parrot_chat()
    sync(client, chat)
    out = recall(client, chat, "zzqx albatross", in_context=[])
    assert trace(client, out)["latency_ms"]["keyword_mode"] == "on" and out["packet"]["text"] == ""


def test_disabled_and_comment_messages_do_not_count_toward_too_broad(client):
    chat = SimChat()
    chat.user("A parrot squawks.")
    chat.reply("The parrot is named Pepper.")
    for i in range(3):  # messages the host hides: not searchable, so not counted either
        chat.user(f"Hidden {i}.")
        chat.messages[-1]["disabled"] = True
    chat.user("next")
    sync(client, chat)
    out = recall(client, chat, "parrot", in_context=[])
    assert trace(client, out)["latency_ms"]["keyword_mode"] == "too_broad"


def test_an_excerpt_only_a_keyword_found_is_left_out_when_it_repeats_a_secret(full):
    client, url = full
    chat = story(client, url)  # "Hana keeps a secret from Kaito: the letter is forged."
    out = ask(client, chat, "Kaito, anything new?")
    t = client.get(f"/v1/trace/{out['trace_id']}").json()
    assert t["latency_ms"]["keyword_withheld"] >= 1
    assert not any("forged" in line for line in out["packet"]["text"].splitlines() if "<Excerpt" in line)


def test_a_keyword_only_excerpt_is_placed_whole_or_short_never_cut():
    from nmos_sidecar.packet import Excerpt, _fit_excerpt, estimate_tokens, excerpt_line

    item = Excerpt(turn=1, speaker="character", text="The parrot is named Pepper. It squawks at dawn every morning.",
                   score=1.0, revision_id="r", short="The parrot is named Pepper and it squawks at dawn.")
    room = estimate_tokens(excerpt_line(item, item.short) + "\n") - 1  # the short form does not fit, a cut does
    assert _fit_excerpt(item, room)[0] == "cut"
    assert _fit_excerpt(Excerpt(**{**item.__dict__, "cut_ok": False}), room) is None


def test_with_facts_threads_and_summaries_off_the_scene_still_sets_the_secret_bar(migrated, monkeypatch):
    from conftest import make_client
    from memeval import _sync, settings_for
    from nmos_sidecar import retrieval
    from test_packet_ledger import extract

    seen: list[frozenset] = []
    real = retrieval.summaries.leaks

    def spy(text, secrets, present=frozenset()):
        seen.append(present)
        return real(text, secrets, present)

    settings = {k: v for k, v in settings_for("full").items() if not k.startswith("embed_")} | {
        "embed_backfill": 0, "facts_limit": 0, "threads_limit": 0}
    with make_client(migrated, **settings) as c:
        chat = SimChat()
        chat.reply("Welcome to the story.")
        for user in ("Hana keeps a secret from Kaito: the letter is forged.", "Hana has the map.",
                     *[f"Idle chatter {i} about clouds." for i in range(4)]):
            chat.user(user)
            chat.reply("Noted.")
            _sync(c, chat)
        extract(migrated)
        monkeypatch.setattr(retrieval.summaries, "leaks", spy)
        out = ask(c, chat, "Kaito, anything new?")  # only the keyword route finds the secret's message
    assert seen and any("kaito" in p for p in seen)  # the bar for a scene where Kaito is present
    assert not any("forged" in line for line in out["packet"]["text"].splitlines() if "<Excerpt" in line)


def test_the_lexical_lookups_are_planned_with_their_words_every_time(client, migrated):
    """psycopg prepares a statement on the server after five runs, and Postgres then plans it without its parameters
    (a generic plan): for `<%` that plan walks every head message with word_similarity instead of asking the trigram
    index, past a keyword's slice, so a long-lived connection dropped a word every ten or so lookups and a replay of one
    request found 13 candidates or 3 depending on what the connection had run before. Never prepared, never generic."""
    from nmos_sidecar import retrieval

    chat = parrot_chat()
    sync(client, chat)
    with db(migrated) as conn:
        head = conn.execute("SELECT head_commit_id FROM conversation").fetchone()["head_commit_id"]
        cut = retrieval._cut(conn, head)
        runs = [(retrieval._lexical(conn, head, "The parrot is named Pepper?", "", cut, 0.4, 300)[1],
                 [r["id"] for r in retrieval._keyword_lexical(conn, head, ["parrot", "pepper"], cut, 300)[0]])
                for _ in range(12)]
        prepared = conn.execute("SELECT generic_plans FROM pg_prepared_statements"
                                " WHERE strpos(statement, '<%') > 0").fetchall()
    assert runs[0][0] == "on" and runs[0][1] and all(r == runs[0] for r in runs)
    assert prepared == []


def test_a_new_head_is_searched_through_the_trigram_index(client, migrated):
    """A reroll, an edit or a deletion makes a new head commit (appends keep the head, D4), which the planner's
    statistics on active_membership do not hold until the next autoanalyze: it estimated the head at one row and planned
    the lookup from the membership, with word_similarity on every head message, past a keyword's slice. (On this small
    chat the planner even planned a known head through revision_text's primary key, checking every revision.) The
    lookup is planned from the trigram index whatever the statistics say."""
    from nmos_sidecar import retrieval

    chat = parrot_chat()
    chat.reply("The parrot sleeps.")
    sync(client, chat)
    with db(migrated) as conn:
        before = conn.execute("SELECT head_commit_id FROM conversation").fetchone()["head_commit_id"]
        conn.execute("ANALYZE active_membership")  # the statistics hold this head only
    chat.reroll("The parrot wakes.")
    sync(client, chat)  # a divergence: a new head they do not know
    with db(migrated) as conn:
        head = conn.execute("SELECT head_commit_id FROM conversation").fetchone()["head_commit_id"]
        with conn.transaction():
            retrieval._apply(conn, {"pg_trgm.word_similarity_threshold": "0.8", "enable_seqscan": "off",
                                    "enable_indexscan": "off"})  # as the keyword route runs it
            plan = conn.execute("EXPLAIN (FORMAT JSON) " + retrieval._MATCHES,
                                retrieval._matches_params(head, "parrot", retrieval._cut(conn, head), 201),
                                prepare=False).fetchone()["QUERY PLAN"]
        found = retrieval._lexical_matches(conn, head, "parrot", retrieval._cut(conn, head), 201)

    def nodes(n):
        yield n
        for child in n.get("Plans", []):
            yield from nodes(child)
    assert head != before
    assert any(n.get("Index Name") == "revision_text_trgm" for n in nodes(plan[0]["Plan"]))
    assert len(found) == 1  # the parrot's first message: the newest reply is still provisional
