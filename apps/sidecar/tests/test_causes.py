"""Phase 11 step 6 (docs/phases/PHASE-11.md Q4, ADR 0040): the cause the story states, in the packet and linked to the
event it names. Nothing is inferred: without a stated cause there is none, and a link needs a clear match nearby."""

from __future__ import annotations

import uuid

from nmos_sidecar.entities import resolve
from nmos_sidecar.facts import cause_links, claim_line, fact_line, relevant_facts
from test_semantics import row

C = {"subject_type": "character", "object_type": "character"}


def angry(pos=10, because="카이토가 유이와의 약속을 잊고 장터에 가서", **kw):
    return row(pos, "유이", "feels_toward", "카이토", "화남", **C, because=because, **kw)


def test_packet_v6_carries_the_stated_cause_and_earlier_policies_do_not():
    f = angry()
    assert fact_line(f, cause=True).endswith(">유이 feels toward 카이토: 화남; because: 카이토가 유이와의 약속을 잊고 장터에 가서</Fact>")
    assert fact_line(f).endswith(">유이 feels toward 카이토: 화남</Fact>")
    assert "because" not in fact_line({**f, "because": None}, cause=True)
    claim = {**f, "source": "character_claim", "asserted_by": "유이"}
    assert claim_line(claim, cause=True).endswith("화남; because: 카이토가 유이와의 약속을 잊고 장터에 가서</Claim>")
    assert "because" not in claim_line(claim)


def test_a_why_question_brings_the_fact_that_has_a_cause():
    facts = [angry(10), row(12, "유이", "feels_toward", "하나", "고마움", **C),
             row(14, "유이", "relationship", "카이토", "소꿉친구", **C)]
    why = relevant_facts(facts, "유이는 왜 저래?", "", set(), 1, causes=True)
    assert why[0]["value"] == "화남"
    plain = relevant_facts(facts, "유이는 왜 저래?", "", set(), 1)
    assert plain[0]["value"] == "소꿉친구"  # packet-v5 and earlier: standing facts first (ADR 0026)
    # the cause's own words count too: only the cause names the forgotten promise
    q = "약속을 잊고 장터에 간 일"
    assert [f["value"] for f in relevant_facts(facts, q, "", set(), 3, causes=True)] == ["화남"]
    assert relevant_facts(facts, q, "", set(), 3) == []


def event(pos, subject, value, **kw):
    return row(pos, subject, "event", None, value, subject_type="character", **kw)


def test_a_cause_links_to_the_event_it_names_nearby_or_to_nothing():
    rows = [event(6, "카이토", "유이와의 약속을 잊고 하나와 장터에 감"), event(8, "하나", "장터에서 사과를 삼"), angry(10)]
    r = resolve(uuid.uuid4(), rows)
    cause_links(rows, [rows[0], rows[1]], r)
    assert rows[2]["cause_event"] == {"turn": 6, "position": 6, "text": "카이토 event: 유이와의 약속을 잊고 하나와 장터에 감"}
    far = [event(1, "카이토", "유이와의 약속을 잊고 하나와 장터에 감"), angry(10)]
    cause_links(far, [far[0]], resolve(uuid.uuid4(), far))
    assert "cause_event" not in far[1]  # nine turns back: another scene
    stranger = [event(6, "레온", "약속을 잊고 장터에 감"), angry(10)]
    cause_links(stranger, [stranger[0]], resolve(uuid.uuid4(), stranger))
    assert "cause_event" not in stranger[1]  # nobody of the pair took part
    names_only = [event(6, "카이토", "유이에게 편지를 씀"), angry(10, because="카이토가 유이에게 거짓말해서")]
    cause_links(names_only, [names_only[0]], resolve(uuid.uuid4(), names_only))
    assert "cause_event" not in names_only[1]  # shared names are not a shared event
