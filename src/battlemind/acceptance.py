"""Private request-bound evidence, separate from legacy labels and training eligibility.

Nothing here returns policy features, rewards, opponent labels or public projections.
The client writer sees only its own request/decision; joins run after both clients stop.
"""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import uuid

from .labels import snapshot_hash

SCHEMA = 'bm-acceptance-1'
ZERO = '0'*64


def digest(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def strict_json(text):
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise ValueError('Duplicate JSON key')
            result[key]=value
        return result
    def bad(value):raise ValueError('Nonfinite JSON')
    def finite(value):
        result=float(value)
        if not math.isfinite(result):raise ValueError('Nonfinite JSON')
        return result
    return json.loads(text,object_pairs_hook=pairs,parse_constant=bad,parse_float=finite)


class ChainWriter:
    def __init__(self, path: Path, *, session: str, build: str, channel: str, room: str | None=None):
        if not re.fullmatch('[a-f0-9]{32}',session) or not re.fullmatch('[a-f0-9]{64}',build):raise ValueError('Invalid recording identity')
        path.parent.mkdir(parents=True,exist_ok=True)
        self.stream=path.open('x',encoding='utf-8',newline='\n')
        self.base={'schema':SCHEMA,'session':session,'build':build,'room':room}
        self.seq=0;self.prev=ZERO;self.closed=False
        self.event('open',channel=channel)

    def event(self,kind,**fields):
        if self.closed:raise ValueError('Recording is already closed')
        body=json.dumps({**self.base,'kind':kind,**fields},ensure_ascii=False,separators=(',',':'),allow_nan=False)
        hashed=digest(self.prev+'\n'+body)
        self.seq+=1
        self.stream.write(json.dumps({'seq':self.seq,'prev':self.prev,'body':body,'hash':hashed},ensure_ascii=False,separators=(',',':'))+'\n')
        self.stream.flush();self.prev=hashed

    def close(self,complete=True):
        if self.closed:return
        self.event('close',complete=complete)
        self.closed=True;self.stream.close()


class ClientRecorder:
    """One private writer per player connection. Never reads engine/other-side files."""
    def __init__(self,path: Path,session: str,build: str):
        self.writer=ChainWriter(path,session=session,build=build,channel='client')
        self.session=session;self.connection=uuid.uuid4().hex;self.counter=0
        self.requests={};self.slots={};self.pending=None;self.room=None
        self.writer.event('connection',connection=self.connection)

    def request(self,room: str,raw: str):
        if self.room is not None and room!=self.room:raise ValueError('Use fresh recording clients for each battle')
        self.room=room
        req=strict_json(raw)
        if req is None:return
        rqid=req['rqid']
        if type(rqid) is not int or rqid<1:raise ValueError('Invalid request ID')
        key=(room,rqid)
        if key in self.requests and self.requests[key]!=raw:raise ValueError('Same request ID changed payload')
        self.requests[key]=raw
        slots=self.slots.setdefault(room,{})
        for mon in req.get('side',{}).get('pokemon',[]):
            ident=mon['ident'].split(': ',1)[-1]
            if ident not in slots:slots[ident]=len(slots)+1
        self.writer.event('request',room=room,rqid=rqid,raw=raw,request_sha256=digest(raw))

    def decision(self,row: dict,room: str,engine_side: str):
        if self.pending is not None:raise ValueError('Previous captured decision has not been submitted')
        if engine_side not in ('p1','p2'):raise ValueError('Unknown engine side')
        rqid=row['observation']['request_id'];raw=self.requests[(room,rqid)]
        if snapshot_hash(row['observation'])!=row['snapshot_sha256']:raise ValueError('Snapshot changed')
        req=strict_json(raw)
        if req['side']['id']!=engine_side:raise ValueError('Request belongs to another player')
        # Retain the original own-slot registry, not an inference from species/HP.
        slots=self.slots.setdefault(room,{})
        for mon in req['side']['pokemon']:
            key=mon['ident'].split(': ',1)[-1]
            if key not in slots:slots[key]=len(slots)+1
        positions=[slots[m['ident'].split(': ',1)[-1]] for m in req['side']['pokemon']]
        row=strict_json(json.dumps(row,allow_nan=False))
        validate_decision(row,req,positions)
        self.pending=(row,room,engine_side,raw,positions)

    def begin_send(self,command: str,room: str):
        if self.pending is None:raise ValueError('Submission has no captured decision')
        row,expected_room,side,raw,positions=self.pending
        if room!=expected_room or command!=row['command']:raise ValueError('Submission differs from decision')
        self.counter+=1;attempt=f'bm1-{self.session}-{self.connection}-{self.counter}'
        wire=command+'|'+attempt
        probabilities=row.get('policy_evaluation',{}).get('probabilities')
        index=[a['id'] for a in row['observation']['legal_actions']].index(row['chosen_action'])
        self.writer.event('attempt',room=room,side=side,attempt=attempt,connection=self.connection,
            operation='choose',
            attempt_number=self.counter,rqid=row['observation']['request_id'],request_sha256=digest(raw),
            decision=row,request_positions=positions,sampled_id=row['chosen_action'],
            sampled_probability=probabilities[index] if probabilities is not None else None,
            command=command,wire=wire)
        self.pending=None
        return attempt,wire

    def begin_cancel(self,room: str,rqid: int,engine_side: str):
        """Explicit orchestration operation, never an automatic policy retry."""
        raw=self.requests[(room,rqid)]
        if engine_side not in ('p1','p2'):raise ValueError('Unknown side')
        if strict_json(raw)['side']['id']!=engine_side:raise ValueError('Request belongs to another player')
        self.counter+=1;attempt=f'bm1-{self.session}-{self.connection}-{self.counter}'
        command=f'/undo |{rqid}';wire=command+'|'+attempt
        self.writer.event('cancel_attempt',room=room,side=engine_side,attempt=attempt,connection=self.connection,
            operation='undo',attempt_number=self.counter,rqid=rqid,request_sha256=digest(raw),
            command=command,wire=wire,sampled_id=None,sampled_probability=None)
        return attempt,wire

    def send_result(self,attempt,success):
        self.writer.event('send_result',attempt=attempt,success=success)

    def close(self,complete=True):self.writer.close(complete)


def validate_decision(row,request,positions):
    """Independently check the request menu/map; never fill observer fields from end logs."""
    obs=row['observation'];rqid=obs['request_id']
    if type(rqid) is not int or rqid<1 or obs['format']!='gen1ou':raise ValueError('Invalid observation request/format')
    if request['rqid']!=rqid or snapshot_hash(obs)!=row['snapshot_sha256']:raise ValueError('Snapshot/request identity mismatch')
    if request.get('wait') or request.get('teamPreview'):raise ValueError('Nonactionable request')
    if len(positions)!=len(request['side']['pokemon']) or any(type(p) is not int for p in positions) or sorted(positions)!=list(range(1,len(positions)+1)):raise ValueError('Invalid own slot registry')
    forced=bool(request.get('forceSwitch',[False])[0]);active=request.get('active',[{}])[0]
    if (obs['request_kind']=='forced_switch')!=forced:raise ValueError('Forcedness mismatch')
    mapping={}
    if not forced:
        for i,m in enumerate(active.get('moves',[]),1):
            if m.get('disabled') or m.get('pp',1)==0:continue
            mid=re.sub('[^a-z0-9]','',m.get('id',m['move']).lower())
            kind='engine' if mid in ('fight','struggle','recharge') else 'move'
            mapping[f'{kind}:{mid}']=f'/choose move {i}|{rqid}'
    own={m['slot']:m for m in obs['own_team']}
    for index,(slot,mon) in enumerate(zip(positions,request['side']['pokemon']),1):
        if own[slot]['active']!=mon['active']:raise ValueError('Request position changed')
        if (forced or not active.get('trapped')) and not mon['active'] and not mon['condition'].startswith('0'):
            mapping[f'switch:{slot}']=f'/choose switch {index}|{rqid}'
    mapping=dict(sorted(mapping.items(),key=lambda item:(item[0].startswith('switch:'),int(item[0].split(':')[1]) if item[0].startswith('switch:') else 0)))
    ids=[a['id'] for a in obs['legal_actions']]
    if list(mapping)!=ids or mapping!=row['legal_mapping'] or row['chosen_action'] not in mapping:raise ValueError('Legal menu/mapping mismatch')
    if mapping[row['chosen_action']]!=row['command']:raise ValueError('Resolved command changed')
    pe=row.get('policy_evaluation')
    if pe:
        p=pe['probabilities']
        if pe['legal_ids']!=ids or pe['chosen_action']!=row['chosen_action'] or len(p)!=len(ids):raise ValueError('Sampled IDs mismatch')
        if any(type(v) not in (float,int) or not math.isfinite(v) or v<=0 for v in p) or not math.isclose(sum(p),1,abs_tol=1e-12):raise ValueError('Invalid sampling distribution')
        draw=pe['draw']
        if type(draw) not in (int,float) or not math.isfinite(draw) or not 0<=draw<1:raise ValueError('Invalid draw')
        total=0.;index=len(p)-1
        for i,v in enumerate(p):
            total+=v
            if draw<total:index=i;break
        if ids[index]!=row['chosen_action']:raise ValueError('CDF selection mismatch')


def read_chain(path: Path,session: str,build: str,channel: str):
    if path.stat().st_size>256*1024*1024:raise ValueError('Oversized evidence stream')
    raw=path.read_bytes()
    if not raw.endswith(b'\n'):raise ValueError('Truncated/unsealed recording')
    prev=ZERO;events=[]
    for i,line in enumerate(raw.decode('utf-8').splitlines(),1):
        envelope=strict_json(line)
        if set(envelope)!={'seq','prev','body','hash'} or type(envelope['seq']) is not int or envelope['seq']!=i or envelope['prev']!=prev:raise ValueError('Broken sequence/chain')
        if digest(prev+'\n'+envelope['body'])!=envelope['hash']:raise ValueError('Corrupt evidence hash')
        prev=envelope['hash'];row=strict_json(envelope['body'])
        if row['schema']!=SCHEMA or row['session']!=session or row['build']!=build:raise ValueError('Engine/source/schema/session mismatch')
        events.append(row)
    if len(events)<2 or events[0]['kind']!='open' or events[0].get('channel')!=channel:raise ValueError('Missing stream header')
    if events[-1]['kind']!='close' or events[-1].get('complete') is not True:raise ValueError('Missing clean recording footer')
    if any(r['kind'] in ('close','open','fault','unbound_forward','unbound_input') for r in events[1:-1]):raise ValueError('Interrupted/unbound recording')
    return events


def validate_acceptance(client_paths: list[Path],room_path: Path,sim_path: Path,*,session: str,build: str,
                        engine_record: Path | None=None,engine_sha256: str | None=None) -> dict:
    """Status-only, fail-closed post-match join. No legacy label/eligibility changes."""
    result={'schema':'bm-acceptance-report-1','integrity':'unknown','attempts':[],
            'training_eligibility_changed':False,'execution':'not established by acceptance evidence'}
    try:
        return _validate(client_paths,room_path,sim_path,session,build,engine_record,engine_sha256,result)
    except (ValueError,KeyError,TypeError,OSError,IndexError,AttributeError) as exc:
        result.update(integrity='invalid_or_incomplete',attempts=[],reason=str(exc))
        return result


def _validate(client_paths,room_path,sim_path,session,build,engine_record,engine_sha256,result):
    attempts={};sends={};connections=set();rooms=set();side_connections={}
    for path in client_paths:
        requests={};counter=0;connection=None;slots={};last_request={}
        for e in read_chain(path,session,build,'client')[1:-1]:
            kind=e['kind']
            if kind=='connection':
                if not re.fullmatch('[a-f0-9]{32}',e['connection']) or connection is not None or e['connection'] in connections:raise ValueError('Reconnect/duplicate connection unsupported')
                connection=e['connection'];connections.add(connection)
            elif kind=='request':
                if connection is None:raise ValueError('Request precedes connection')
                req=strict_json(e['raw']);key=(e['room'],e['rqid'])
                if type(e['rqid']) is not int or e['rqid']<last_request.get(e['room'],0):raise ValueError('Out-of-order client request')
                last_request[e['room']]=e['rqid']
                if req['rqid']!=e['rqid'] or digest(e['raw'])!=e['request_sha256']:raise ValueError('Corrupt raw request')
                if key in requests and requests[key]!=e['raw']:raise ValueError('Conflicting repeated request')
                requests[key]=e['raw']
                registry=slots.setdefault(e['room'],{})
                for mon in req.get('side',{}).get('pokemon',[]):
                    ident=mon['ident'].split(': ',1)[-1]
                    if ident not in registry:registry[ident]=len(registry)+1
            elif kind in ('attempt','cancel_attempt'):
                counter+=1;aid=e['attempt'];rooms.add(e['room'])
                if type(e['attempt_number']) is not int or type(e['rqid']) is not int or e['attempt_number']!=counter or aid!=f'bm1-{session}-{connection}-{counter}' or e['connection']!=connection:raise ValueError('Corrupt attempt identity/order')
                if aid in attempts or e['side'] not in ('p1','p2'):raise ValueError('Duplicate attempt/side')
                if e['side'] in side_connections and side_connections[e['side']]!=connection:raise ValueError('Reconnect/side reuse unsupported')
                side_connections[e['side']]=connection
                raw=requests[(e['room'],e['rqid'])];req=strict_json(raw)
                if req['side']['id']!=e['side']:raise ValueError('Cross-player request linkage')
                if digest(raw)!=e['request_sha256']:raise ValueError('Request hash mismatch')
                if e['wire']!=e['command']+'|'+aid:raise ValueError('Wire command mismatch')
                if kind=='attempt':
                    positions=[slots[e['room']][m['ident'].split(': ',1)[-1]] for m in req['side']['pokemon']]
                    if positions!=e['request_positions'] or e['operation']!='choose':raise ValueError('Own position/operation mismatch')
                    validate_decision(e['decision'],req,positions)
                    if e['sampled_id']!=e['decision']['chosen_action'] or e['command']!=e['decision']['command']:raise ValueError('Attempt/command mismatch')
                    pe=e['decision'].get('policy_evaluation');prob=None if not pe else pe['probabilities'][pe['legal_ids'].index(e['sampled_id'])]
                    if (prob is not None and type(e['sampled_probability']) not in (int,float)) or prob!=e['sampled_probability']:raise ValueError('Sampled probability changed')
                elif e['operation']!='undo' or e['command']!=f"/undo |{e['rqid']}" or e['sampled_id'] is not None or e['sampled_probability'] is not None:
                    raise ValueError('Invalid cancellation attempt')
                req.pop('rqid');e['_engine_request_hash']=digest(json.dumps(req,sort_keys=True,ensure_ascii=False,separators=(',',':')))
                attempts[aid]=e
            elif kind=='send_result':
                if e['attempt'] not in attempts or e['attempt'] in sends or type(e['success']) is not bool:raise ValueError('Send-result linkage mismatch')
                sends[e['attempt']]=e['success']
            else:raise ValueError('Unsupported client event')
    if len(rooms)!=1 or not attempts:raise ValueError('Expected exactly one recorded battle')
    room=next(iter(rooms));received={};forwarded={};rejected=set();room_requests={};receipt_order={}
    room_events=read_chain(room_path,session,build,'room');sim_events=read_chain(sim_path,session,build,'sim')
    if any(e['room']!=room for e in [*room_events,*sim_events]):raise ValueError('Stream room mismatch')
    for e in room_events[1:-1]:
        if e['room']!=room:raise ValueError('Wrong room')
        kind=e['kind']
        if kind=='request':
            key=(e['side'],e['rqid'])
            if key in room_requests:raise ValueError('Duplicate engine request identity')
            room_requests[key]=e['request_sha256'];continue
        aid=e['attempt']
        if aid not in attempts:raise ValueError('Unbound room attempt')
        a=attempts[aid]
        prefix='/choose ' if a['operation']=='choose' else '/undo '
        if e['side']!=a['side'] or e['rqid']!=a['rqid'] or e['command']!=a['command'].removeprefix(prefix).split('|')[0] or e['operation']!=a['operation']:raise ValueError('Receipt identity/command mismatch')
        if kind=='received':
            if aid in received:raise ValueError('Duplicate receipt')
            if a['attempt_number']!=receipt_order.get(a['connection'],0)+1:raise ValueError('Receipt reordered or missing earlier attempt')
            receipt_order[a['connection']]=a['attempt_number']
            received[aid]=e
        elif kind=='forwarded':
            if aid not in received or aid in forwarded or aid in rejected:raise ValueError('Forward ordering')
            if e['current_rqid']!=a['rqid'] or e['request_sha256']!=a['request_sha256'] or room_requests[(a['side'],a['rqid'])]!=a['request_sha256']:raise ValueError('Stale/changed forwarded request')
            forwarded[aid]=e
        elif kind=='room_rejected':
            if aid not in received or aid in forwarded or aid in rejected:raise ValueError('Rejection ordering')
            rejected.add(aid)
        else:raise ValueError('Unsupported room event')
    current=None;engine_requests={};parsed={};accepted={};commits={};dispositions={};branches={};last_index=-1;pending={};errors=set();cancelled_by=set();dispatched=set()
    for e in sim_events[1:-1]:
        if e['room']!=room:raise ValueError('Wrong simulator room')
        kind=e['kind']
        if kind=='engine_request':
            old=engine_requests.get(e['side'],{}).get('epoch',0)
            if e['side'] not in ('p1','p2') or type(e['epoch']) is not int or e['epoch']!=old+1:raise ValueError('Engine request epoch order')
            engine_requests[e['side']]={'epoch':e['epoch'],'sha256':e['sha256']};continue
        aid=e.get('attempt')
        if kind=='dispatch':
            if current is not None or aid not in forwarded or aid in dispatched:raise ValueError('Dispatch missing/repeated/out of order')
            a=attempts[aid]
            for k in ('side','rqid','current_rqid','request_sha256','command','operation'):
                if e[k]!=forwarded[aid][k]:raise ValueError('Forward/dispatch mismatch')
            if e['engine_request']!=engine_requests.get(a['side']) or e['engine_request']['sha256']!=a['_engine_request_hash']:raise ValueError('Simulator request content mismatch')
            current=aid;dispatched.add(aid)
        elif kind=='dispatch_end':
            if aid!=current:raise ValueError('Dispatch end mismatch')
            current=None
        elif kind in ('normalization','parsed','accepted','choice_error'):
            if aid!=current or aid not in attempts or e['side']!=attempts[aid]['side']:raise ValueError('Unbound simulator choice')
            if kind=='choice_error':
                if e['reason'] not in ('invalid','unavailable') or aid in errors:raise ValueError('Invalid error event')
                errors.add(aid)
            elif kind=='normalization':
                if aid in branches or e['reason'] not in ('locked_move','gen1_fight','no_enabled_moves'):raise ValueError('Unsupported normalization')
                branches[aid]=e['reason']
            elif kind=='parsed':
                if aid in parsed or type(e['ok']) is not bool:raise ValueError('Duplicate/invalid parse result')
                parsed[aid]=e['ok']
            else:
                if not parsed.get(aid) or aid in errors or aid in accepted or e['side'] in pending:raise ValueError('Acceptance without parse/replacement')
                a=attempts[aid];operation=a['command'].removeprefix('/choose ').split('|')[0]
                expected=operation if operation.startswith('switch ') else 'move '+a['sampled_id'].split(':',1)[1]
                reason=branches.get(aid)
                if reason=='gen1_fight':expected='move fight'
                elif reason=='no_enabled_moves':expected='move struggle'
                elif reason=='locked_move':
                    if not re.fullmatch('move [a-z0-9]+',e['choice']):raise ValueError('Invalid normalized move')
                    expected=e['choice']
                if e['choice']!=expected:raise ValueError('Normalization not supported by emitted branch')
                if len(e['actions'])!=1:raise ValueError('Only singles action evidence supported')
                view=e['actions'][0]
                if set(view)!={'kind','move_id','move_slot','target_location','switch_position'}:raise ValueError('Unexpected private action fields')
                if any(view[k] is not None and type(view[k]) is not int for k in ('move_slot','target_location','switch_position')):raise ValueError('Invalid normalized action numeric fields')
                if e['choice'].startswith('move '):
                    if view['kind']!='move' or view['move_id']!=e['choice'][5:] or view['switch_position'] is not None:raise ValueError('Conflicting normalized action')
                elif view['kind']!=('instaswitch' if a['decision']['observation']['request_kind']=='forced_switch' else 'switch') or view['switch_position']!=int(e['choice'].split()[1]) or view['move_id'] is not None:
                    raise ValueError('Conflicting switch position')
                accepted[aid]=e;pending[e['side']]=aid
        elif kind in ('replaced','cancelled'):
            if aid not in accepted or aid in commits or aid in dispositions or pending.get(e['side'])!=aid:raise ValueError('Invalid cancellation/replacement')
            if e.get('by')!=current:raise ValueError('Unbound cancellation/replacement request')
            dispositions[aid]=kind;del pending[e['side']]
            if kind=='cancelled':
                if attempts[current]['operation']!='undo':raise ValueError('Cancellation is not an undo operation')
                cancelled_by.add(current)
        elif kind=='committed':
            if aid not in accepted or aid in commits or aid in dispositions or pending.get(e['side'])!=aid:raise ValueError('Commit without current acceptance')
            if e['choice']!=accepted[aid]['choice'] or e['actions']!=accepted[aid]['actions'] or type(e['input_index']) is not int or e['input_index']<=last_index:raise ValueError('Conflicting committed choice')
            commits[aid]=e;last_index=e['input_index'];del pending[e['side']]
        else:raise ValueError('Unsupported simulator event')
    if current is not None:raise ValueError('Interrupted dispatch')
    official=None
    if engine_record is not None:
        raw=engine_record.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=engine_sha256:raise ValueError('Official end log hash mismatch')
        official=strict_json(raw.decode())
        if official['roomid']!=room:raise ValueError('Official room mismatch')
    for aid,a in attempts.items():
        status='unknown';reason='missing_receipt_or_acceptance'
        if aid in rejected:status='rejected';reason='explicit_room_gate_rejection'
        elif aid in errors or parsed.get(aid) is False:status='rejected';reason='explicit_engine_error_or_parse_failure'
        elif aid in cancelled_by:status='cancellation_applied';reason='explicit_engine_cancellation'
        elif aid in dispositions:status=dispositions[aid];reason='accepted_choice_invalidated_before_commit'
        elif aid in commits:
            commit=commits[aid]
            if official is None:reason='missing_official_end_log'
            elif official['inputLog'][commit['input_index']]!=f">{a['side']} {commit['choice']}":raise ValueError('Explicit commitment/index mismatch')
            else:status='committed';reason='request_attempt_parse_accept_commit_and_exact_end_log'
        elif aid in accepted:status='accepted_not_committed';reason='no_commit_for_this_accepted_attempt'
        if sends.get(aid) is not True:status='unknown';reason='missing_or_failed_client_send_result'
        result['attempts'].append({'attempt':aid,'side':a['side'],'rqid':a['rqid'],'sampled_id':a['sampled_id'],
            'sampled_probability':a['sampled_probability'],'status':status,'reason':reason,
            'normalization':branches.get(aid),'accepted_choice':accepted.get(aid,{}).get('choice'),
            'commit_index':commits.get(aid,{}).get('input_index')})
    result['integrity']='valid';result['counts']=dict(Counter(r['status'] for r in result['attempts']))
    return result


if __name__=='__main__':
    import argparse
    from .acceptance_build import verify_build
    parser=argparse.ArgumentParser(description='Read-only, post-match acceptance evidence report; never changes legacy labels.')
    parser.add_argument('--build',type=Path,required=True);parser.add_argument('--session',required=True)
    parser.add_argument('--clients',nargs='+',type=Path,required=True);parser.add_argument('--room',type=Path,required=True)
    parser.add_argument('--sim',type=Path,required=True);parser.add_argument('--engine',type=Path,required=True)
    parser.add_argument('--engine-sha256',required=True)
    args=parser.parse_args();identity=verify_build(args.build)
    result=validate_acceptance(args.clients,args.room,args.sim,session=args.session,build=identity['build_id'],
                               engine_record=args.engine,engine_sha256=args.engine_sha256)
    print(json.dumps(result,indent=2,allow_nan=False))
    raise SystemExit(0 if result['integrity']=='valid' else 1)
