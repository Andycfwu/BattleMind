"""Synthetic source-grounded traces. Never substitutes for live engine verification.

Wrap/Clamp/fight cases model the branches in pinned side.ts:675-708 and the
retained audit's first mismatch names. Their raw requests are newly constructed,
not falsely presented as recovered historical requests or real battle outcomes.
"""
import copy
from dataclasses import asdict
import json
from pathlib import Path

import pytest

from battlemind.acceptance import (ChainWriter,ClientRecorder,digest,strict_json,
                                  validate_acceptance,read_chain)
from battlemind.adapter import snapshot_request
from battlemind.labels import snapshot_hash

SESSION='1'*32
BUILD='2'*64
ROOM='battle-gen1ou-fixture'


def payloads(path):return [json.loads(json.loads(line)['body']) for line in path.read_text().splitlines()]


def rewrite(path,events):
    # A temporary synthetic fixture mutation with recomputed chains tests semantic
    # checks, independently of the separate byte-corruption test.
    prev='0'*64;lines=[]
    for i,e in enumerate(events,1):
        body=json.dumps(e,ensure_ascii=False,separators=(',',':'));h=digest(prev+'\n'+body)
        lines.append(json.dumps(dict(seq=i,prev=prev,body=body,hash=h)));prev=h
    path.write_text('\n'.join(lines)+'\n',encoding='utf-8')


def row_for(request,tracker):
    obs,mapping=snapshot_request(request,1,tracker)
    data=json.loads(json.dumps(asdict(obs)));ids=[a['id'] for a in data['legal_actions']]
    return dict(observation=data,snapshot_sha256=snapshot_hash(data),chosen_action=ids[0],
        legal_mapping=mapping,command=mapping[ids[0]],decision_id='synthetic:request',
        policy_evaluation=dict(legal_ids=ids,chosen_action=ids[0],probabilities=[1/len(ids)]*len(ids),draw=0.))


@pytest.fixture
def make_trace(tmp_path,turn_request,tracker):
    counter=0
    def make(normalized=None,branch=None,commit=True,forced=False,engine=None,side='p1'):
        nonlocal counter
        counter+=1;root=tmp_path/str(counter);root.mkdir()
        req=copy.deepcopy(turn_request)
        if side=='p2':
            req['rqid']=8;req['side']['id']='p2'
            for m in req['side']['pokemon']:m['ident']=m['ident'].replace('p1:','p2:')
        if forced:req['forceSwitch']=[True];req.pop('active')
        if branch:req['active'][0]['maybeLocked']=True
        if engine:req['active'][0]['moves']=[dict(move=engine,id=engine,target='self')]
        local_tracker=copy.deepcopy(tracker)
        if side=='p2':local_tracker.own_slots={};local_tracker.own_boosts={}
        row=row_for(req,local_tracker);raw=json.dumps(req,separators=(',',':'))
        client=ClientRecorder(root/'client.jsonl',SESSION,BUILD);client.request(ROOM,raw)
        client.decision(row,ROOM,side);aid,wire=client.begin_send(row['command'],ROOM);client.send_result(aid,True);client.close()
        context=dict(side=side,attempt=aid,rqid=req['rqid'],current_rqid=req['rqid'],request_sha256=digest(raw),
                     command=row['command'].removeprefix('/choose ').split('|')[0],operation='choose',forwarded=False)
        server=ChainWriter(root/'room.jsonl',session=SESSION,build=BUILD,channel='room',room=ROOM)
        server.event('request',side=side,rqid=req['rqid'],request_sha256=digest(raw));server.event('received',**context)
        context['forwarded']=True;server.event('forwarded',**context);server.close()
        no_rqid={k:v for k,v in req.items() if k!='rqid'}
        engine_request=dict(epoch=1,sha256=digest(json.dumps(no_rqid,sort_keys=True,ensure_ascii=False,separators=(',',':'))))
        sim=ChainWriter(root/'sim.jsonl',session=SESSION,build=BUILD,channel='sim',room=ROOM)
        sim.event('engine_request',side=side,**engine_request);sim.event('dispatch',**context,engine_request=engine_request)
        if branch:sim.event('normalization',side=side,attempt=aid,reason=branch)
        sim.event('parsed',side=side,attempt=aid,ok=True)
        choice=normalized or ('switch 2' if forced else 'move '+row['chosen_action'].split(':')[1])
        view=dict(kind='instaswitch' if forced else 'move',move_id=None if forced else choice[5:],
                  move_slot=None if forced or branch else 0,target_location=None if forced or branch else 0,
                  switch_position=2 if forced else None)
        sim.event('accepted',side=side,attempt=aid,choice=choice,actions=[view])
        if commit:sim.event('committed',side=side,attempt=aid,choice=choice,actions=[view],input_index=0)
        sim.event('dispatch_end',attempt=aid);sim.close()
        end=dict(roomid=ROOM,inputLog=['>'+side+' '+choice] if commit else [])
        (root/'end.json').write_text(json.dumps(end))
        return root
    return make


def validate(root,**overrides):
    kwargs=dict(session=SESSION,build=BUILD,engine_record=root/'end.json',engine_sha256=digest((root/'end.json').read_text()))
    kwargs.update(overrides)
    return validate_acceptance([root/'client.jsonl'],root/'room.jsonl',root/'sim.jsonl',**kwargs)


@pytest.mark.parametrize('choice,branch',[(None,None),('move wrap','locked_move'),('move clamp','locked_move'),
    ('move fight','gen1_fight'),('move struggle','no_enabled_moves'),('move recharge','locked_move')])
def test_exact_and_source_supported_normalizations(make_trace,choice,branch):
    root=make_trace(choice,branch);before={p:p.read_bytes() for p in root.iterdir()}
    report=validate(root)
    assert report['integrity']=='valid',report
    assert report['counts']=={'committed':1}
    assert report['attempts'][0]['sampled_id']=='move:psychic'
    assert all(p.read_bytes()==raw for p,raw in before.items())


def test_many_to_one_preserves_sampled_id_probability(make_trace):
    first=make_trace('move wrap','locked_move');second=make_trace('move wrap','locked_move')
    events=payloads(second/'client.jsonl');a=next(e for e in events if e['kind']=='attempt');row=a['decision']
    row['chosen_action']='move:recover';row['command']=row['legal_mapping']['move:recover']
    row['policy_evaluation']['chosen_action']='move:recover';row['policy_evaluation']['draw']=.4
    a.update(sampled_id='move:recover',command=row['command'],wire=row['command']+'|'+a['attempt'])
    rewrite(second/'client.jsonl',events)
    for name in ('room.jsonl','sim.jsonl'):
        es=payloads(second/name)
        for e in es:
            if 'command' in e:e['command']='move 2'
        rewrite(second/name,es)
    a,b=validate(first),validate(second)
    assert a['counts']==b['counts']=={'committed':1}
    assert a['attempts'][0]['sampled_id']!=b['attempts'][0]['sampled_id']
    assert a['attempts'][0]['sampled_probability']==b['attempts'][0]['sampled_probability']==pytest.approx(1/3)


@pytest.mark.parametrize('kwargs',[{'forced':True},{'engine':'fight'},{'engine':'recharge'},{'engine':'struggle'}])
def test_forced_and_engine_requests(make_trace,kwargs):
    assert validate(make_trace(**kwargs))['counts']=={'committed':1}


def test_accepted_but_not_committed_is_distinct(make_trace):
    report=validate(make_trace(commit=False));assert report['counts']=={'accepted_not_committed':1}
    assert report['training_eligibility_changed'] is False


@pytest.mark.parametrize('mutation',['receipt_missing','commit_missing','end_missing','send_missing'])
def test_missing_evidence_is_never_inferred_from_silence(make_trace,mutation):
    root=make_trace()
    if mutation=='end_missing':report=validate(root,engine_record=None,engine_sha256=None)
    else:
        filename,kind={'receipt_missing':('room.jsonl','received'),'commit_missing':('sim.jsonl','committed'),'send_missing':('client.jsonl','send_result')}[mutation]
        rewrite(root/filename,[e for e in payloads(root/filename) if e['kind']!=kind]);report=validate(root)
    assert not any(a['status']=='committed' for a in report['attempts'])


@pytest.mark.parametrize('mutation',['duplicate','schema','build','rqid','normalized','position','input_index','request_hash','order','truncated','bytes'])
def test_corruption_is_invalid_not_repaired(make_trace,mutation):
    root=make_trace();file=root/'sim.jsonl';es=payloads(file)
    if mutation=='duplicate':es.insert(3,copy.deepcopy(es[2]))
    elif mutation in ('schema','build'):es[2][mutation]='incorrect'
    elif mutation=='rqid':es[2]['rqid']+=1
    elif mutation=='normalized':next(e for e in es if e['kind']=='accepted')['choice']='move blizzard'
    elif mutation=='position':next(e for e in es if e['kind']=='accepted')['actions'][0]['switch_position']=4
    elif mutation=='input_index':next(e for e in es if e['kind']=='committed')['input_index']=1
    elif mutation=='request_hash':es[2]['engine_request']['sha256']='0'*64
    elif mutation=='order':es[3],es[4]=es[4],es[3]
    elif mutation=='truncated':file.write_bytes(file.read_bytes()[:-1])
    elif mutation=='bytes':file.write_text(file.read_text().replace('psychic','blizzard',1))
    if mutation not in ('truncated','bytes'):rewrite(file,es)
    assert validate(root)['integrity']=='invalid_or_incomplete'


def test_stale_room_rejection_is_explicit(make_trace):
    root=make_trace();events=payloads(root/'room.jsonl')
    for e in events:
        if e['kind'] in ('received','forwarded'):
            e['current_rqid']=99
            if e['kind']=='forwarded':e['kind']='room_rejected'
    rewrite(root/'room.jsonl',events)
    se=payloads(root/'sim.jsonl');rewrite(root/'sim.jsonl',[e for e in se if e['kind'] in ('open','engine_request','close')])
    assert validate(root)['counts']=={'rejected':1}


def test_explicit_parse_rejection(make_trace):
    root=make_trace();events=payloads(root/'sim.jsonl')
    for e in events:
        if e['kind']=='parsed':e['ok']=False
    rewrite(root/'sim.jsonl',[e for e in events if e['kind'] not in ('accepted','committed')])
    assert validate(root)['counts']=={'rejected':1}


def test_repeated_requests_and_changed_payload(make_trace,tmp_path,turn_request):
    r=ClientRecorder(tmp_path/'repeat.jsonl',SESSION,BUILD);raw=json.dumps(turn_request)
    r.request(ROOM,raw);r.request(ROOM,raw)
    turn_request['active'][0]['moves'][0]['disabled']=True
    with pytest.raises(ValueError,match='changed payload'):r.request(ROOM,json.dumps(turn_request))
    r.close(False)
    with pytest.raises(ValueError,match='footer'):read_chain(tmp_path/'repeat.jsonl',SESSION,BUILD,'client')


def test_team_position_registry_follows_raw_request_order(tmp_path,turn_request,tracker):
    req=copy.deepcopy(turn_request);r=ClientRecorder(tmp_path/'positions.jsonl',SESSION,BUILD)
    r.request(ROOM,json.dumps(req));row=row_for(req,tracker);r.decision(row,ROOM,'p1')
    aid,_=r.begin_send(row['command'],ROOM);r.send_result(aid,True)
    req['rqid']=9;req['side']['pokemon'].reverse()
    req['side']['pokemon'][0]['active']=True;req['side']['pokemon'][1]['active']=False
    req['forceSwitch']=[True];req.pop('active')
    r.request(ROOM,json.dumps(req));row=row_for(req,tracker);r.decision(row,ROOM,'p1')
    aid,_=r.begin_send(row['command'],ROOM);r.send_result(aid,True);r.close()
    a=[e for e in payloads(tmp_path/'positions.jsonl') if e['kind']=='attempt'][-1]
    assert a['request_positions']==[2,1] and a['sampled_id']=='switch:1' and a['command']=='/choose switch 2|9'


@pytest.mark.parametrize('cancel',[False,True])
def test_replaced_or_cancelled_acceptance_cannot_become_old_commit(make_trace,cancel):
    root=make_trace(commit=False);client=payloads(root/'client.jsonl');a1=next(e for e in client if e['kind']=='attempt')
    a2=copy.deepcopy(a1);aid1=a1['attempt'];aid2=aid1.rsplit('-',1)[0]+'-2'
    a2.update(attempt=aid2,attempt_number=2)
    if cancel:
        a2.update(kind='cancel_attempt',operation='undo',command='/undo |7',wire='/undo |7|'+aid2,sampled_id=None,sampled_probability=None)
        a2.pop('decision');a2.pop('request_positions')
    else:
        row=a2['decision'];row['chosen_action']='move:recover';row['command']=row['legal_mapping']['move:recover']
        row['policy_evaluation'].update(chosen_action='move:recover',draw=.4)
        a2.update(sampled_id='move:recover',command=row['command'],wire=row['command']+'|'+aid2)
    sent=copy.deepcopy(next(e for e in client if e['kind']=='send_result'));sent['attempt']=aid2
    rewrite(root/'client.jsonl',client[:-1]+[a2,sent,client[-1]])
    room=payloads(root/'room.jsonl');extra=copy.deepcopy([e for e in room if e['kind'] in ('received','forwarded')])
    for e in extra:e.update(attempt=aid2,command='' if cancel else 'move 2',operation='undo' if cancel else 'choose')
    rewrite(root/'room.jsonl',room[:-1]+extra+[room[-1]])
    sim=payloads(root/'sim.jsonl');dispatch=copy.deepcopy(next(e for e in sim if e['kind']=='dispatch'))
    dispatch.update(attempt=aid2,command='' if cancel else 'move 2',operation='undo' if cancel else 'choose')
    base={k:dispatch[k] for k in ('schema','session','build','room')}
    extra=[dispatch,{**base,'kind':'cancelled' if cancel else 'replaced','side':'p1','attempt':aid1,'by':aid2}]
    if not cancel:
        extra.append({**base,'kind':'parsed','side':'p1','attempt':aid2,'ok':True})
        accepted=copy.deepcopy(next(e for e in sim if e['kind']=='accepted'));accepted.update(attempt=aid2,choice='move recover')
        accepted['actions'][0].update(move_id='recover',move_slot=1)
        extra += [accepted,{**accepted,'kind':'committed','input_index':0}]
        (root/'end.json').write_text(json.dumps(dict(roomid=ROOM,inputLog=['>p1 move recover'])))
    extra.append({**base,'kind':'dispatch_end','attempt':aid2})
    rewrite(root/'sim.jsonl',sim[:-1]+extra+[sim[-1]])
    result=validate(root)
    assert result['integrity']=='valid',result
    assert result['counts']==({'cancelled':1,'cancellation_applied':1} if cancel else {'replaced':1,'committed':1})
    # Even a same-text later entry cannot manufacture a commit for the invalidated ID.
    es=payloads(root/'sim.jsonl');bad=copy.deepcopy(next(e for e in es if e['kind']=='accepted'))
    bad.update(kind='committed',input_index=9);es.insert(-1,bad);rewrite(root/'sim.jsonl',es)
    assert validate(root)['integrity']=='invalid_or_incomplete'


def test_two_players_have_separate_journals_and_exact_commit_links(make_trace):
    a=make_trace();b=make_trace(side='p2')
    ae=payloads(a/'sim.jsonl');be=payloads(b/'sim.jsonl')
    ac=next(e for e in ae if e['kind']=='committed');bc=next(e for e in be if e['kind']=='committed');bc['input_index']=1
    combined=[e for e in ae[:-1] if e['kind']!='committed']+[e for e in be[1:-2] if e['kind']!='committed']+[ac,bc,be[-2],ae[-1]]
    rewrite(a/'sim.jsonl',combined)
    ar=payloads(a/'room.jsonl');br=payloads(b/'room.jsonl');rewrite(a/'room.jsonl',ar[:-1]+br[1:-1]+[ar[-1]])
    (a/'end.json').write_text(json.dumps(dict(roomid=ROOM,inputLog=['>p1 move psychic','>p2 move psychic'])))
    def check():return validate_acceptance([a/'client.jsonl',b/'client.jsonl'],a/'room.jsonl',a/'sim.jsonl',session=SESSION,build=BUILD,
        engine_record=a/'end.json',engine_sha256=digest((a/'end.json').read_text()))
    report=check();assert report['counts']=={'committed':2},report
    assert 'p2' not in {e.get('side') for e in payloads(a/'client.jsonl')}
    next(e for e in combined if e['kind']=='dispatch')['side']='p2';rewrite(a/'sim.jsonl',combined)
    assert check()['integrity']=='invalid_or_incomplete'


def test_private_mutations_do_not_change_policy_prediction_memory_or_viewer(make_trace,tracker,turn_request):
    from battlemind.schema import snapshot_from_dict
    from battlemind.reinforce import load_checkpoint,ReinforceAgent
    from battlemind.adaptation_experiment import artifacts
    from battlemind.opponent_memory import encounter_evidence,ObserverMemory
    from battlemind.environment import ROOT
    from battlemind.viewer_records import historical_replay
    root=make_trace('move wrap','locked_move');row=next(e['decision'] for e in payloads(root/'client.jsonl') if e['kind']=='attempt')
    snapshot=snapshot_from_dict(row['observation']);checkpoint=load_checkpoint(ROOT/'runs/reinforce-main/checkpoints/c0.json')
    model,_=artifacts()
    from test_adaptation import sequence
    public_snapshots,public_history=sequence(turn_request,tracker)
    (root/'privileged').mkdir()
    histories={'a':[{'turn':0,'kind':'switch','actor':None,'values':['alakazam','313/313']},
                   {'turn':0,'kind':'switch','actor':'opponent:1','values':['starmie','51/100']}],
               'b':[{'turn':0,'kind':'switch','actor':'opponent:1','values':['alakazam','100/100']},
                   {'turn':0,'kind':'switch','actor':None,'values':['starmie','164/323']}]}
    (root/'privileged/000-histories.json').write_text(json.dumps(histories));(root/'run.json').write_text(json.dumps({'config':{'battles':1,'format':'gen1ou','seed':42}}))
    (root/'battles.jsonl').write_text(json.dumps({'match':0,'status':'completed','winner':'a','player_roles':{'a':'p1','b':'p2'}})+'\n')
    def public_results():
        evidence=encounter_evidence(public_snapshots,public_history,model,True)
        assert evidence['admitted']==4
        memory=ObserverMemory()
        for ordinal in range(2):
            memory.begin('opaque',ordinal);summary=memory.finish('opaque',ordinal,evidence)
        assert summary.individual.encounters==2 and summary.individual.examples==8
        return (ReinforceAgent(checkpoint,10).act(snapshot),model.logistic.predict(snapshot),evidence,summary,historical_replay(root,0,'test','test'))
    before=public_results();snap_before=asdict(snapshot)
    (root/'sim.jsonl').write_text('corrupt private acceptance with opponent choices\n')
    (root/'end.json').write_text(json.dumps({'private_team':'changed','winner':'changed'}))
    assert validate(root)['integrity']=='invalid_or_incomplete'
    assert public_results()==before and asdict(snapshot)==snap_before


@pytest.mark.parametrize('field,value', [('sampled_probability',.99),('attempt_number',2),
    ('attempt_number',True),('rqid',98),('request_sha256','0'*64),('side','p2')])
def test_corrupt_client_identity_or_probability_is_rejected(make_trace,field,value):
    root=make_trace();events=payloads(root/'client.jsonl')
    next(e for e in events if e['kind']=='attempt')[field]=value
    rewrite(root/'client.jsonl',events)
    assert validate(root)['integrity']=='invalid_or_incomplete'


def test_reconnect_and_reused_connection_cannot_merge(make_trace):
    root=make_trace();es=payloads(root/'client.jsonl');es.insert(-1,copy.deepcopy(es[1]))
    rewrite(root/'client.jsonl',es)
    assert validate(root)['integrity']=='invalid_or_incomplete'


def test_stale_forward_and_boolean_commit_index_are_invalid(make_trace):
    root=make_trace();es=payloads(root/'room.jsonl')
    next(e for e in es if e['kind']=='forwarded')['current_rqid']=8
    rewrite(root/'room.jsonl',es)
    assert validate(root)['integrity']=='invalid_or_incomplete'
    root=make_trace();es=payloads(root/'sim.jsonl')
    next(e for e in es if e['kind']=='committed')['input_index']=False
    rewrite(root/'sim.jsonl',es)
    assert validate(root)['integrity']=='invalid_or_incomplete'


@pytest.mark.parametrize('raw',['{"value":1e999}','{"a":1,"a":2}','{"value":NaN}'])
def test_strict_json_rejects_nonfinite_or_duplicate_keys(raw):
    with pytest.raises(ValueError):strict_json(raw)


def test_cdf_exact_boundary_goes_to_next_sampled_action(turn_request,tracker):
    from battlemind.acceptance import validate_decision
    row=row_for(turn_request,tracker);pe=row['policy_evaluation'];pe['probabilities']=[.5,.25,.25];pe['draw']=.5
    with pytest.raises(ValueError,match='CDF'):validate_decision(row,turn_request,[1,2])
    row['chosen_action']=pe['chosen_action']='move:recover';row['command']=row['legal_mapping'][row['chosen_action']]
    validate_decision(row,turn_request,[1,2])


def test_cancellation_api_and_fresh_battle_boundary(tmp_path,turn_request):
    recorder=ClientRecorder(tmp_path/'client.jsonl',SESSION,BUILD);recorder.request(ROOM,json.dumps(turn_request))
    with pytest.raises(ValueError,match='another player'):recorder.begin_cancel(ROOM,7,'p2')
    aid,wire=recorder.begin_cancel(ROOM,7,'p1')
    assert wire=='/undo |7|'+aid
    with pytest.raises(ValueError,match='fresh recording'):recorder.request(ROOM+'-next',json.dumps(turn_request))
    recorder.send_result(aid,True);recorder.close()
    assert next(e for e in payloads(tmp_path/'client.jsonl') if e['kind']=='cancel_attempt')['sampled_probability'] is None


def test_client_hook_captures_only_current_request_before_send(monkeypatch,tmp_path,turn_request,tracker):
    import asyncio
    from types import SimpleNamespace
    from battlemind.acceptance_player import AcceptanceLocalPlayer
    from battlemind.runner import LocalPlayer
    captured=[];sent=[]
    async def transport(message,room='',message_2=None):sent.append((message,room,message_2));return 'sent'
    def init(player,**kwargs):
        player.ps_client=SimpleNamespace(send_message=transport)
        player.journal=SimpleNamespace(write=captured.append)
        player.trackers={ROOM:SimpleNamespace(role='p1')}
    async def ordered(player,messages):
        if messages[1][1]=='request':
            req=json.loads(messages[1][2]);row=row_for(req,tracker)
            assert len(player.acceptance_recorder.requests)==len(captured)+1
            player.journal.write(row)
            assert await player.ps_client.send_message(row['command'],ROOM)=='sent'
    monkeypatch.setattr(LocalPlayer,'__init__',init);monkeypatch.setattr(LocalPlayer,'_handle_battle_message',ordered)
    recorder=ClientRecorder(tmp_path/'client.jsonl',SESSION,BUILD)
    player=AcceptanceLocalPlayer(acceptance_recorder=recorder)
    second=copy.deepcopy(turn_request);second['rqid']=9
    asyncio.run(player._handle_battle_message([['>'+ROOM],['','request',json.dumps(turn_request)],['','request',json.dumps(second)]]))
    recorder.close();events=payloads(tmp_path/'client.jsonl')
    assert len(sent)==2 and [e['rqid'] for e in events if e['kind']=='attempt']==[7,9]
    assert [e['kind'] for e in events]==['open','connection','request','attempt','send_result','request','attempt','send_result','close']
    assert all(wire.startswith(row['command']+'|bm1-') for (wire,_,_),row in zip(sent,captured))


@pytest.mark.parametrize('failure',[False,True])
def test_seal_only_after_cleanup_returns(monkeypatch,tmp_path,failure):
    import asyncio
    from types import SimpleNamespace
    import battlemind.acceptance_player as module
    recorders=[ClientRecorder(tmp_path/f'{i}.jsonl',SESSION,BUILD) for i in range(2)]
    async def stop(players):
        assert all(not r.writer.closed for r in recorders)
        if failure:raise OSError('synthetic cleanup failure')
    monkeypatch.setattr(module,'close_players',stop)
    players=[SimpleNamespace(acceptance_recorder=r) for r in recorders]
    if failure:
        with pytest.raises(OSError):asyncio.run(module.close_acceptance_players(players))
    else:asyncio.run(module.close_acceptance_players(players))
    assert all(r.writer.closed for r in recorders)
    for i in range(2):assert payloads(tmp_path/f'{i}.jsonl')[-1]['complete'] is not failure
