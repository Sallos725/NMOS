"""ADR 0026: how the cast stand with each other outranks trivia, and takes the budget before threads.

The evidence case (owner report 2026-09-26, reproduced read-only from the owner's database): a character
agreed at turn 46 to speak 반말 to the persona, and at turn 63 went back to 존댓말. The packet built for
that reply held three threads and four `knows` facts about other characters; the agreement ranked 23rd
and her relationship to the persona 30th. The user's message named three characters, so every fact
about them had the same mention score, and a `known_by` list naming one of them decided the order.
The rows below are synthetic, shaped like that case.
"""

from __future__ import annotations

import re

from conftest import make_client
from nmos_sidecar.facts import relevant_facts
from nmos_sidecar.packet import compile_packet
from simchat import SimChat
from test_extraction import drain, filler
from test_sidecar_integration import recall, sync

BASE = {"object": None, "object_type": None, "host_logical_id": "x", "known_by": None, "hidden_from": None,
        "knowledge": "unknown", "salience": None, "epistemic": "stated"}
PERSONA = frozenset({"유우마"})
QUERY = ("“귀엽네.” 반대쪽 손으로 블랑의 머리를 쓰다듬는 유우마. “난 블랑도, 누나도 좋아하는데, 독차지 하려고?” "
         "블랑은 그 상황이 싫진 않았다. 라디아도 그 상황이 싫지는 않았다. 엘피는 아직 자고 있었다.")


def fact(position, subject, predicate, value, **extra):
    return {**BASE, "position": position, "turn": position // 2, "subject": subject, "predicate": predicate,
            "value": value, **extra}


def scene():
    trivia = [fact(100 + i, who, "knows", text, knowledge="limited", known_by=["블랑", "엘피", "라디아", "유우마"])
              for i, (who, text) in enumerate([
                  ("블랑", "유우마가 엘피에게 블랑은 교수님이라서 말을 못 한다고 말한 사실"),
                  ("블랑", "엘피와 유우마가 강의실 밖 복도에서 자신의 수업을 듣고 있었다"),
                  ("블랑", "유우마가 엘피의 재검토 자료에 내용을 추가했다는 사실"),
                  ("엘피", "계란은 식탁에 살살, 대신 한 번에 깨야 한다"),
                  ("엘피", "계란 껍질이 들어갔을 때 다른 껍질 조각으로 건져낼 수 있다")])]
    sister = fact(86, "라디아", "relationship", "누나", object="유우마", object_type="character",
                  knowledge="public")
    agreed = fact(92, "라디아", "event", "유우마에게 말을 놓기 시작함", salience="major", knowledge="public")
    return trivia, sister, agreed


def test_relationship_and_major_event_outrank_trivia_in_a_crowded_scene():
    trivia, sister, agreed = scene()
    picked = relevant_facts([*trivia, sister, agreed], QUERY, "", set(), 8, 3, PERSONA)
    assert picked[0] is sister
    assert picked[1] is agreed
    assert set(map(id, picked[2:])) == set(map(id, trivia))  # the rest still come, after them


def test_a_known_by_name_is_not_a_mention():
    # The fact's subject is not in the scene; only its known_by list is. It no longer comes by that alone.
    only_known = fact(120, "카이토", "knows", "지하실 열쇠의 위치", knowledge="limited", known_by=["블랑"])
    assert relevant_facts([only_known], "블랑, 오늘 수업 어땠어?", "", set(), 8, 3, PERSONA) == []
    # A character it is hidden from, addressed now, still brings it first (D19).
    hidden = {**only_known, "known_by": None, "hidden_from": ["블랑"]}
    assert relevant_facts([hidden], "블랑, 오늘 수업 어땠어?", "", set(), 8, 3, PERSONA) == [hidden]


def test_priors_order_equal_mentions_only():
    trivia, sister, agreed = scene()
    # Unmentioned: a prior never brings a fact by itself.
    assert relevant_facts([sister, agreed], "블랑, 오늘 수업 어땠어?", "", set(), 8, 3, PERSONA) == []
    # Mentioned only in the previous reply: below facts named in the user's message.
    picked = relevant_facts([trivia[0], sister], "블랑, 오늘 수업 어땠어?", "라디아가 문을 열었다.", set(), 8, 3,
                            PERSONA)
    assert picked == [trivia[0], sister]


LEAD = '    <Fact kind="relationship" turn="43" knowledge="public">라디아 relationship 유우마: 누나</Fact>'
THREADS = [f'    <Thread kind="promise" by="엘피" to="유우마" turn="{t}" knowledge="public">다음에 같이 요리하기 {t}</Thread>'
           for t in (55, 50, 39)]
OTHER = ['    <Fact kind="knows" turn="57">블랑 knows: 유우마가 재검토 자료에 내용을 추가했다는 사실</Fact>']


def test_lead_facts_take_the_budget_before_threads():
    full, _, _, kept = compile_packet([], 2000, facts=OTHER, threads=THREADS, lead_facts=[LEAD])
    assert kept == {"state": 0, "threads": 3, "facts": 2}
    assert full.index("<Threads>") < full.index("<Facts>")  # section order is unchanged
    assert full.index(LEAD) < full.index(OTHER[0])  # lead facts open the Facts section
    assert full.count("<Facts>") == 1
    # A budget with room for the lead fact and one thread: the lead fact is kept, then threads by rank.
    lead_only, _, _, _ = compile_packet([], 2000, lead_facts=[LEAD])
    one_thread, _, _, _ = compile_packet([], 2000, threads=THREADS[:1])
    budget = estimate(lead_only) + (estimate(one_thread) - frame()) + 2
    text, _, _, kept = compile_packet([], budget, facts=OTHER, threads=THREADS, lead_facts=[LEAD])
    assert LEAD in text and kept["facts"] == 1 and kept["threads"] == 1


def estimate(text: str) -> int:
    from nmos_sidecar.packet import estimate_tokens
    return estimate_tokens(text)


def frame() -> int:
    from nmos_sidecar.packet import PACKET_CLOSE, PACKET_NOTE, PACKET_OPEN
    return estimate("\n".join([PACKET_OPEN, PACKET_NOTE, PACKET_CLOSE]))


def test_the_trace_records_what_fit(migrated):
    def complete(system, user):
        target = user.split("TARGET", 1)[1]
        items = []
        if "누나" in target:
            items.append({"subject": "라디아", "subject_type": "character", "predicate": "relationship",
                          "object": "{{user}}", "object_type": "character", "value": "누나", "modality": "actual",
                          "knowledge": "public"})
        if "약속" in target:
            items += [{"subject": "엘피", "subject_type": "character", "predicate": "promised", "object": "{{user}}",
                       "object_type": "character", "value": f"같이 요리하기 {i}", "modality": "actual",
                       "knowledge": "public"} for i in range(3)]
        return {"assertions": items}, "{}"

    with make_client(migrated, llm_url="http://fake/v1", llm_model="fake") as c:
        chat = SimChat()
        chat.user("라디아를 누나라고 부른다.")
        chat.reply("라디아는 웃었다.")
        chat.user("엘피와 약속한다.")
        chat.reply("엘피가 새끼손가락을 걸었다.")
        filler(chat, 5)
        sync(c, chat)
        drain(migrated, complete)
        out = recall(c, chat, "라디아와 엘피가 들어왔다.", budget=260)
        timings = c.get(f"/v1/trace/{out['trace_id']}").json()["latency_ms"]
    text = out["packet"]["text"]
    assert "라디아 relationship {{user}}: 누나" in text  # the lead fact fit before any thread
    assert timings["facts"] == 1 and timings["kept_facts"] == 1
    assert timings["threads"] == 3 and timings["kept_threads"] == len(re.findall("<Thread ", text)) < 3
