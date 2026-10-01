"""The re-extraction loss tool (tools/reextract_loss.py, PHASE-22 Q8): same-generation pairs, as "Needs attention" lists
them, and pairs across generations, measured only. Synthetic names only."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from conftest import make_client
from memeval import stub_extractor
from test_dropped import chat_of, damaged, forgetful
from test_extraction import drain
from test_generations import LLM
from test_sidecar_integration import sync

TOOL = Path(__file__).resolve().parents[3] / "tools/reextract_loss.py"
_spec = importlib.util.spec_from_file_location("reextract_loss", TOOL)
tool = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(tool)


def test_same_generation_counts_what_the_rebuild_lost_and_what_memory_dropped(migrated, capsys):
    chat = chat_of("Kaito is in the harbor.", "Hana is in the chapel. Hana is a knight. It is today.",
                   "Hana is a knight.", "Kaito is in the garden.")
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        damaged(c, migrated, chat)
    (conv,) = tool.measure(migrated)
    same = conv["same_generation"]
    # Four turns rebuilt; turn 1's occupation is lost by its turn, but turn 2 still states it: nothing dropped.
    assert (same["turns"], same["lost"], same["lost_by_predicate"], same["dropped"]) == (4, 1, {"identity": 1}, 0)
    assert same["facts"] == same["stated_again"] + same["lost"]
    assert conv["across_generations"]["turns"] == 0
    tool.main([migrated])
    out = capsys.readouterr().out
    assert "lost 1 {'identity': 1}, dropped 0 {}" in out


def test_across_generations_is_measured_and_not_listed(migrated):
    chat = chat_of("Kaito is in the harbor.", "Hana is a knight. It is today.")
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        sync(c, chat)
        drain(migrated, stub_extractor)
    with make_client(migrated, extract_backfill=100, llm_url=LLM["llm_url"], llm_model="fake-2"):
        drain(migrated, forgetful)  # a new generation that leaves the occupation out
    (conv,) = tool.measure(migrated)
    across, same = conv["across_generations"], conv["same_generation"]
    assert (across["turns"], across["lost"], across["lost_by_predicate"]) == (2, 1, {"identity": 1})
    assert across["facts"] == across["stated_again"] + across["lost"]
    assert (same["turns"], same["dropped"]) == (0, 0)  # a new generation is not listed (Q5)
