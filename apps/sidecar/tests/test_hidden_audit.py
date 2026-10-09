"""Hidden diagnostic provenance does not become an offered or echoed packet line."""
from __future__ import annotations

from copy import deepcopy
from uuid import uuid4

from nmos_sidecar import audit
from nmos_sidecar.retrieval import RecallOptions


def hidden(kind: str, ref: dict[str, int]) -> dict:
    return {"kind": kind, "ref": ref, "turn": 1, "text": "", "tok": 0,
            "placed": False, "why": "secret_withheld", "label": "hidden"}


def test_audit_keeps_placeholder_and_hidden_provenance_separate(monkeypatch):
    placeholder = {"kind": "secret", "ref": {"assertion": 1}, "turn": 1,
                   "text": "<Secret>concealed</Secret>", "content": "concealed", "tok": 5,
                   "placed": True, "why": "placed", "label": "required"}
    withheld = hidden("fact", {"assertion": 1})
    trace = {"id": uuid4(), "lines": [placeholder], "query": "", "previous_ai": "",
             "token_estimate": 5, "budget_tokens": 600, "policy": "packet-v16"}
    monkeypatch.setattr(audit, "_trace", lambda *_: trace)
    monkeypatch.setattr(audit, "reply_after", lambda *_: ("ok", "concealed"))
    before = audit.audit(None, trace["id"])
    trace["lines"].append(withheld)
    result = audit.audit(None, trace["id"])
    assert result["summary"] == before["summary"]
    assert result["summary"]["offered"] == result["summary"]["placed"] == 1
    assert result["summary"]["placed_echoed"] == 1
    assert result["summary"]["unplaced_echoed"] == 0
    assert len(result["lines"]) == 2
    assert result["lines"][0]["ref"] == result["lines"][1]["ref"]
    assert result["lines"][0]["echoed"] is True
    assert result["lines"][1] == withheld
    assert "echo" not in result["lines"][1] and "echoed" not in result["lines"][1]
    assert trace["lines"] == [placeholder, withheld]


def test_compare_hidden_excerpt_does_not_count_as_an_offer(monkeypatch):
    visible = {"kind": "fact", "ref": {"assertion": 1}, "turn": 1, "text": "public memory",
               "tok": 5, "placed": True, "why": "placed", "label": "supportive"}
    lines = [visible]
    trace_id = uuid4()
    monkeypatch.setattr(audit, "audit", lambda *_: {"lines": [{**visible, "echoed": True}]})
    monkeypatch.setattr(audit, "replay", lambda *_: {"status": "ok", "tokens": 5, "lines": lines,
                                                   "reproduced": True})
    before = audit.compare(None, [trace_id], RecallOptions(), ("packet-v16",))
    lines.append(hidden("excerpt", {"revision": 2}))
    result = audit.compare(None, [trace_id], RecallOptions(), ("packet-v16",))
    assert result == before
    counts = result["policies"]["packet-v16"]
    assert counts["excerpt_offered"] == counts["excerpt_placed"] == 0
    assert counts["placed"] == {"fact": 1}
    assert counts["echoed_recorded"] == counts["echo_kept"] == 1
    assert counts["new_lines"] == 0


def test_hidden_addition_does_not_hide_an_old_replay_mismatch():
    original = [{"kind": "secret", "ref": {"assertion": 1}, "turn": 1, "tok": 5,
                 "text": "<Secret />", "placed": True, "why": "placed"}]
    current = [*original, hidden("fact", {"assertion": 1})]
    assert not audit._same(current, original)
    assert not audit._same(original, current)
    assert audit._same(current, deepcopy(current))
