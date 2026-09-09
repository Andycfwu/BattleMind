"""Bounded localhost viewer and independent read-only spectator connection.

Playback is in the browser. Only an explicit demo launch chooses policies; no
playback command, frame state or spectator output is ever an agent input.
"""

import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import urlsplit

from websockets.asyncio.client import connect

from .demo_bundle import verify, write
from .environment import ROOT, sha256, source_manifest
from .labels import read_jsonl
from .prediction_report import audit_predictions
from .runner import RunConfig, run
from .viewer_records import VERSION, public_line, terminal_lines, validate_replay

LIVE_POLICIES = ('random','max-base-power','gen1-heuristic','switch-logistic','learned-score')


def can_launch(ledger: dict) -> bool:
    return (ledger['state']=='idle' and ledger['requested']<ledger['maximum_games']
            and ledger['run_seconds']+75<=ledger['maximum_run_seconds'])


def demo_sources() -> dict:
    return {**source_manifest(),**{p.relative_to(ROOT).as_posix():sha256(p)
        for p in (ROOT/'src/battlemind/viewer').glob('*') if p.is_file()}}


class Spectator:
    def __init__(self, port: int, record: dict):
        self.port,self.record=port,record
        self.tags=set();self.queue=asyncio.Queue();self.error=None
        self.ended=asyncio.Event()

    def room(self, tag: str, index: int):
        if not tag.startswith('battle-gen1ou-') or index!=0:
            raise ValueError('Demo spectator supports one known Gen 1 room')
        if tag not in self.tags:
            self.tags.add(tag);self.queue.put_nowait(tag)

    async def __aenter__(self):
        self.ws=await connect(f'ws://127.0.0.1:{self.port}/showdown/websocket',proxy=None,open_timeout=3)
        self.tasks=[asyncio.create_task(self.join()),asyncio.create_task(self.receive())]
        return self

    async def join(self):
        try:
            while True:
                tag=await self.queue.get()
                await self.ws.send('|/join '+tag)
        except asyncio.CancelledError: raise
        except Exception as exc: self.error=str(exc);self.ended.set()

    async def receive(self):
        try:
            async for message in self.ws:
                lines=str(message).split('\n')
                if not lines[0].startswith('>') or lines[0][1:] not in self.tags: continue
                for line in lines[1:]:
                    if line.startswith(('|error|','|bigerror|','|popup|')):
                        raise ValueError('Unexpected spectator server error: '+line[:300])
                    if line.startswith(('|win|','|tie|')): self.ended.set()
                    clean=public_line(line)
                    if clean: self.record['lines'].append(clean)
        except asyncio.CancelledError: raise
        except Exception as exc: self.error=str(exc);self.ended.set()

    async def terminal(self,row):
        await asyncio.wait_for(self.ended.wait(),5)
        if self.error or not self.record['lines']:
            raise ValueError('Spectator collection failed: '+str(self.error))
        self.record.update(status=row['status'],outcome=row['winner'] if row['status']=='completed' else None,detail=row.get('detail'))
        self.record['lines'] += terminal_lines(row)
        validate_replay(self.record)

    async def __aexit__(self,*args):
        for task in self.tasks: task.cancel()
        await asyncio.gather(*self.tasks,return_exceptions=True)
        await self.ws.close()


async def serve(bundle: Path, output: Path, port: int=8765, games: int=2, seconds: int=1800,
                recordings: Path | None=None):
    if not 0<=games<=8 or not 1<=seconds<=3600 or not 1024<=port<=65535 or port==8000:
        raise ValueError('Viewer: 0..8 games, 1..3600 service seconds, separate unprivileged port')
    verified=verify(bundle)
    output.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((bundle/'manifest.json').read_text())
    replays={i:json.loads((bundle/f'replays/{i}.json').read_text()) for i in manifest['replays']}
    imported_recordings={}
    if recordings:
        for path in sorted(recordings.glob('*.json')):
            record=json.loads(path.read_text());validate_replay(record)
            if record['status']=='running' or record['id'] in replays:
                raise ValueError('Imported playback must be a finished unique public record')
            record['origin']='recorded spectator stream'
            replays[record['id']]=record
            imported_recordings[path.name]=sha256(path)
    token=secrets.token_hex(24)
    pending=asyncio.Queue();loop=asyncio.get_running_loop();stop=asyncio.Event()
    ledger={'schema_version':'v7-demo-budget-1','purpose':'functional demonstration only; not benchmark evidence',
        'requested':0,'maximum_games':games,'maximum_run_seconds':300,'run_seconds':0.0,'state':'idle','runs':[],
        'source':demo_sources(),'bundle_manifest_sha256':verified['manifest_sha256'],
        'imported_public_recordings':imported_recordings}
    write(output/'ledger.json',ledger)
    # Exact endpoint maps. Neither models nor observer/private audit inputs are served.
    files={'/':ROOT/'src/battlemind/viewer/index.html',
           '/app.js':ROOT/'src/battlemind/viewer/app.js','/app.css':ROOT/'src/battlemind/viewer/app.css',
           '/boot.js':ROOT/'src/battlemind/viewer/boot.js'}
    files.update({'/assets/'+name:bundle/'assets'/name for name in
                 json.loads((ROOT/'configs/viewer-assets.json').read_text())['files']
                 if not name.startswith(('source/','licenses/'))})
    lock=threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_): pass

        def respond(self,status,data,content='application/json'):
            with (output/'http-requests.jsonl').open('a',encoding='utf-8') as log:
                log.write(json.dumps({'method':self.command,'path':urlsplit(self.path).path,'status':status})+'\n')
            self.send_response(status)
            self.send_header('Content-Type',content)
            self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'none'; media-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.end_headers();self.wfile.write(data)

        def valid_host(self):
            return self.headers.get('Host')==f'127.0.0.1:{port}'

        def do_GET(self):
            if not self.valid_host(): return self.respond(403,b'{}')
            route=urlsplit(self.path).path
            if route in files:
                p=files[route];return self.respond(200,p.read_bytes(),mimetypes.guess_type(p.name)[0] or 'application/octet-stream')
            if route=='/api/state':
                # JSON serialization makes a detached display copy; browser cannot mutate state.
                data={'replays':[{k:r[k] for k in ('id','title','status','origin')} for r in replays.values()],
                    'ledger':{k:ledger[k] for k in ('requested','maximum_games','run_seconds','maximum_run_seconds','state')},
                    'policies':LIVE_POLICIES,'token':token,'live_adaptation':False}
                return self.respond(200,json.dumps(data).encode())
            if route.startswith('/api/replay/'):
                ident=route.removeprefix('/api/replay/')
                if ident in replays: return self.respond(200,json.dumps(replays[ident]).encode())
            self.respond(404,b'{"error":"Unknown endpoint"}')

        def do_POST(self):
            if (not self.valid_host() or self.headers.get('Origin') not in {None,f'http://127.0.0.1:{port}'}
                or self.headers.get('X-BattleMind-Token')!=token or self.headers.get('Content-Type')!='application/json'):
                return self.respond(403,b'{}')
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=512: raise ValueError('Invalid payload size')
                data=json.loads(self.rfile.read(length))
                if self.path=='/api/stop':
                    loop.call_soon_threadsafe(stop.set);return self.respond(200,b'{"stopping":true}')
                if self.path!='/api/demo' or set(data)!={'agent_a','agent_b'} or any(v not in LIVE_POLICIES for v in data.values()):
                    raise ValueError('Unknown demo request')
                with lock:
                    if not can_launch(ledger):
                        return self.respond(409,b'{"error":"Busy, stopped or demo budget exhausted"}')
                    ledger['state']='queued';write(output/'ledger.json',ledger)
                loop.call_soon_threadsafe(pending.put_nowait,data)
                self.respond(202,b'{"queued":true}')
            except (ValueError,TypeError) as exc:
                self.respond(400,json.dumps({'error':str(exc)}).encode())

    http=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    write(output/'service.json',{'schema_version':'v7-service-1','url':f'http://127.0.0.1:{port}','token':token})
    print(f'Viewer http://127.0.0.1:{port} | {games} game / 300s aggregate demo ceiling | Ctrl+C or stop-demo.ps1',flush=True)

    async def worker():
        while True:
            data=await pending.get()
            if demo_sources()!=ledger['source']: raise ValueError('Source changed during demo; restart before collection')
            ident=f'live-{ledger["requested"]+1}'
            while ident in replays:
                ident+='-new'
            record={'schema_version':VERSION,'id':ident,'title':f'Functional demo: {data["agent_a"]} vs {data["agent_b"]}',
                'origin':'live spectator stream; delayed playback','status':'running','outcome':None,'detail':None,
                'lines':[],'explanations':[],'provenance':{},'limitations':['Spectator playback may lag; simulation may already be finished.',
                    'No live individual adaptation. Learned-score uses the frozen V5 checkpoint.']}
            replays[ident]=record
            ledger['requested']+=1;ledger['state']='running';write(output/'ledger.json',ledger)
            started=time.monotonic();path=output/ident
            config=RunConfig(**data,battles=1,seed=71000+ledger['requested'],timeout=60,run_timeout=75,turn_cap=300,
                predictor=str((bundle/'predictor.json').resolve()) if any(v in {'switch-logistic','learned-score'} for v in data.values()) else None,
                checkpoint_a=str((bundle/'checkpoint.json').resolve()) if data['agent_a']=='learned-score' else None,
                checkpoint_b=str((bundle/'checkpoint.json').resolve()) if data['agent_b']=='learned-score' else None)
            try:
                verify(bundle)
                result=await run(config,path,True,spectator=Spectator(config.port,record))
                audit=audit_predictions(path)
                if result['invalid_action_incidents'] or result.get('unexpected_client_warning_records') or result.get('server_crash_reports'):
                    raise ValueError('Demo action/protocol validation failed')
                if result['crash'] or result['timeout'] or result['cancelled'] or result['not_started']:
                    raise ValueError('Demo collection incomplete; no further launch')
                if record['status']=='running': raise ValueError('Missing spectator terminal accounting')
                record['provenance']={'run_manifest_sha256':sha256(path/'run.json'),'match':0}
                write(output/f'public/{ident}.json',record)
                ledger['runs'].append({'path':ident,'summary':result,'audit':audit,'public_sha256':sha256(output/f'public/{ident}.json')})
                ledger['state']='idle'
            except asyncio.CancelledError:
                record.update(status='cancelled',outcome=None,detail='Viewer stopped; managed clients/engine cleaned up')
                record['lines']=[l for l in record['lines'] if not l.startswith(('|win|','|tie|'))]
                write(output/f'public/{ident}.json',record)
                ledger['state']='cancelled'
                raise
            except Exception as exc:
                record.update(status='crash',outcome=None,detail=str(exc))
                record['lines']=[l for l in record['lines'] if not l.startswith(('|win|','|tie|'))]
                ledger['state']='failed';ledger['error']=str(exc)
                write(output/f'public/{ident}.json',record)
            finally:
                ledger['run_seconds']+=time.monotonic()-started
                write(output/'ledger.json',ledger)

    task=asyncio.create_task(worker())
    stopper=asyncio.create_task(stop.wait())
    try:
        await asyncio.wait([task,stopper],timeout=seconds,return_when=asyncio.FIRST_COMPLETED)
        if task.done(): await task
    finally:
        task.cancel();stopper.cancel()
        await asyncio.gather(task,stopper,return_exceptions=True)
        # Runner cancellation performs client/engine cleanup. Close viewer afterward.
        await asyncio.to_thread(http.shutdown);http.server_close();thread.join(timeout=3)
        ledger['service_stopped']=True;write(output/'ledger.json',ledger)
    return {'output':str(output),'requested':ledger['requested'],'run_seconds':ledger['run_seconds'],'service_stopped':True}
