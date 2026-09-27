"""Phase 10 step 4 (ADR 0034): the scene cast and packet-v3's <Private> section."""

from __future__ import annotations

import uuid

from conftest import make_client
from nmos_sidecar.entities import resolve
from nmos_sidecar.packet import PACKET_NOTE, PRIVATE_NOTE, Line, compile_lines
from nmos_sidecar.scene import cast, private
from simchat import SimChat
from test_extraction import drain, filler
from test_generations import LLM
from test_semantics import row
from test_sidecar_integration import recall, sync

C = {"subject_type": "character"}


def scene(rows, query="", previous="", now=None):
    r = resolve(uuid.uuid4(), rows)
    return cast(rows, r, query, previous, now), r


def test_the_cast_is_the_last_turns_people_the_named_ones_and_the_persona():
    rows = [row(1, "라디아", "goal", None, "연구", **C), row(8, "블랑", "event", None, "출근", **C,
            participants=[{"name": "엘피", "type": "character"}]), row(9, "엘피", "has_status", None, "졸림", **C),
            row(9, "주방", "world_fact", None, "따뜻함", subject_type="place")]
    names, _ = scene(rows)
    assert sorted(names.values()) == ["{{user}}", "블랑", "엘피"]  # 라디아 is not in the last two turns
    names, _ = scene(rows, query="라디아 누나도 와.")
    assert "라디아" in names.values()  # named now: extraction lags a turn behind
    # The window ends before the current turn: with nothing extracted since turn 9, turn 13 has only the persona.
    assert sorted(scene(rows, now=13)[0].values()) == ["{{user}}"]
    assert sorted(scene(rows, now=10)[0].values()) == ["{{user}}", "블랑", "엘피"]
    # a name only ever in knowledge marks counts when it is said
    rows.append(row(2, "엘피", "goal", None, "몰래 보기", **C, knowledge="limited", known_by=["엘피"], hidden_from=["비올레"]))
    assert "비올레" in scene(rows, previous="비올레 이모가 문을 열었다.")[0].values()


def test_a_limited_fact_is_private_when_someone_in_the_scene_is_not_a_holder():
    rows = [row(9, "블랑", "event", None, "출근", **C), row(9, "엘피", "has_status", None, "졸림", **C)]
    names, r = scene(rows)
    secret = {"knowledge": "limited", "known_by": ["엘피", "{{user}}"], "hidden_from": ["블랑"]}
    shared = {"knowledge": "limited", "known_by": ["엘피", "블랑", "{{user}}"]}
    assert private(secret, names, r) and not private(shared, names, r)
    assert not private({"knowledge": "public"}, names, r) and not private({"knowledge": "unknown"}, names, r)
    assert not private(secret, {}, r)  # nobody known in the scene: nothing moves
    # The persona's names are one person: "유우마" in known_by is the persona when the host says so.
    r2 = resolve(uuid.uuid4(), rows, persona=["유우마"])
    names2 = cast(rows, r2)
    assert not private({"knowledge": "limited", "known_by": ["엘피", "블랑", "유우마"]}, names2, r2)


def fact(i: int, private: bool = False) -> Line:
    xml = f'    <Fact kind="goal" turn="{i}" known_by="엘피" hidden_from="블랑">엘피 goal: 비밀 {i}</Fact>'
    return Line("fact", xml, {"assertion": i}, i, f"엘피 goal: 비밀 {i}", f"비밀 {i}", private=private)


def test_packet_v3_moves_private_lines_and_adds_the_rule():
    lines = [fact(1), fact(2, private=True)]
    v3 = compile_lines([], 600, facts=lines, policy="packet-v3")
    body = v3.text.split("</Note>", 1)[1]
    assert "<Facts>" in body and "<Private>" in body and body.index("</Facts>") < body.index("<Private>")
    assert "비밀 2" in body.split("<Private>", 1)[1] and "비밀 1" not in body.split("<Private>", 1)[1]
    assert PRIVATE_NOTE.strip() in v3.text and v3.ledger[1]["private"] is True and "private" not in v3.ledger[0]
    v2 = compile_lines([], 600, facts=lines, policy="packet-v2")
    assert "<Private>" not in v2.text and PRIVATE_NOTE.strip() not in v2.text
    # with nothing private, packet-v3 is packet-v2
    assert compile_lines([], 600, facts=[fact(1)], policy="packet-v3").text == \
        compile_lines([], 600, facts=[fact(1)], policy="packet-v2").text
    # a packet of private lines only still has its frame and note
    only = compile_lines([], 600, facts=[fact(3, private=True)], policy="packet-v3").text
    assert only.startswith("<NarrativeMemory") and "<Facts>" not in only and PACKET_NOTE.removesuffix("</Note>") in only


def test_a_secret_goes_private_while_the_one_it_is_kept_from_is_in_the_scene(migrated, db):
    secret = [{"subject": "엘피", "subject_type": "character", "predicate": "goal", "value": "엄마 몰래 수업 보기",
               "knowledge": "limited", "known_by": ["엘피", "{{user}}"], "hidden_from": ["블랑"], "modality": "actual"}]
    blanc = [{"subject": "블랑", "subject_type": "character", "predicate": "event", "value": "출근 준비",
              "modality": "actual"}]

    def complete(system, user):
        target = user.split("TARGET", 1)[1]
        return {"assertions": (secret if "작전" in target else []) + (blanc if "출근" in target else [])}, "{}"

    with make_client(migrated, **LLM) as c:
        chat = SimChat()
        chat.user("엘피와 작전을 짠다.")
        chat.reply("엘피가 고개를 끄덕였다.")
        filler(chat, 3)
        chat.user("다음 날 아침.")
        chat.reply("블랑이 출근 준비를 한다.")
        chat.user("next")
        sync(c, chat)
        drain(migrated, complete)
        with_blanc = recall(c, chat, "엘피, 수업 작전 기억나?", in_context=[])["packet"]["text"]
        chat.reply("엘피는 방으로 들어갔다.")
        filler(chat, 3)
        chat.user("엘피와 둘이 남았다.")
        sync(c, chat)
        drain(migrated, complete)
        without = recall(c, chat, "엘피, 수업 작전 기억나?", in_context=[])["packet"]["text"]
    assert "엄마 몰래 수업 보기" in with_blanc.split("<Private>", 1)[1]  # 블랑 acted in the last turns
    assert "<Private>" not in without and "엄마 몰래 수업 보기" in without  # only holders in the scene now
    trace = db.execute("SELECT latency_ms FROM retrieval_trace ORDER BY created_at LIMIT 1").fetchone()["latency_ms"]
    assert "블랑" in trace["scene_cast"]


# --- per-chat memory mode (ADR 0035) -------------------------------------------------------------------------

from nmos_sidecar.scene import display, missing, narrator_knows  # noqa: E402


def test_the_narrator_knows_public_unmarked_and_their_own_facts():
    rows = [row(9, "블랑", "event", None, "출근", **C), row(9, "엘피", "has_status", None, "졸림", **C)]
    r = resolve(uuid.uuid4(), rows)
    assert narrator_knows({"knowledge": "public"}, "블랑", r) and narrator_knows({}, "블랑", r)
    assert narrator_knows({"knowledge": "limited", "known_by": ["엘피", "블랑"]}, "블랑", r)
    assert not narrator_knows({"knowledge": "limited", "known_by": ["엘피"], "hidden_from": ["블랑"]}, "블랑", r)
    assert narrator_knows({"knowledge": "limited", "known_by": ["{{user}}"]}, "{{user}}", r)


def test_a_withheld_line_names_the_persona_as_the_story_does():
    rows = [row(9, "블랑", "event", None, "출근", **C), row(9, "유우마", "event", None, "등교", **C)]
    r = resolve(uuid.uuid4(), rows, persona=["유우마"])
    holders, absent = missing({"knowledge": "limited", "known_by": ["엘피", "{{user}}", "유우마"]}, cast(rows, r), r)
    assert holders == ["엘피", "유우마"] and absent == ["블랑"]  # one persona, by the name the host reports
    assert display(r, "{{user}}") == "유우마" and display(r, "엘피") == "엘피"


def _secret_chat(migrated, c, complete):
    chat = SimChat()
    chat.user("엘피와 작전을 짠다: 엄마 몰래 수업 보기.")
    chat.reply("엘피가 고개를 끄덕였다.")
    filler(chat, 3)
    chat.user("다음 날 아침.")
    chat.reply("블랑이 출근 준비를 한다.")
    chat.user("next")
    sync(c, chat)
    drain(migrated, complete)
    return chat


SECRET = [{"subject": "엘피", "subject_type": "character", "predicate": "goal", "value": "엄마 몰래 수업 보기",
           "knowledge": "limited", "known_by": ["엘피", "{{user}}"], "hidden_from": ["블랑"], "modality": "actual"}]
BLANC = [{"subject": "블랑", "subject_type": "character", "predicate": "event", "value": "출근 준비", "modality": "actual"}]


def _complete(system, user):
    target = user.split("TARGET", 1)[1]
    return {"assertions": (SECRET if "작전" in target else []) + (BLANC if "출근" in target else [])}, "{}"


def test_strict_mode_withholds_and_a_narrator_drops_what_they_do_not_know(migrated, db):
    with make_client(migrated, **LLM) as c:
        chat = _secret_chat(migrated, c, _complete)
        conv = next(x for x in c.get("/v1/conversations").json() if x["host_chat_ref"] == chat.id)["id"]
        assert c.get(f"/v1/conversations/{conv}/memory-mode").json()["strict"] is False
        assert "블랑" in c.get(f"/v1/conversations/{conv}/memory-mode").json()["characters"]

        default = recall(c, chat, "엘피와 작전을 짠다", in_context=[])["packet"]["text"]
        assert "엄마 몰래 수업 보기" in default  # the fact; the excerpt saying it is skipped as a repeat of it
        assert c.put(f"/v1/conversations/{conv}/memory-mode", json={"strict": True}).json() == \
            {"strict": True, "narrator": None}
        strict = recall(c, chat, "엘피와 작전을 짠다", in_context=[])["packet"]["text"]
        assert "엄마 몰래 수업 보기" not in strict  # neither the fact nor the excerpt that says it
        assert '<Secret holders="엘피, {{user}}" not_known_by="블랑"' in strict and "<Private>" not in strict and "A Secret is something" in strict

        c.put(f"/v1/conversations/{conv}/memory-mode", json={"strict": False, "narrator": "블랑"})
        told_by_blanc = recall(c, chat, "블랑, 출근 준비는? 엘피는 수업 작전 기억나?", in_context=[])["packet"]["text"]
        assert "엄마 몰래 수업 보기" not in told_by_blanc and "<Secret" not in told_by_blanc
        assert "블랑 event: 출근 준비" in told_by_blanc and "told in the first person by 블랑" in told_by_blanc
        # With nothing the narrator knows, there is no packet at all.
        assert recall(c, chat, "엘피, 수업 작전 기억나?", in_context=[])["packet"]["text"] == ""
        c.put(f"/v1/conversations/{conv}/memory-mode", json={"strict": False, "narrator": "{{user}}"})
        told_by_user = recall(c, chat, "엘피, 수업 작전 기억나?", in_context=[])["packet"]["text"]
        assert "엄마 몰래 수업 보기" in told_by_user  # the user's character is a holder

        traces = db.execute("SELECT id, recall_options, latency_ms FROM retrieval_trace ORDER BY created_at").fetchall()
        assert [t["recall_options"]["strict"] for t in traces] == [False, True, False, False, False]
        assert [t["recall_options"]["narrator"] for t in traces] == [None, None, "블랑", "블랑", "{{user}}"]
        assert traces[1]["latency_ms"]["memory_mode_withheld"] >= 2  # the fact and the excerpt
        # A recorded request replays with its own mode, whatever the chat's mode is now.
        assert c.get(f"/v1/trace/{traces[1]['id']}/replay").json()["reproduced"] is True
        # The Inspector shows the last request's scene and mode (step 6).
        page = c.get(f"/inspector/c/{conv}", params={"lang": "en"}).text
        assert "Scene: {{user}}, 블랑, 엘피 · memory mode: narrator {{user}}" in page
        assert c.put(f"/v1/conversations/{conv}/memory-mode", json={"narrator": "x" * 61}).status_code == 422
        assert c.put("/v1/conversations/00000000-0000-0000-0000-000000000000/memory-mode", json={}).status_code == 404


def test_a_private_claim_shows_who_knows_it_in_the_private_section_only():
    from nmos_sidecar.facts import claim_entry
    c = {"id": 1, "turn": 3, "subject": "엘피", "subject_type": "character", "predicate": "goal", "value": "몰래 보기",
         "asserted_by": "엘피", "knowledge": "limited", "known_by": ["엘피"], "hidden_from": ["블랑"]}
    v3 = compile_lines([], 600, facts=[claim_entry(c, private=True)], policy="packet-v3").text
    assert '<Claim by="엘피" kind="goal" turn="3" known_by="엘피" hidden_from="블랑">' in v3 and "<Private>" in v3
    v2 = compile_lines([], 600, facts=[claim_entry(c, private=True)], policy="packet-v2").text
    assert '<Claim by="엘피" kind="goal" turn="3">' in v2 and "<Private>" not in v2  # earlier policies unchanged
    assert claim_entry(c).marks == {"by": "엘피", "hidden_from": ["블랑"]}  # an echo of it may be a leak (K11)
