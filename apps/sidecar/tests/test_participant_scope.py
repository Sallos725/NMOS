"""Evidence behind the Phase 8 draft (docs/phases/PHASE-8.md): the scope audit and the recall gap.

Both hold for the released code and keep holding after Phase 8: the audit is checked against the
recorded runs, and facts without participant data (every row of `extract-v7` and older, PHASE-8 Q5)
are selected only through their subject and object.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from nmos_sidecar.facts import relevant_facts

TOOL = Path(__file__).resolve().parents[3] / "tools" / "check_phase8_scope_audit.py"

# Three recorded events whose second person occurs only in the value (fixtures/model/phase*/).
EVENTS = [("유이", "카이토에게 은빛 열쇠를 건넸다"),
          ("산적들", "다리 위에서 카이토를 덮쳐 왔다"),
          ("카이토", "유이를 경비병들에게 넘겨주었다")]
SECOND = {"유이": "카이토", "산적들": "카이토", "카이토": "유이"}
QUERIES = ["{who}야, 오랜만이야.", "{who}, 괜찮아?", "{who}는 어디 있어?"]


def test_scope_audit_matches_the_recorded_runs():
    spec = importlib.util.spec_from_file_location("check_phase8_scope_audit", TOOL)
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    problems, audit = tool.check()
    assert problems == []
    table = tool.counts(audit)
    assert {p: table[p]["usable"] for p in table} == {"event": 51, "destroyed": 12, "goal": 5, "knows": 10,
                                                      "fulfilled": 0}


@pytest.mark.parametrize("salience", ["major", None])
@pytest.mark.parametrize("subject,value", EVENTS)
def test_without_participant_data_the_second_person_never_selects_the_fact(subject, value, salience):
    """PHASE-8 evidence: 0 of 18. Addressing the event's subject still selects it."""
    fact = {"subject": subject, "object": None, "predicate": "event", "value": value, "position": 10,
            "host_logical_id": "m10", "salience": salience, "names": [subject], "known_by": None,
            "hidden_from": None}
    for q in QUERIES:
        assert relevant_facts([fact], q.format(who=SECOND[subject]), "", set(), 8, events_limit=3) == []
    assert relevant_facts([fact], QUERIES[0].format(who=subject), "", set(), 8, events_limit=3) == [fact]
