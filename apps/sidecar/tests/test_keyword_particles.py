"""AGE-76: constructed stories, exact particle boundaries and replay compatibility."""
from __future__ import annotations

from uuid import UUID

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import make_client
from nmos_sidecar import audit, retrieval
from nmos_sidecar.retrieval import RecallOptions
from simchat import SimChat
from test_sidecar_integration import recall, sync


def story(answer: str, distractor: str = "차건혁, 유나겸, 배시후의 이름이 기록에 남았다.") -> SimChat:
    chat = SimChat()
    chat.user("서고에서 이야기가 시작되었다.")
    chat.reply(answer)
    for n in range(4):
        chat.user(f"풍경을 살핀다. {n}")
        chat.reply("흰 구름이 산 너머로 천천히 지나갔다.")
    chat.user("기록을 정돈한다.")
    chat.reply(distractor)
    chat.user("계속")
    return chat


def lookup(url: str, word: str, *, particles: bool = True, upto=None):
    with psycopg.connect(url, row_factory=dict_row) as conn:
        head = conn.execute("SELECT head_commit_id FROM conversation").fetchone()["head_commit_id"]
        return retrieval._keyword_lexical(conn, head, [word], retrieval._cut(conn, head), 300,
                                         upto, particles=particles)


@pytest.mark.parametrize("name,particle,action", [
    ("차건혁", "은", "주전자 뚜껑을 닫았다"),
    ("민지", "는", "오르골 태엽을 감았다"),
    ("한서윤", "이", "빗장을 걸었다"),
    ("유나겸", "에게", "보라색 우산을 건넸다"),
    ("도윤", "과", "종이배를 접었다"),
    ("서재", "에서", "은빛 나침반을 찾았다"),
    ("윤하", "도", "분홍 리본을 묶었다"),
    ("민지", "에게서", "작은 단추를 받았다"),
])
def test_particle_bearing_keywords_recall_the_exact_source_without_vectors(client, migrated, name, particle, action):
    answer = f"{name}{particle} {action}."
    chat = story(answer, "두 사람의 이름이 기록에 남았다.")
    sync(client, chat)
    old, _ = lookup(migrated, name, particles=False)
    new, mode = lookup(migrated, name)
    assert not any(r["clean"] == answer for r in old)
    assert mode == "on" and any(r["clean"] == answer and r["keyword_score"] > 0 for r in new)


def test_default_api_records_the_correction_and_new_trace_replays(client, migrated):
    answer = "차건혁은 주전자 뚜껑을 닫았다."
    chat = story(answer)
    sync(client, chat)
    out = recall(client, chat, "차건혁이 닫은 것은 무엇이었지?", budget=4000)
    trace = client.get(f"/v1/trace/{out['trace_id']}").json()
    assert trace["policy"] == "packet-v18"
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        row = conn.execute("SELECT recall_options FROM retrieval_trace WHERE id=%s", (out["trace_id"],)).fetchone()
        assert row["recall_options"]["keyword_particles"] is True
        again = audit.replay(conn, UUID(out["trace_id"]), RecallOptions())
    assert answer in out["packet"]["text"]
    assert again["reproduced"] is True


@pytest.mark.parametrize("policy", ["packet-v16", "packet-v17", "packet-v18"])
def test_old_trace_missing_option_and_old_policies_keep_old_matching(migrated, policy):
    chat = story("차건혁은 주전자 뚜껑을 닫았다.")
    with make_client(migrated, packet_policy=policy) as client:
        sync(client, chat)
        out = recall(client, chat, "차건혁이 닫은 것은 무엇이었지?", budget=4000)
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        off = audit.replay(conn, UUID(out["trace_id"]), RecallOptions(), keyword_particles=False)
        conn.execute("UPDATE retrieval_trace SET recall_options=recall_options-'keyword_particles' WHERE id=%s",
                     (out["trace_id"],))
        missing = audit.replay(conn, UUID(out["trace_id"]), RecallOptions())
        forced = audit.replay(conn, UUID(out["trace_id"]), RecallOptions(), keyword_particles=True)
    assert missing["text"] == off["text"]
    if policy != "packet-v18":
        assert forced["text"] == missing["text"] == out["packet"]["text"]
    else:
        assert "차건혁은 주전자 뚜껑을 닫았다" in forced["text"]
        assert forced["text"] != missing["text"]


@pytest.mark.parametrize("word", ["차건혁", "민지"])
def test_particle_hits_do_not_admit_prefix_suffix_or_other_actor_collisions(client, migrated, word):
    bodies = [f"{word}은 작은 상자를 닫았다.", f"김{word}은 창문을 닫았다.",
              f"{word}도서관에서 문을 닫았다.", f"{word}이는 문을 닫았다.",
              f"A{word}은 문을 닫았다.", f"{word}은A 문을 닫았다.",
              f"{word}_은 문을 닫았다.", "박하준은 주전자 뚜껑을 닫았다."]
    chat = SimChat()
    for body in bodies:
        chat.user("이야기가 이어진다.")
        chat.reply(body)
    chat.user("계속")
    sync(client, chat)
    old, _ = lookup(migrated, word, particles=False)
    new, _ = lookup(migrated, word)
    gained = {r["clean"] for r in new} - {r["clean"] for r in old}
    assert gained == {bodies[0]}


@pytest.mark.parametrize("count", [5, 201])
def test_combined_fuzzy_and_particle_hits_obey_both_rarity_limits(client, migrated, count):
    chat = SimChat()
    for n in range(count):
        chat.user(f"민지는 산을 바라본다. {n}")
        chat.reply(f"민지는 다시 길을 걷는다. {n}")
    chat.user("계속")
    sync(client, chat)
    rows, mode = lookup(migrated, "민지")
    assert rows == [] and mode == "too_broad"


@pytest.mark.parametrize("kind", ["disabled", "comment", "cut", "edited", "in_context", "upto"])
def test_particle_correction_keeps_source_visibility_filters(client, migrated, kind):
    answer = "민지는 은빛 나침반을 감췄다."
    chat = story(answer, "도서관의 불이 꺼졌다.")
    if kind == "disabled":
        chat.messages[1]["disabled"] = True
    elif kind == "comment":
        chat.messages[1]["isComment"] = True
    elif kind == "cut":
        chat.messages[2]["disabled"] = "allBefore"
    sync(client, chat)
    if kind == "edited":
        chat.edit(1, "밤하늘에 별이 보였다.")
        sync(client, chat)
    if kind == "upto":
        rows, _ = lookup(migrated, "민지", upto=0)
        assert not rows
    else:
        held = [chat.messages[1]["chatId"]] if kind == "in_context" else []
        out = recall(client, chat, "민지는 무엇을 감췄어?", in_context=held, budget=4000)
        assert answer not in out["packet"]["text"]


def test_particle_lookup_uses_selective_trigram_prefilters_and_is_never_prepared(client, migrated):
    from nmos_sidecar.keywords import particle_lookup

    chat = story("민지는 은빛 나침반을 감췄다.", "차건혁은 주전자 뚜껑을 닫았다.")
    sync(client, chat)
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        head = conn.execute("SELECT head_commit_id FROM conversation").fetchone()["head_commit_id"]
        retrieval._apply(conn, {"pg_trgm.word_similarity_threshold": str(retrieval.PARTICLE_PREFILTER), "enable_seqscan": "off",
                                "enable_indexscan": "off"})
        for word in ["민지", "차건혁"]:
            prefixes, particle = particle_lookup(word)
            params = retrieval._matches_params(head, word, -1, 201) | {"prefixes": prefixes, "particle": particle}
            plan = conn.execute("EXPLAIN (ANALYZE, FORMAT JSON) " + retrieval._PARTICLE_MATCHES,
                                params, prepare=False).fetchone()["QUERY PLAN"][0]["Plan"]
            def nodes(n):
                yield n
                for child in n.get("Plans", []):
                    yield from nodes(child)
            index = [n for n in nodes(plan) if n.get("Index Name") == "revision_text_trgm"]
            assert index and any("~~" in n["Index Cond"] for n in index)
            assert all(n["Actual Rows"] < len(chat.messages) // 2 for n in index)
        for _ in range(12):
            rows, mode = retrieval._keyword_lexical(conn, head, ["민지"], -1, 300, particles=True)
            assert mode == "on" and len(rows) == 1
        assert not conn.execute("SELECT 1 FROM pg_prepared_statements WHERE strpos(statement, 'LIKE ANY') > 0").fetchall()


def test_expired_route_abstains_and_restores_connection_settings(client, migrated):
    chat = story("민지는 은빛 나침반을 감췄다.")
    sync(client, chat)
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        head = conn.execute("SELECT head_commit_id FROM conversation").fetchone()["head_commit_id"]
        before = conn.execute("SHOW statement_timeout").fetchone()
        assert retrieval._keyword_lexical(conn, head, ["민지"], -1, 0, particles=True) == ([], "timeout")
        assert conn.execute("SHOW statement_timeout").fetchone() == before
        assert conn.execute("SELECT 1 AS n").fetchone()["n"] == 1


@pytest.mark.parametrize("timeout,expected", [(300, "on"), (10, "timeout")])
def test_particle_sql_shares_keyword_slice_and_route_deadline(client, migrated, monkeypatch, timeout, expected):
    chat = story("민지는 은빛 나침반을 감췄다.", "A parrot named Pepper landed.")
    sync(client, chat)
    monkeypatch.setattr(retrieval, "_PARTICLE_MATCHES",
                        retrieval._PARTICLE_MATCHES.replace("SELECT sr.id", "SELECT sr.id, pg_sleep(0.05)"))
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        head = conn.execute("SELECT head_commit_id FROM conversation").fetchone()["head_commit_id"]
        rows, mode = retrieval._keyword_lexical(conn, head, ["민지", "parrot"], -1, timeout, particles=True)
        assert mode == expected
        if expected == "on":
            assert len(rows) == 1 and "Pepper" in rows[0]["clean"]
        else:
            assert rows == []
        assert conn.execute("SELECT 1 AS n").fetchone()["n"] == 1


def test_particle_prefilter_accepts_only_existing_hangul_keyword_shape():
    from nmos_sidecar.keywords import particle_lookup

    for word in ["민", "Alice", "한A", "민지%", "민지_", "123", ""]:
        assert particle_lookup(word) is None


def keyword_rows(url: str, words: list[str], *, particles: bool):
    with psycopg.connect(url, row_factory=dict_row) as conn:
        head = conn.execute("SELECT head_commit_id FROM conversation").fetchone()["head_commit_id"]
        return retrieval._keyword_lexical(conn, head, words, -1, 300, particles=particles)


@pytest.mark.parametrize("legacy_count", [49, 50])
def test_supplement_uses_only_slots_after_unchanged_legacy_candidates(client, migrated, monkeypatch, legacy_count):
    chat = SimChat()
    for n in range(legacy_count):
        chat.user("Clouds pass above the mountains.")
        chat.reply(f"A parrot rested by marker {n}.")
    chat.user("기록을 살핀다.")
    chat.reply("민지는 은빛 나침반을 감췄다.")
    chat.user("계속")
    sync(client, chat)
    old, _ = keyword_rows(migrated, ["parrot", "민지"], particles=False)
    if legacy_count == 50:
        # A full legacy list must not risk its route budget on unused additions.
        monkeypatch.setattr(retrieval, "_PARTICLE_MATCHES", "SELECT 1 / 0")
    new, _ = keyword_rows(migrated, ["parrot", "민지"], particles=True)
    assert [(r["id"], r["keyword_score"]) for r in new[:legacy_count]] == [
        (r["id"], r["keyword_score"]) for r in old]
    assert len(new) == 50 and len({r["id"] for r in new}) == 50
    assert any("나침반" in r["clean"] for r in new) is (legacy_count == 49)


def test_new_keyword_evidence_never_changes_a_legacy_candidates_weight_or_order(client, migrated):
    chat = story("민지는 parrot 그림을 그렸다.", "A parrot sleeps by the harbor.")
    sync(client, chat)
    old, _ = keyword_rows(migrated, ["parrot", "민지"], particles=False)
    new, _ = keyword_rows(migrated, ["parrot", "민지"], particles=True)
    assert len(old) == 2
    assert [(r["id"], r["keyword_score"]) for r in new] == [(r["id"], r["keyword_score"]) for r in old]


@pytest.mark.parametrize("count", [5, 201])
def test_combined_breadth_rejects_only_additions_and_preserves_legacy_weight(client, migrated, count):
    chat = SimChat()
    chat.user("구름이 흐른다.")
    chat.reply("민지, 은빛 나침반을 감췄다.")
    for n in range(count):
        chat.user(f"민지는 산을 바라본다. {n}")
        chat.reply(f"민지는 새 길을 걷는다. {n}")
    chat.user("계속")
    sync(client, chat)
    old, _ = keyword_rows(migrated, ["민지"], particles=False)
    new, mode = keyword_rows(migrated, ["민지"], particles=True)
    assert len(old) == 1 and mode == "on"
    assert [(r["id"], r["keyword_score"]) for r in new] == [(r["id"], r["keyword_score"]) for r in old]


def test_a_cancelled_legacy_lookup_never_runs_supplement_with_an_incomplete_denominator(client, migrated, monkeypatch):
    chat = story("민지는 은빛 나침반을 감췄다.", "A parrot sleeps by the harbor.")
    sync(client, chat)
    real = retrieval._lexical_matches
    seen = []
    particle = retrieval.particle_lookup

    def cancel_name(conn, head, query, cut, limit, upto=None):
        if query == "민지":
            raise psycopg.errors.QueryCanceled()
        return real(conn, head, query, cut, limit, upto)

    def watched(word):
        seen.append(word)
        return particle(word)

    monkeypatch.setattr(retrieval, "_lexical_matches", cancel_name)
    monkeypatch.setattr(retrieval, "particle_lookup", watched)
    rows, mode = keyword_rows(migrated, ["민지", "parrot"], particles=True)
    assert mode == "on" and len(rows) == 1 and "parrot" in rows[0]["clean"]
    assert "민지" not in seen


def test_supplement_sql_has_only_the_legacy_words_remaining_slice_and_keeps_legacy_on_timeout(client, migrated, monkeypatch):
    chat = story("민지는 은빛 나침반을 감췄다.", "민지, 주전자 뚜껑을 닫았다.")
    sync(client, chat)
    real = retrieval._lexical_matches

    def delayed(conn, head, query, cut, limit, upto=None):
        conn.execute("SELECT pg_sleep(0.015)")
        return real(conn, head, query, cut, limit, upto)

    monkeypatch.setattr(retrieval, "_lexical_matches", delayed)
    # 20 ms fits a fresh 25 ms slice but not what remains after the legacy lookup.
    monkeypatch.setattr(retrieval, "_PARTICLE_MATCHES",
                        retrieval._PARTICLE_MATCHES.replace("SELECT sr.id", "SELECT sr.id, pg_sleep(0.020)"))
    rows, mode = keyword_rows(migrated, ["민지"], particles=True)
    assert mode == "on" and len(rows) == 1 and rows[0]["clean"].startswith("민지,")


@pytest.mark.parametrize("word", ["민지", "나나"])
def test_coarse_envelope_covers_unicode_boundaries_and_repeated_syllables(client, migrated, word):
    from nmos_sidecar.keywords import _SOURCE_PARTICLES
    from nmos_sidecar.packet import clean_text

    positives = [f"{word}는 나침반을 감췄다.", f"어느 날 {word}는 나침반을 감췄다.",
                 f"({word}는) 나침반을 감췄다.", f"【{word}는】 나침반을 감췄다.",
                 f"🍀{word}는 나침반을 감췄다.", f"첫 문장.\u2003{word}는 나침반을 감췄다.",
                 f"첫 문장.{word}는 나침반을 감췄다.", f"첫 문장\n{word}는 나침반을 감췄다."]
    negatives = [f"김{word}는 나침반을 감췄다.", f"{word}도서관에 나침반을 감췄다.",
                 f"A{word}는 나침반을 감췄다.", f"{word}는A 나침반을 감췄다."]
    chat = SimChat()
    for body in positives + negatives:
        chat.user("흰 구름이 흘렀다.")
        chat.reply(body)
    chat.user("계속")
    sync(client, chat)
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        head = conn.execute("SELECT head_commit_id FROM conversation").fetchone()["head_commit_id"]
        pattern = r"\m" + word + "(" + "|".join(_SOURCE_PARTICLES) + r")\M"
        oracle = conn.execute("SELECT rt.clean_content AS clean FROM active_membership am JOIN source_revision sr"
                              " ON sr.id=am.source_revision_id JOIN revision_text rt ON rt.source_revision_id=sr.id"
                              " AND rt.normalizer='clean-v3' WHERE am.commit_id=%s AND sr.lifecycle='accepted'"
                              " AND (word_similarity(%s,rt.clean_content)>=0.8::real OR rt.clean_content ~ %s)",
                              (head, word, pattern)).fetchall()
    rows, mode = keyword_rows(migrated, [word], particles=True)
    assert mode == "on" and {r["clean"] for r in rows} == {r["clean"] for r in oracle}
    assert {clean_text(body) for body in positives} <= {r["clean"] for r in rows}
    assert not (set(negatives) & {r["clean"] for r in rows})
