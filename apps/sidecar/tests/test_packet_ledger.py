"""Phase 9 (ADR 0027): the packet ledger, packet-v1 budgets, echo and replay."""

from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import make_client
from memeval import RECENT, StubEmbedder, _drain, _sync, settings_for, stub_extractor
from nmos_sidecar.extraction import process_extract
from nmos_sidecar.worker import run_once
from nmos_sidecar import audit
from nmos_sidecar.packet import (EXCERPT_SHARE, PACKET_CLOSE, PACKET_NOTE, PACKET_OPEN, STATE_SHARE, Excerpt, Line,
                                 StateItem, compile_lines, compile_packet, estimate_tokens)
from simchat import SimChat


# --- the compiler (pure) ---------------------------------------------------------------------------

def fact(n: int, words: str = "등대 꼭대기에서 바다를 오래 바라보는 버릇이 있다") -> Line:
    xml = f'    <Fact kind="has_trait" turn="{n}">하나 has trait: {words} {n}</Fact>'
    return Line("fact", xml, {"assertion": n}, n, f"하나 has trait: {words} {n}", f"{words} {n}")


QUOTE = Excerpt(turn=3, speaker="하나", text="…한참 뒤에야 하나가 입을 열었다. 금고 비밀번호는 보라일곱이야.", score=0.03,
                revision_id="r-quote", short="금고 비밀번호는 보라일곱이야.")
FRAME = estimate_tokens("\n".join([PACKET_OPEN, PACKET_NOTE, PACKET_CLOSE]))


def test_packet_v0_spends_the_budget_on_facts_and_drops_the_quote():
    out = compile_lines([QUOTE], 600, facts=[fact(i) for i in range(12)], policy="packet-v0")
    assert "보라일곱" not in out.text
    excerpt = [e for e in out.ledger if e["kind"] == "excerpt"]
    assert excerpt == [{**excerpt[0], "placed": False, "why": "budget"}]
    assert out.tokens <= 600


def test_packet_v1_keeps_room_for_the_best_excerpt():
    facts = [fact(i) for i in range(12)]
    out = compile_lines([QUOTE], 600, facts=facts, policy="packet-v1")
    assert "보라일곱" in out.text and out.tokens <= 600
    placed = [e for e in out.ledger if e["placed"]]
    assert [e["kind"] for e in placed].count("excerpt") == 1
    assert any(e["kind"] == "fact" for e in placed)  # facts still lead
    # every offered line is in the ledger, in offer order, with its provenance and cost
    assert [e["ref"] for e in out.ledger] == [{"assertion": i} for i in range(12)] + [{"revision": "r-quote"}]
    assert all(e["tok"] > 0 for e in out.ledger)
    assert {e["why"] for e in out.ledger if not e["placed"]} == {"budget"}


def test_packet_v1_shortens_an_excerpt_rather_than_dropping_it():
    long = Excerpt(turn=3, speaker="하나", text="바람이 커튼을 흔들었다. " * 20 + "금고 비밀번호는 보라일곱이야.", score=0.03,
                   revision_id="r-long", short="금고 비밀번호는 보라일곱이야.")
    out = compile_lines([long], 600, facts=[fact(i) for i in range(12)], policy="packet-v1")
    entry = next(e for e in out.ledger if e["kind"] == "excerpt")
    assert entry["placed"] and entry["form"] == "short" and entry["text"] == "금고 비밀번호는 보라일곱이야."
    assert "보라일곱" in out.text and "커튼" not in out.text
    reserve = int((600 - FRAME) * EXCERPT_SHARE)
    assert entry["tok"] <= reserve


def test_packet_v1_uses_the_whole_budget_when_nothing_competes():
    long = Excerpt(turn=3, speaker="하나", text="바람이 커튼을 흔들었다. 금고 비밀번호는 보라일곱이야.", score=0.03,
                   revision_id="r-long", short="금고 비밀번호는 보라일곱이야.")
    out = compile_lines([long], 600, policy="packet-v1")
    entry = out.ledger[0]
    assert entry["placed"] and "form" not in entry  # the full excerpt: no reason to shorten it


def test_packet_v1_caps_parser_state():
    state = [StateItem(key=f"npc{i}.hp", value=f"{i * 7} / 100, 상처 입음, 붕대를 감고 휴식 중", turn=i) for i in range(40)]
    out = compile_lines([QUOTE], 600, state=state, facts=[fact(1)], policy="packet-v1")
    kept = [e for e in out.ledger if e["kind"] == "state" and e["placed"]]
    assert sum(e["tok"] for e in kept) <= int((600 - FRAME) * STATE_SHARE)
    assert {e["why"] for e in out.ledger if e["kind"] == "state" and not e["placed"]} == {"state_cap"}
    assert "보라일곱" in out.text and "has trait" in out.text
    v0 = compile_lines([QUOTE], 600, state=state, facts=[fact(1)], policy="packet-v0")
    assert "보라일곱" not in v0.text and "has trait" not in v0.text  # state took everything


def test_packet_v1_skips_an_excerpt_that_restates_a_fact():
    same = Excerpt(turn=9, speaker="user", text="하나의 특징: 등대 꼭대기에서 바다를 오래 바라보는 버릇이 있다 1.", score=0.05,
                   revision_id="r-trait", short="하나의 특징: 등대 꼭대기에서 바다를 오래 바라보는 버릇이 있다 1.")
    out = compile_lines([same, QUOTE], 600, facts=[fact(i) for i in range(12)], policy="packet-v1")
    trait, quote = [e for e in out.ledger if e["kind"] == "excerpt"]
    assert not trait["placed"] and trait["why"] == "repeats" and "assertion" in trait["repeats"]
    assert quote["placed"] and "보라일곱" in out.text  # the room went to the next excerpt
    v0 = compile_lines([same, QUOTE], 600, facts=[fact(i) for i in range(12)], policy="packet-v0")
    assert not any(e["why"] == "repeats" for e in v0.ledger)


def test_nothing_placed_still_lists_what_was_offered():
    out = compile_lines([QUOTE], 100, facts=[fact(1)], policy="packet-v1")  # the frame alone is over budget
    assert out.text == "" and out.tokens == 0 and len(out.ledger) == 2 and not any(e["placed"] for e in out.ledger)


def test_compile_packet_keeps_the_v0_contract():
    text, tokens, chosen, kept = compile_packet([QUOTE], 600, facts=[fact(1).xml])
    assert "보라일곱" in text and chosen == [QUOTE] and tokens == estimate_tokens(text)
    assert kept == {"state": 0, "threads": 0, "facts": 1}


def test_unknown_policy_is_refused():
    with pytest.raises(ValueError):
        compile_lines([], 600, policy="packet-v9")


def test_echo_counts_reused_spans_the_request_did_not_contain():
    quote = '하나가 주위를 살피더니 속삭였다. "금고 비밀번호는 보라일곱이야.…'
    question = "하나야, 금고 비밀번호가 뭐였지?"
    # measured shape of a real reply: the key phrase only, not the excerpt (docs/perf/phase9-packets.md)
    assert audit.echoed(quote, '하나가 목소리를 낮추며 대답했다. "보라일곱이야. 아까도 말했잖아."', (question,))
    assert not audit.echoed(quote, "비밀번호는 모르겠어.", (question,))  # the question's words are not reuse
    wound = "검술보다 활을 더 잘 다루며 오른쪽 어깨에 오래된 화살 상처가 남아 있다"
    assert audit.echoed(wound, "하나는 오른쪽 어깨를 잠깐 만지작거렸다.", ("하나야, 어깨는 괜찮아?",))
    assert not audit.echoed(wound, "하나는 찻잔을 내려놓았다.")
    assert audit.echoed("the letter is forged", "Kaito must never learn the letter is forged.")
    assert not audit.echoed("the letter is forged", "the letter is here", ("what about the letter?",))
    assert audit.echo("검", "그는 검을 뽑았다") == 1.0 and audit.echo("검", "그는 활을 들었다") == 0.0
    assert audit.echo("", "anything") == 0.0 and audit.echo("text", None) == 0.0


# --- traces, audit and replay (database) ----------------------------------------------------------

@pytest.fixture
def full(migrated: str) -> Iterator[tuple]:
    """Extraction by the memeval stub extractor, no vectors (a replay needs no embedder)."""
    settings = {k: v for k, v in settings_for("full").items() if not k.startswith("embed_")} | {"embed_backfill": 0}
    with make_client(migrated, **settings) as c:
        yield c, migrated


def ask(client, chat: SimChat, text: str) -> dict:
    chat.user(text)
    _sync(client, chat)
    recent = chat.messages[-RECENT:]
    return client.post("/v1/retrieve", json={"chat_id": chat.id, "query": text, "previous_ai": "",
                                             "in_context_ids": [m["chatId"] for m in recent],
                                             "budget_tokens": 600}).json()


def story(client, url: str, vectors: bool = False) -> SimChat:
    chat = SimChat()
    chat.reply("Welcome to the story.")
    for user in ("Hana keeps a secret from Kaito: the letter is forged.", "Hana has the map.",
                 *[f"Idle chatter {i} about clouds." for i in range(4)]):
        chat.user(user)
        chat.reply("Noted.")
        _sync(client, chat)
    (_drain(url, "full") if vectors else extract(url))
    return chat


def extract(url: str) -> None:
    """Run the queued extraction jobs with the stub extractor (no vectors in these setups)."""
    from conftest import active_generation

    with db(url) as conn:
        gen = active_generation(conn, "extract")
        jobs = {"extract": (gen.key, lambda c, job: process_extract(c, job, stub_extractor, gen, gen.spec["context_turns"]))}
        while run_once(conn, jobs):
            pass


def db(url: str):
    return psycopg.connect(url, row_factory=dict_row, autocommit=True)


def test_a_trace_records_every_offered_line_with_provenance(full):
    client, url = full
    chat = story(client, url)
    out = ask(client, chat, "Kaito, what do you know about the letter?")
    trace = client.get(f"/v1/trace/{out['trace_id']}").json()
    assert trace["policy"] == "packet-v1" and trace["budget_tokens"] == 600
    assert trace["upto_position"] == len(chat.messages) - 1 and trace["previous_ai"] == ""
    assert trace["recall_options"]["facts_limit"] == 8
    facts = [e for e in trace["lines"] if e["kind"] == "fact"]
    assert facts and all(e["placed"] for e in facts)
    with db(url) as conn:
        for e in facts:  # each line leads to its assertion and the generation that extracted it
            row = conn.execute("SELECT x.extractor_key FROM assertion a JOIN extraction x ON x.id = a.extraction_id"
                               " WHERE a.id = %s", (e["ref"]["assertion"],)).fetchone()
            assert row["extractor_key"] == trace["extractor_key"]
    secret = next(e for e in facts if "forged" in e["text"])
    assert secret["marks"] == {"hidden_from": ["Kaito"]}
    assert trace["latency_ms"]["placed"]["fact"] == len(facts)


def test_replay_reproduces_the_packet_as_of_its_request(full):
    client, url = full
    chat = story(client, url)
    first = ask(client, chat, "Hana, what about the map?")
    recorded = client.get(f"/v1/trace/{first['trace_id']}").json()
    # The story goes on: more facts about Hana, extracted after the request.
    chat.reply("Noted.")
    for user in ("Hana has the lantern.", "Hana has the rope.", "Hana is in the chapel.", "Hana is a knight."):
        chat.user(user)
        chat.reply("Noted.")
        _sync(client, chat)
    extract(url)
    later = ask(client, chat, "Hana, what about the map?")
    assert "lantern" in later["packet"]["text"]  # the live read sees them
    again = client.get(f"/v1/trace/{first['trace_id']}/replay").json()
    assert again["status"] == "ok" and again["reproduced"] is True
    assert again["text"] == first["packet"]["text"] and "lantern" not in again["text"]
    assert again["lines"] == [{k: v for k, v in e.items()} for e in recorded["lines"]]
    other = client.get(f"/v1/trace/{first['trace_id']}/replay", params={"policy": "packet-v0"}).json()
    assert other["status"] == "ok" and "reproduced" not in other and other["policy"] == "packet-v0"
    assert client.get(f"/v1/trace/{first['trace_id']}/replay", params={"policy": "x"}).status_code == 422


def test_replay_refuses_when_the_story_before_the_request_changed(full):
    client, url = full
    chat = story(client, url)
    out = ask(client, chat, "Hana, what about the map?")
    chat.reply("Noted.")
    chat.edit(3, "Hana has the compass.")  # the map turn, before the request
    _sync(client, chat)
    assert client.get(f"/v1/trace/{out['trace_id']}/replay").json()["status"] == "changed"
    assert client.get(f"/v1/trace/{out['trace_id']}/audit").json()["summary"]["reply"] == "changed"


def test_echo_of_the_reply_that_followed(full):
    client, url = full
    chat = story(client, url)
    out = ask(client, chat, "Kaito, what do you know about the letter?")
    assert client.get(f"/v1/trace/{out['trace_id']}/audit").json()["summary"]["reply"] == "pending"
    chat.reply("Hana hesitates. Kaito must never learn that the letter is forged.")
    chat.user("…")
    _sync(client, chat)
    report = client.get(f"/v1/trace/{out['trace_id']}/audit").json()
    assert report["summary"]["reply"] == "ok"
    secret = next(e for e in report["lines"] if "forged" in e["text"])
    assert secret["echoed"] and secret["possible_leak"]
    assert report["summary"]["possible_leaks"] == 1


def test_a_reroll_of_the_reply_keeps_the_request_auditable(full):
    client, url = full
    chat = story(client, url)
    out = ask(client, chat, "Hana, what do you carry?")
    chat.reply("Hana shrugs.")
    _sync(client, chat)
    chat.reroll("Hana has the map, of course.")
    chat.user("…")
    _sync(client, chat)
    report = client.get(f"/v1/trace/{out['trace_id']}/audit").json()
    assert report["summary"]["reply"] == "ok"
    assert any(e.get("echoed") for e in report["lines"] if "map" in e["text"])
    assert client.get(f"/v1/trace/{out['trace_id']}/replay").json()["reproduced"] is True


def test_compare_policies_over_traces(full):
    client, url = full
    chat = story(client, url)
    ids = [ask(client, chat, q)["trace_id"] for q in ("Hana, what do you carry?",)]
    chat.reply("Hana has the map.")
    ids.append(ask(client, chat, "Kaito, what do you know about the letter?")["trace_id"])
    from nmos_sidecar.retrieval import RecallOptions

    with db(url) as conn:
        report = audit.compare(conn, ids, RecallOptions())
    assert report["traces"] == 2 and report["skipped"] == {}
    v0, v1 = report["policies"]["packet-v0"], report["policies"]["packet-v1"]
    assert v1["packets"] == v0["packets"] == 2 and v1["replayed_same_policy"] == v1["reproduced"] == 2
    assert v0["replayed_same_policy"] == 0
    # the first request's reply ("Hana has the map.") echoed the map fact, and both policies keep it
    assert v1["echoed_recorded"] >= 1 and v1["echo_kept"] == v1["echoed_recorded"] == v0["echo_kept"]


def test_traces_from_before_the_ledger_are_not_replayed(full):
    client, url = full
    chat = story(client, url)
    out = ask(client, chat, "Hana, what about the map?")
    with db(url) as conn:
        conn.execute("UPDATE retrieval_trace SET lines = NULL, upto_position = NULL WHERE id = %s", (out["trace_id"],))
    assert client.get(f"/v1/trace/{out['trace_id']}/replay").json()["status"] == "not_recorded"
    assert client.get(f"/v1/trace/{out['trace_id']}/audit").json()["summary"]["reply"] == "not_recorded"


def test_replay_ignores_vectors_and_facts_derived_after_the_request(migrated):
    """Bitemporal: the turn is on the head before the request, but embedded and extracted only after it."""
    with make_client(migrated, embedder=StubEmbedder(), **settings_for("full")) as client:
        chat = story(client, migrated, vectors=True)
        chat.user("하나는 은빛 열쇠를 등대 지하에 숨겼다.")
        chat.reply("그 비밀은 아무도 모른다.")
        for i in range(3):
            chat.user(f"Idle chatter {i} about rain.")
            chat.reply("Noted.")
        _sync(client, chat)  # not drained: no vector, no extraction for it yet
        query = "혹시 그 반짝이는 은빛 물건은 어디 숨겼지?"
        out = ask(client, chat, query)
        assert "등대 지하" not in out["packet"]["text"]
        _drain(migrated, "full")
        chat.reply("Noted.")  # ask the same question again, now that the turn is embedded
        live = ask(client, chat, query)
        assert "등대 지하" in live["packet"]["text"]
        again = client.get(f"/v1/trace/{out['trace_id']}/replay").json()
        assert again["status"] == "ok" and again["reproduced"] is True and again["notes"] == []
        assert "등대 지하" not in again["text"]


def test_inspector_shows_the_last_packet_ledger(full):
    client, url = full
    chat = story(client, url)
    ask(client, chat, "Kaito, what do you know about the letter?")
    chat.reply("Kaito must never learn that the letter is forged.")
    chat.user("…")
    _sync(client, chat)
    conv = client.get("/v1/conversations").json()[0]["id"]
    page = client.get(f"/inspector/c/{conv}", params={"lang": "en"}).text
    assert "Last packet: what went in" in page and "policy packet-v1" in page and "next reply: present" in page
    assert "a hidden fact reappears" in page and "the letter is forged" in page
    assert "fact 2" in page or "fact 1" in page  # the retrievals table counts what each packet held
    ko = client.get(f"/inspector/c/{conv}").text
    assert "마지막 패킷" in ko and "들어감" in ko


def test_the_users_own_message_is_never_recalled_as_memory(full):
    """The plugin anchors only messages of 16+ characters, so a short first message reached the sidecar
    with no in-context ids and came back as an excerpt of itself (Phase 9 real-host smoke)."""
    client, url = full
    chat = SimChat()
    chat.user("하나는 도서관으로 간다.")
    _sync(client, chat)
    out = client.post("/v1/retrieve", json={"chat_id": chat.id, "query": "하나는 도서관으로 간다.",
                                            "in_context_ids": [], "budget_tokens": 600}).json()
    assert out["packet"]["text"] == ""
    trace = client.get(f"/v1/trace/{out['trace_id']}").json()
    assert trace["lines"] == [] and trace["in_context"] == []  # the recorded request is what the plugin sent
    assert client.get(f"/v1/trace/{out['trace_id']}/replay").json()["reproduced"] is True


def test_replay_does_not_claim_reproduction_when_the_embedder_fails(migrated):
    from nmos_sidecar.llm import LLMError
    from nmos_sidecar.retrieval import RecallOptions

    class Down(StubEmbedder):
        def embed(self, texts, timeout_s):
            raise LLMError("embedder down")

    with make_client(migrated, embedder=StubEmbedder(), **settings_for("full")) as client:
        chat = story(client, migrated, vectors=True)
        out = ask(client, chat, "혹시 그 반짝이는 은빛 물건은 어디 숨겼지?")
        trace = client.get(f"/v1/trace/{out['trace_id']}").json()
        with db(migrated) as conn:
            again = audit.replay(conn, out["trace_id"], RecallOptions(embedder=Down(),
                                                                      embed_projection=trace["embed_projection"]))
        assert again["status"] == "ok" and "reproduced" not in again
        assert any(n.startswith("vectors fallback") for n in again["notes"])
