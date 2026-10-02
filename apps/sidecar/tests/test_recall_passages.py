"""Synthetic fixtures verify local passage/source binding; they are not benchmark evidence."""
import array
import hashlib
import json
import math
import pytest
from recall_passages import PassageIndex,cosine


def index(tmp_path):
    source='The red sign marks the east exit. The blue sign marks the west exit.'
    first=source.index(' The blue')
    snippets=[source[:first],source[first:]]
    path=tmp_path/'passages';path.mkdir()
    rows=[]
    for i,text in enumerate(snippets):
        v=[0.0]*4096;v[i]=1.0
        with (path/(str(i)+'.f32')).open('wb') as f:array.array('f',v).tofile(f)
        rows.append({'revision':'R1','start':0 if i==0 else first,'end':first if i==0 else len(source),
                     'source_sha256':hashlib.sha256(source.encode()).hexdigest(),'text':text,'key':str(i)})
    (path/'manifest.json').write_text(json.dumps({'version':'passage-eval-v1','model':'qwen3-embedding:8b','entries':rows}))
    q=[0.0]*4096;q[1]=1.0
    p=tmp_path/'query-vectors';p.mkdir()
    (p/'q.json').write_text(json.dumps({'identity':{'model':'qwen3-embedding:8b','text':'QUERY'},'vector':q}))
    return PassageIndex(tmp_path),source


def test_selects_relevant_contiguous_source_with_provenance(tmp_path):
    ix,source=index(tmp_path);r=ix.best('R1',source,'QUERY')
    assert r['text']==' The blue sign marks the west exit.'
    assert source[r['start']:r['end']]==r['text']
    assert r['similarity']==pytest.approx(1) and r['generation']


def test_unprepared_source_has_no_new_candidate(tmp_path):
    ix,source=index(tmp_path)
    assert ix.best('UNKNOWN',source,'QUERY') is None


def test_changed_source_refused(tmp_path):
    ix,source=index(tmp_path)
    with pytest.raises(ValueError,match='immutable source'):
        ix.best('R1',source+' changed','QUERY')


def test_missing_query_cannot_invoke_a_model(tmp_path):
    ix,source=index(tmp_path)
    with pytest.raises(ValueError,match='not frozen'):
        ix.best('R1',source,'not cached')


@pytest.mark.parametrize('a,b',[([],[]),([1],[1,0]),([0,0],[1,0])])
def test_invalid_vectors_rejected(a,b):
    with pytest.raises(ValueError):cosine(a,b)


def test_cosine_ignores_magnitude():
    assert cosine([2,0],[1,1])==pytest.approx(1/math.sqrt(2))
