"""Synthetic tests for the selected evaluation candidate; no dataset-specific expectations."""
from __future__ import annotations
import copy
from pathlib import Path
import pytest
import recall_candidate as T
from nmos_sidecar import packet,retrieval


def candidate(**kw):
    return {'clean':'prefix exact source passage suffix','text_start':7,'text_end':27,'sim':0.7,**kw}


def test_vector_focus_preserves_original_and_source_offsets():
    c=candidate();before=copy.deepcopy(c);(out,)=T.focus_candidates([c],0.42)
    assert c==before
    assert out['clean']==before['clean'][7:27]
    assert out['full_clean']==before['clean']
    assert out['focus_span']=={'start':7,'end':27}
    assert out['clean'][out['text_start']:out['text_end']]==out['clean']


@pytest.mark.parametrize('change',[{'sim':0.2},{'sim':None},{'text_start':-1},{'text_end':100},
                                    {'text_start':25,'text_end':5},{'text_start':None}])
def test_invalid_or_weak_vector_keeps_original(change):
    c=candidate(**change)
    assert T.focus_candidates([c],0.42)==[c]


def test_current_query_alone_controls_context_expansion():
    content=' '.join(f'Archive note {i}.' for i in range(20))
    normal_query='Find the archive.'
    token=T._QUERY.set(normal_query)
    try:
        actual=T.focused_excerpt(content,'Find the archive. Previous reply asks why and its contents.', ['archive'],960)
        assert actual==packet.grown_excerpt(content,'archive',['archive'],960)
    finally:T._QUERY.reset(token)
    token=T._QUERY.set('Why was the archive closed?')
    try:
        long,short=T.focused_excerpt(content,'unrelated previous reply',['archive'],960)
        assert len(long)>len(actual[0]) and len(long)<=322
        assert short in long or short.strip('…') in long
    finally:T._QUERY.reset(token)


def test_scope_restored_after_failure(monkeypatch):
    monkeypatch.setattr(retrieval,'fuse',retrieval.fuse)
    monkeypatch.setattr(retrieval,'grown_excerpt',retrieval.grown_excerpt)
    def fail(*a,**kw):
        assert T._QUERY.get()=='Why now?'
        raise RuntimeError('synthetic read failure')
    wrapped=T.install(fail,Path('/tmp/unused'))
    with pytest.raises(RuntimeError):
        wrapped(None,None,'Why now?','',set(),retrieval.RecallOptions())
    assert T._QUERY.get()==''


def test_multilingual_details_cue_uses_current_query():
    assert T.DETAIL.search('이 기록의 내용은?')
    assert T.DETAIL.search('What are its contents?')
    assert not T.DETAIL.search('Find the archive.')


def test_answer_span_context_cannot_leak_after_a_failed_gather(monkeypatch):
    monkeypatch.setattr(retrieval, 'fuse', retrieval.fuse)
    monkeypatch.setattr(retrieval, 'grown_excerpt', retrieval.grown_excerpt)
    source = 'Cedar memo.\n1. West gate.\n2. Keys.\n3. Tide.'
    def fail(*args, **kwargs):
        retrieval.fuse([], [], 0.4, 0.42, [{'id': 'R1', 'position': 1,
                                          'clean': source, 'keyword_score': 1}])
        assert T._ANSWER_SPANS.get()
        raise RuntimeError('synthetic failure after choosing a span')
    wrapped = T.install(fail, Path('/tmp/unused'), answer_spans=True)
    before = T._QUERY.get(), T._ANSWER_SPANS.get(), T._CHAR_LIMIT.get()
    with pytest.raises(RuntimeError, match='synthetic failure'):
        wrapped(None, None, 'What are the contents of the cedar memo?', '', set(),
                retrieval.RecallOptions(excerpt_chars=500))
    assert (T._QUERY.get(), T._ANSWER_SPANS.get(), T._CHAR_LIMIT.get()) == before
