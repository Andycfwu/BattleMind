"""Backend-only checks against an already running zero-game viewer. Collects no games."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.error
import urllib.request

p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
a=p.parse_args();state=json.loads((a.run/'service.json').read_text());url=state['url']
if not url.startswith('http://127.0.0.1:'):raise ValueError('Local test only')
before=(a.run/'ledger.json').read_bytes()
if json.loads(before)['maximum_games']!=0:raise ValueError('This check requires a zero-game viewer')

def request(path,body=None,headers=None):
    req=urllib.request.Request(url+path,data=json.dumps(body).encode() if body is not None else None,
        headers=headers or {},method='POST' if body is not None else 'GET')
    try:
        with urllib.request.urlopen(req,timeout=3) as r:return r.status,dict(r.headers),r.read()
    except urllib.error.HTTPError as e:return e.code,dict(e.headers),e.read()

results={}
for path in ['/predictor.json','/checkpoint.json','/memory-trace/run.json','/privileged/labels.jsonl',
             '/assets/../../predictor.json','/assets/source/LICENSE','/api/replay/../../predictor']:
    code,_,_=request(path);assert code==404,(path,code);results[path]=code
code,headers,_=request('/');assert code==200
assert "connect-src 'self'" in headers['Content-Security-Policy']
assert "media-src 'none'" in headers['Content-Security-Policy']
assert "font-src 'none'" in headers['Content-Security-Policy']
for key,value in [('Host','example.com'),('Origin','http://example.com')]:
    h={'Content-Type':'application/json','X-BattleMind-Token':state['token'],key:value}
    code,_,_=request('/api/demo',{'agent_a':'random','agent_b':'random'},h)
    assert code==403;results['reject_'+key]=code
h={'Content-Type':'application/json','X-BattleMind-Token':state['token']}
code,_,_=request('/api/demo',{'agent_a':'random','agent_b':'random'},h)
assert code==409;results['exhausted_budget']=code
code,_,_=request('/api/demo',{'agent_a':'unrecognized','agent_b':'random'},h)
assert code==400;results['unknown_policy']=code
code,_,_=request('/api/stop',{}, {'Content-Type':'application/json'})
assert code==403;results['stop_without_token']=code
assert before==(a.run/'ledger.json').read_bytes(),'Read/budget-denied operations mutated ledger'
result={'ok':True,'requested_games':0,'ledger_unchanged_sha256':hashlib.sha256(before).hexdigest(),'checks':results}
with a.output.open('x') as f:json.dump(result,f,indent=2)
print(json.dumps(result,indent=2))
