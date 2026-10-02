"""Synthetic evidence for question-directed span selection; no benchmark answers."""
import pytest

from recall_answer_spans import select_span


@pytest.mark.parametrize('entries', [
    ['1. Close the west gate.', '2. Count the keys.', '3. Record the tide.'],
    ['"하나. 서쪽 문을 닫는다."', '"둘. 열쇠를 센다."', '"셋. 조수를 기록한다."'],
])
def test_document_question_keeps_the_real_list_as_a_contiguous_source(entries):
    source = 'The cedar memo was put on the table.\n' + '\n'.join(entries) + '\nUnrelated conversation.'
    result = select_span(source, 'What are the contents of the cedar memo?', ['cedar','memo'], 500)
    assert result is not None and result.kind == 'enumerated'
    selected = source[result.start:result.end]
    assert all(item in selected for item in entries)
    assert 'Unrelated conversation' not in selected


def test_unrelated_list_does_not_override_the_existing_vector_focus():
    source = 'The grocery list.\n1. Apples.\n2. Bread.\n3. Rice.'
    assert select_span(source, 'What are the contents of the cedar memo?', ['cedar','memo'], 500) is None


def test_list_is_not_selected_for_an_ordinary_question():
    source = 'Cedar memo.\n1. West gate.\n2. Keys.\n3. Tide.'
    assert select_span(source, 'Who wrote the cedar memo?', ['cedar','memo'], 500) is None


def test_causal_span_preserves_the_explanation_instead_of_a_question():
    source = ('Why was the pump stopped?\n'
              'The pump stopped because its valve jammed. Due to the blockage pressure rose. '
              'Therefore the fuse opened.\nThe crew then left.')
    result = select_span(source, 'Why did the pump stop?', ['pump'], 160)
    assert result is not None and result.kind == 'causal'
    selected = source[result.start:result.end]
    assert 'valve jammed' in selected and 'fuse opened' in selected
    assert len(selected) <= 160


def test_a_list_larger_than_the_budget_is_not_claimed_complete():
    source = 'Cedar memo.\n1. ' + 'A' * 100 + '\n2. ' + 'B' * 100 + '\n3. ' + 'C' * 100
    assert select_span(source, 'What are its contents?', ['cedar','memo'], 80) is None


def test_causal_connectives_without_the_requested_topic_are_not_an_answer():
    source = 'Because the tide rose, the boat moved. Due to the wind it turned. Therefore it hit the quay.'
    assert select_span(source, 'Why did the pump stop?', ['pump'], 500) is None


def test_packing_question_uses_its_action_even_when_names_dominate_keywords():
    source = ('하린과 도윤은 감자를 옮기는 방법을 의논했다.\n'
              '작은 바구니가 있었다. 예전에 사과를 담았던 바구니였다.\n'
              '하린은 감자를 그 안에 놓고 천을 덮었다.\n그 뒤 집에 돌아갔다.')
    result = select_span(source, '하린이 감자를 뭐에 담아 갔더라?', ['하린','감자','갔더라'], 480)
    assert result is not None and result.kind == 'enclosure'
    selected = source[result.start:result.end]
    assert '바구니' in selected and '감자를 그 안에' in selected
    assert '집에 돌아갔다' not in selected


def test_ordinary_question_does_not_trigger_packing_selection():
    source = '감자를 담았던 바구니.\n하린이 덮개를 닫았다.'
    assert select_span(source, '하린은 무슨 일을 했어?', ['하린'], 480) is None
