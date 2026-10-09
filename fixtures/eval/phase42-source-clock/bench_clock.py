import os,sys,json,uuid,dataclasses,hashlib
from pathlib import Path
root=Path(os.environ.get('NMOS_BENCH_SOURCE', Path(__file__).resolve().parents[3]))
assert os.environ.get('NMOS_TEST_ADMIN_URL'), 'set a disposable PostgreSQL admin URL'
sys.path[:0]=[str(root/'apps/sidecar/src'),str(root/'tools'),str(root/'apps/sidecar/tests')]
import psycopg
from psycopg.rows import dict_row
from fastapi.testclient import TestClient
from bench_scale import ADMIN_URL,build_chat,p,post,sync,QUERIES
from nmos_sidecar.api import create_app
from nmos_sidecar.config import Settings
from nmos_sidecar.migrate import apply_migrations
from nmos_sidecar import retrieval
name='nmos_clock_bench_'+uuid.uuid4().hex[:8]
with psycopg.connect(ADMIN_URL,autocommit=True) as c:c.execute(f'CREATE DATABASE "{name}"')
url=ADMIN_URL.rpartition('/')[0]+'/'+name
rules=Path(os.environ.get('NMOS_BENCH_OUTPUT', '/tmp'))/'nmos-clock-bench-rules.json';rules.write_text(json.dumps({'rules':[{'id':'clock','card':'Clock benchmark','kind':'block','role':'char','start':r'☆ \[','end':r'\]\s*$','separator':'|'}]}))
result={'messages':10000,'model_calls':0,'method':'Synthetic 10k long-message corpus, 5000 clocks; in-process retrieve API; six alternating rounds of eight temporal queries, v18 source_clock off/on. No extraction, vectors, providers, warmup or individually cold-cache claims. Shared host; record concurrent workloads separately.','rows':[]}
from nmos_sidecar import api
original=api.retrieve
enabled=False
def retrieve(conn,request,options):
 return original(conn,request,dataclasses.replace(options,source_clock=enabled))
api.retrieve=retrieve
try:
 apply_migrations(url);chat=build_chat(10000)
 for j,item in enumerate(['은빛종','유리병','꽃다발','목걸이','부채','사진첩','모래시계','보석함']):
  chat.edit(101+j*400, f'서윤은 도윤에게 {item}을 건넸다. ' + '창밖의 거리에는 익숙한 풍경이 한없이 펼쳐져 있었다. ' * 50)
 for i,m in enumerate(chat.messages):
  if m['role']=='char':chat.edit(i,m['data']+f'\n☆ [Date: 0712-03-{i%28+1:02d} | Time: Morning]')
 with TestClient(create_app(Settings(database_url=url,packet_policy='packet-v18',parsers_file=str(rules)))) as client,psycopg.connect(url,row_factory=dict_row,autocommit=True) as db:
  print('syncing',flush=True);sync(client,chat,character_name='Clock benchmark');db.execute('ANALYZE');print('synced',flush=True)
  assert db.execute('SELECT count(*) AS n FROM state_observation').fetchone()['n']==10000
  for turn in range(6):
   for item in ['은빛종','유리병','꽃다발','목걸이','부채','사진첩','모래시계','보석함']:
    q=f'서윤이 도윤에게 {item}을 건넨 것은 언제였지?'
    for enabled in ([False,True] if turn%2==0 else [True,False]):
     r,ms=post(client,'/v1/retrieve',{'chat_id':chat.id,'query':q,'previous_ai':'','in_context_ids':[m['chatId'] for m in chat.messages[-40:]],'budget_tokens':4000})
     trace=client.get('/v1/trace/'+r['trace_id']).json()
     assert trace['recall_options']['source_clock']==enabled
     result['rows'].append({'round':turn+1,'enabled':enabled,'api_ms':round(ms,3),'clock_ms':trace['latency_ms'].get('source_clock',0),'stages':trace['latency_ms'],'added':trace['latency_ms']['placed'].get('source_time',0)})
   print('round',turn+1,flush=True)
  assert sum(x['added'] for x in result['rows'] if x['enabled']) > 0, 'clock route was not exercised'
  result['api_ms']={str(flag):{'p50':round(p(vals,.5),3),'p95':round(p(vals,.95),3)} for flag in [False,True] for vals in [[x['api_ms'] for x in result['rows'] if x['enabled']==flag]]}
  vals=[x['clock_ms'] for x in result['rows'] if x['enabled']]
  result['clock_ms']={'p50':p(vals,.5),'p95':p(vals,.95),'max':max(vals)}
finally:
 with psycopg.connect(ADMIN_URL,autocommit=True) as c:c.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
(Path(os.environ.get('NMOS_BENCH_OUTPUT', '/tmp'))/'nmos-clock-10k.json').write_text(json.dumps(result,indent=2))
print(json.dumps({k:v for k,v in result.items() if k!='rows'}))
