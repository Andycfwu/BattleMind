"""Single-use 48-game acceptance verification. No optimizer or eligibility updates.

Each phase runs in a separate process. Only its instrumented match call temporarily
binds the existing runner's player/cleanup factories; historical files and global
bindings in other processes are unchanged. Never use this as a training runner.
"""
import argparse
import asyncio
from collections import Counter
from contextlib import contextmanager
from dataclasses import asdict
import json
import os
from pathlib import Path
import shutil
import sys
import time

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psutil

from battlemind.environment import ROOT, LocalServer, executable, inspect_server
from battlemind import runner
from battlemind.acceptance import ClientRecorder, validate_acceptance, read_chain
from battlemind.acceptance_build import recording_environment, verify_build
from battlemind.acceptance_player import AcceptanceLocalPlayer, close_acceptance_players
from battlemind.adapter import resolve_action
from battlemind.labels import audit_labels, label_summary, read_jsonl, snapshot_hash
from battlemind.policies import make_policy
from battlemind.reinforce import load_checkpoint
from battlemind.reporting import JsonlWriter, known_gen1_warning, summarize
from battlemind.schema import snapshot_from_dict

SPEC = ROOT/'configs/acceptance-live-replacement.json'
INPUTS = ROOT/'configs/acceptance-required-inputs.json'
from diagnostics.acceptance_preflight import DeadlineIO, required_inputs, supervise
from diagnostics.acceptance_readiness import operational_preflight
DERIVED = ROOT/'.local/pokemon-showdown-acceptance-v1-r3'
OUTPUT = ROOT/'runs/acceptance-live-verification-replacement-1'
READINESS_INPUTS=('scripts/inspect-acceptance-runtime.cjs','diagnostics/acceptance_readiness.py')


def save(path, data):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(data, stream, indent=2, allow_nan=False)


def validate_spec(spec):
    expected={'maximum_games':48,'maximum_wall_seconds':600,'concurrency':1,'host':'127.0.0.1',
        'format':'gen1ou','turn_cap':300,'game_timeout_seconds':60,'policy_seed':260911,
        'policies':['reinforce-original-c0','random'],'training_updates':False,'eligibility_changes':False,
        'resume':False,'retries':False,'borrow_allocations':False,
        'phases':{'original':{'games':24,'seconds':180},'instrumented':{'games':24,'seconds':240},'overhead':{'games':0,'seconds':180}}}
    if any(spec.get(key)!=value for key,value in expected.items()):raise ValueError('Specification differs from authorized design')
    if spec['teams']!=['configs/teams/ou-v1-a.txt','configs/teams/ou-v1-b.txt','configs/teams/ou-v2-c.txt','configs/teams/ou-v2-d.txt']:
        raise ValueError('Fixed four-team pool changed')
    original=json.loads((ROOT/'configs/acceptance-live-verification.json').read_text())
    additions={'replacement_of','output','overhead_allocations','input_manifest','input_manifest_sha256'}
    if {k:v for k,v in spec.items() if k not in additions|{'schema','status'}} != {k:v for k,v in original.items() if k not in {'schema','status'}}:
        raise ValueError('Scientific verification differs from original specification')
    if spec.get('overhead_allocations')!={'preflight':100,'reporting_and_preservation':60,'cleanup_and_final_accounting':20}:
        raise ValueError('Replacement overhead allocation changed')
    if spec.get('output')!=OUTPUT.relative_to(ROOT).as_posix() or spec.get('input_manifest')!=INPUTS.relative_to(ROOT).as_posix():
        raise ValueError('Replacement output/input manifest differs')


class Budget:
    """Single-use reservations; workers never change scientific or policy settings."""
    def __init__(self, root, clock=time.monotonic):
        self.path=root/'ledger.json'; self.clock=clock
        self.data=json.loads(self.path.read_text())

    @classmethod
    def create(cls, root, specification, preflight_seconds=0., clock=time.monotonic):
        if not 0<=preflight_seconds<100:raise ValueError('Offline preflight exceeded allocation')
        started=clock()
        data={'schema':'bm-acceptance-live-ledger-2','state':'prepared',
            'started_monotonic':started,'preflight_seconds':preflight_seconds,
            'maximum_seconds':600,'maximum_games':48,'all_phases_reserved_before_collection':True,
            'cleanup_reserve_seconds':20,
            'preflight':{'state':'running','start':started,'maximum_seconds':100},
            'reporting':{'state':'reserved','maximum_seconds':60},
            'phases':{name:{'planned':24,'reserved':24,'requested':0,'state':'reserved',
                'maximum_seconds':specification['phases'][name]['seconds'],'requested_indices':[]}
                for name in ('original','instrumented')}}
        save(root/'ledger.json',data);return cls(root,clock)

    def write(self):
        temporary=self.path.with_suffix('.pending')
        temporary.write_text(json.dumps(self.data,indent=2)+'\n')
        temporary.replace(self.path)

    def reload(self):self.data=json.loads(self.path.read_text())

    def total(self):
        if 'total_seconds' in self.data:return self.data['total_seconds']
        return self.clock()-self.data['started_monotonic']+self.data['preflight_seconds']

    def overhead(self):
        if 'overhead_seconds' in self.data:return self.data['overhead_seconds']
        now=self.clock()
        phase_seconds=sum(p.get('seconds',now-p['start'] if p['state']=='running' else 0.) for p in self.data['phases'].values())
        return now-self.data['started_monotonic']+self.data['preflight_seconds']-phase_seconds

    def active(self):
        if self.data['state'] in ('finished','stopped') or 'collection_stop_monotonic' in self.data:
            raise ValueError('Experiment stopped; no restart')

    def deadline(self, stage):
        p=self.data[stage] if stage in ('preflight','reporting') else self.data['phases'][stage]
        debit=self.data['preflight_seconds'] if stage=='preflight' else 0.
        reserve=80 if stage in ('original','instrumented') else 20
        return min(p['start']+p['maximum_seconds']-debit,
                   self.data['started_monotonic']+600-self.data['preflight_seconds']-reserve)

    def preflight_done(self, ok, reason=None):
        p=self.data['preflight']
        if p['state']!='running':return
        now=self.clock();elapsed=now-p['start']+self.data['preflight_seconds']
        ok=ok and elapsed<100
        if not ok:reason=reason or ('Preflight deadline exhausted' if elapsed>=100 else 'Preflight did not pass')
        p.update(state='finished' if ok else 'stopped',stop=now,seconds=elapsed,reason=reason)
        if not ok:self.stop_work(reason or 'Preflight deadline exhausted')
        else:self.write()

    def begin(self, name):
        self.active()
        if self.data['preflight']['state']!='finished':raise ValueError('Preflight has not passed')
        p=self.data['phases'][name]
        if p['state']!='reserved' or any(q['state']=='running' for q in self.data['phases'].values()):raise ValueError('Consumed/overlapping phase')
        if self.overhead()>=100 or self.total()+66+80>600:raise ValueError('Experiment budget exhausted')
        if name=='instrumented' and self.data['phases']['original']['state']!='finished':raise ValueError('Original phase has not passed')
        p.update(state='running',start=self.clock());self.data['state']='running';self.write()

    def request(self,name,index):
        self.active()
        p=self.data['phases'][name]
        if p['state']!='running' or index!=p['requested'] or index>=24:raise ValueError('Invalid/repeated game reservation')
        if self.clock()+66>self.deadline(name):raise ValueError('Conservative game reservation guard')
        p['requested']+=1;p['requested_indices'].append(index);self.write()

    def finish(self,name,ok,reason=None):
        p=self.data['phases'][name]
        if p['state']!='running':return
        now=self.clock()
        p.update(state='finished' if ok else 'stopped',stop=now,seconds=now-p['start'],reason=reason)
        if now>self.deadline(name):p.update(state='stopped',reason='Phase wall budget exceeded')
        self.write()

    def stop_work(self, reason=None):
        if 'collection_stop_monotonic' in self.data:return
        now=self.clock()
        self.data.update(collection_stop_monotonic=now,collection_stop_reason=reason)
        self.write()

    def begin_reporting(self):
        p=self.data['reporting']
        if p['state']!='reserved' or self.data['state'] in ('finished','stopped'):
            raise ValueError('Reporting allocation already consumed')
        self.stop_work()
        p.update(state='running',start=self.clock());self.write()

    def finish_reporting(self, ok, reason=None):
        p=self.data['reporting']
        if p['state']!='running':return
        now=self.clock()
        p.update(state='finished' if ok and now<=self.deadline('reporting') else 'stopped',
                 stop=now,seconds=now-p['start'],reason=reason)
        self.write()

    def close(self,reason=None):
        if self.data['state'] in ('finished','stopped'):return
        self.stop_work(reason)
        if self.data['preflight']['state']=='running':self.preflight_done(False,reason or 'Interrupted preflight')
        for name in self.data['phases']:self.finish(name,False,reason or 'Interrupted phase')
        if self.data['reporting']['state']=='running':self.finish_reporting(False,reason or 'Interrupted report')
        if (self.data['preflight']['state']!='finished' or self.data['reporting']['state']!='finished'
            or any(p['state']!='finished' for p in self.data['phases'].values())):
            reason=reason or 'Required stage incomplete'
        now=self.clock()
        total=now-self.data['started_monotonic']+self.data['preflight_seconds']
        overhead=total-sum(p.get('seconds',0.) for p in self.data['phases'].values())
        self.data.update(state='stopped' if reason else 'finished',reason=reason,
            total_seconds=total,overhead_seconds=overhead,stop_monotonic=now,
            post_collection_seconds=now-self.data['collection_stop_monotonic'],
            final_accounting_seconds=now-self.data.get('final_accounting_start',now))
        if total>600 or overhead>180:self.data.update(state='stopped',reason='Aggregate/overhead budget exceeded')
        self.write()


def check_freeze(root, io):
    frozen=json.loads(io.read_text(root/'freeze.json'))
    for name,value in frozen['source'].items():
        if io.hash(ROOT/name)!=value:raise ValueError('Frozen source changed: '+name)
    for name,key in (('specification.json','specification_sha256'),('required-inputs.json','required_inputs_sha256')):
        if io.hash(root/name)!=frozen[key]:raise ValueError('Frozen input manifest changed: '+name)
    io.check('load frozen checkpoint')
    if load_checkpoint(root/'inputs/initial.json').sha256!=frozen['checkpoint_sha256']:raise ValueError('Checkpoint changed')
    io.check('after checkpoint validation')
    return frozen


@contextmanager
def recorded_factories(directory, session, build):
    """Scoped to one awaited match in this single-purpose, concurrency-one process."""
    old_player,old_close=runner.LocalPlayer,runner.close_players
    def create(**kwargs):
        recorder=ClientRecorder(directory/f"{kwargs['state'].index:03d}-{kwargs['side']}.client.jsonl",session,build)
        return AcceptanceLocalPlayer(acceptance_recorder=recorder,**kwargs)
    runner.LocalPlayer,runner.close_players=create,close_acceptance_players
    try:yield
    finally:runner.LocalPlayer,runner.close_players=old_player,old_close


def replay_match(path,index,config,checkpoint):
    count=Counter()
    for side in ('a','b'):
        policy=make_policy(getattr(config,'agent_'+side),runner.policy_seed(config.seed,index,side),
                           checkpoint=checkpoint if side=='a' else None)
        for row in read_jsonl(path/f'privileged/attempts/{index:03d}-{side}.jsonl'):
            obs=snapshot_from_dict(row['observation'])
            if snapshot_hash(row['observation'])!=row['snapshot_sha256']:raise ValueError('Pre-decision snapshot hash changed')
            if side=='a':
                result=policy.act(obs)
                if json.loads(json.dumps(asdict(result)))!=row['policy_evaluation']:raise ValueError('Frozen policy probability/draw/value mismatch')
                selected=result.chosen_action
            else:selected=policy.choose(obs)
            if selected!=row['chosen_action'] or resolve_action(selected,obs,row['legal_mapping'])!=row['command']:
                raise ValueError('Frozen policy/command mismatch')
            count['decisions']+=1;count[side]+=1
    return dict(count)


def inspect_match(path,row,config,checkpoint,evidence_directory=None):
    index=row['match'];replay=replay_match(path,index,config,checkpoint)
    events=[e for e in read_jsonl(path/'events.jsonl') if e.get('match')==index]
    warnings=[e for e in events if e['kind']=='client_log']
    unexpected=[e for e in warnings if not known_gen1_warning(e)]
    result={'match':index,'replay':replay,'warning_records':len(warnings),
        'known_warnings':sum(known_gen1_warning(e) for e in warnings),'unexpected_warnings':unexpected}
    errors=[]
    if row['status'] not in ('completed','truncated'):errors.append('Blocking battle status: '+row['status'])
    if row['invalid_actions']:errors.append('Invalid action incident')
    if unexpected:errors.append('Unexpected client warning/error')
    if not row.get('engine_record'):errors.append('Missing official end log')
    if evidence_directory and row.get('engine_record'):
        acceptance_started=time.monotonic()
        session=json.loads((evidence_directory/'session.json').read_text())
        if len(row['battle_tags'])!=1:raise ValueError('Ambiguous battle identity')
        room=row['battle_tags'][0]
        clients=[evidence_directory/f'{index:03d}-{side}.client.jsonl' for side in ('a','b')]
        report=validate_acceptance(clients,evidence_directory/f'{room}.room.jsonl',evidence_directory/f'{room}.sim.jsonl',
            session=session['session'],build=session['build'],engine_record=path/row['engine_record']['path'],
            engine_sha256=row['engine_record']['sha256'])
        result['acceptance']=report
        save(path/f'privileged/{index:03d}-acceptance-report.json',report)
        if report['integrity']!='valid':errors.append('Acceptance integrity: '+report.get('reason','unknown'))
        else:
            if len(report['attempts'])!=replay['decisions']:errors.append('Decision/attempt cardinality mismatch')
            if row['status']=='completed' and any(a['status']!='committed' for a in report['attempts']):errors.append('Completed game has uncertified attempts')
            for side,client in zip(('a','b'),clients):
                captured=read_chain(client,session['session'],session['build'],'client')
                own=[e['decision'] for e in captured if e['kind']=='attempt']
                if own!=read_jsonl(path/f'privileged/attempts/{index:03d}-{side}.jsonl'):errors.append('Private/legacy own-journal mismatch')
        result['acceptance_validation_seconds']=time.monotonic()-acceptance_started
    result['blocking_errors']=errors
    return result


def isolation_audit(root):
    """Mutate disposable copies, never the collected evidence or policy source."""
    from battlemind.adaptation_experiment import artifacts
    from battlemind.opponent_memory import encounter_evidence, ObserverMemory
    from battlemind.schema import PublicEvent
    from battlemind.viewer_records import historical_replay
    phase=root/'instrumented'
    if not (phase/'battles.jsonl').exists():return {'status':'unavailable','reason':'no instrumented collection'}
    rows=[r for r in read_jsonl(phase/'battles.jsonl') if r['status']=='completed']
    if not rows:return {'status':'unavailable','reason':'no completed instrumented battle'}
    valid_indices={entry['match'] for entry in read_jsonl(phase/'match-audits.jsonl')
                   if entry.get('acceptance',{}).get('integrity')=='valid'}
    rows=[row for row in rows if row['match'] in valid_indices]
    if not rows:return {'status':'unavailable','reason':'no complete valid acceptance trace to mutate'}
    row=rows[0];index=row['match'];target=root/'privileged/isolation-copy';target.mkdir()
    (target/'privileged/attempts').mkdir(parents=True)
    for name in ('run.json',f'privileged/{index:03d}-histories.json',
                 f'privileged/attempts/{index:03d}-a.jsonl',f'privileged/attempts/{index:03d}-b.jsonl'):
        shutil.copyfile(phase/name,target/name)
    (target/'battles.jsonl').write_text(json.dumps(row)+'\n')
    (target/'privileged/acceptance').mkdir()
    room=row['battle_tags'][0];source_evidence=root/'privileged/acceptance'
    for name in ('session.json',f'{index:03d}-a.client.jsonl',f'{index:03d}-b.client.jsonl',f'{room}.room.jsonl',f'{room}.sim.jsonl'):
        shutil.copyfile(source_evidence/name,target/'privileged/acceptance'/name)
    end_copy=target/'privileged/private-end.json';shutil.copyfile(phase/row['engine_record']['path'],end_copy)
    checkpoint=load_checkpoint(root/'inputs/initial.json');model,_=artifacts()
    metadata=json.loads((phase/'run.json').read_text());config=runner.RunConfig(**{**metadata['config'],'teams':tuple(metadata['config']['teams'])})
    records=read_jsonl(target/f'privileged/attempts/{index:03d}-a.jsonl')
    observations=tuple(snapshot_from_dict(r['observation']) for r in records)
    history=tuple(PublicEvent(e['turn'],e['kind'],e['actor'],tuple(e['values'])) for e in json.loads((target/f'privileged/{index:03d}-histories.json').read_text())['a'])
    def public_outputs():
        evidence=encounter_evidence(observations,history,model,True)
        memory=ObserverMemory();memory.begin('isolation-key',0);summary=memory.finish('isolation-key',0,evidence)
        return {'policy_replay':replay_match(target,index,config,checkpoint),
            'predictor':[model.logistic.predict(o) for o in observations],
            'memory_evidence':evidence,'memory_summary':asdict(summary),
            'viewer':historical_replay(target,index,'live-check','live-check')}
    before=public_outputs()
    evidence=target/'privileged/acceptance';session=json.loads((evidence/'session.json').read_text())
    def private_validation():return validate_acceptance([evidence/f'{index:03d}-{side}.client.jsonl' for side in ('a','b')],
        evidence/f'{room}.room.jsonl',evidence/f'{room}.sim.jsonl',session=session['session'],build=session['build'],
        engine_record=end_copy,engine_sha256=row['engine_record']['sha256'])
    if private_validation()['integrity']!='valid':raise ValueError('Copied live acceptance trace did not validate')
    (evidence/f'{room}.sim.jsonl').write_text('corrupted opponent acceptance\n')
    end_copy.write_text('{"private_choices":"changed","winner":"changed"}')
    after=public_outputs()
    if before!=after or private_validation()['integrity']!='invalid_or_incomplete':raise ValueError('Private mutation isolation/audit failure')
    return {'status':'passed','match':index,'snapshot_count':len(observations),'memory_examples':before['memory_evidence']['admitted'],
        'outputs_sha256':snapshot_hash(before),'mutation_scope':'only disposable private acceptance/end copies; no online features read them'}


async def collect_phase(root,name):
    budget=Budget(root);budget.active()
    io=DeadlineIO(budget.deadline(name));frozen=check_freeze(root,io);spec=json.loads(io.read_text(root/'specification.json'))
    p=budget.data['phases'][name]
    if p['state']!='running' or p['requested']:raise ValueError('No resume/repeated phase execution')
    path=root/name;path.mkdir(exist_ok=False);(path/'privileged/attempts').mkdir(parents=True)
    instrumented=name=='instrumented';engine=DERIVED if instrumented else ROOT/'.local/pokemon-showdown'
    private=Path(os.environ['BATTLEMIND_ACCEPTANCE_DIR']) if instrumented else None
    if instrumented:
        verified=verify_build(engine,io=io)
        if verified['build_id']!=spec['instrumented_build_id'] or os.environ['BATTLEMIND_ACCEPTANCE_BUILD']!=verified['build_id']:
            raise ValueError('Instrumented build/environment mismatch')
    config=runner.RunConfig(agent_a='reinforce',agent_b='random',battles=24,seed=260911,concurrency=1,
        turn_cap=300,timeout=60,run_timeout=p['maximum_seconds'],teams=tuple(spec['teams']),
        checkpoint_a=str(root/'inputs/initial.json'),showdown=str(engine),port=8000)
    config.validate();shutil.copyfile(root/'inputs/initial.json',path/'reinforce-a.json');checkpoint=load_checkpoint(path/'reinforce-a.json')
    metadata={'schema_version':'2.0','config':asdict(config),'acceptance_phase':name,
        'reinforce_checkpoints':{'a':{'path':'reinforce-a.json','sha256':checkpoint.sha256,'evaluation_updates':False}},
        'policies':{side:{'name':agent,'version':make_policy(agent,260911,checkpoint=checkpoint if side=='a' else None).version}
                    for side,agent in (('a','reinforce'),('b','random'))},'code_sha256':frozen['source'],
        'randomness':{'simulator_seed':None,'exact_replay_determinism':False}}
    save(path/'run.json',metadata)
    decisions,battles,events,labels=[JsonlWriter(path/n) for n in ('decisions.jsonl','battles.jsonl','events.jsonl','privileged/labels.jsonl')]
    audit=JsonlWriter(path/'match-audits.jsonl');rows=[];failure=None
    cpu=time.process_time();peak_python=peak_server=0;server_cpu=0.;server_pid=None;owned=set();stop=False
    async def sample():
        nonlocal peak_python,peak_server,server_cpu
        while not stop:
            peak_python=max(peak_python,psutil.Process().memory_info().rss)
            if server_pid:
                try:
                    parent=psutil.Process(server_pid);group=[parent]+parent.children(recursive=True)
                    owned.update(process.pid for process in group)
                    peak_server=max(peak_server,sum(process.memory_info().rss for process in group))
                    server_cpu=max(server_cpu,sum(sum(process.cpu_times()[:2]) for process in group))
                except psutil.NoSuchProcess:pass
            await asyncio.sleep(.1)
    task=asyncio.create_task(sample())
    try:
        io.check('server startup after validated preflight')
        budget.active()
        async with LocalServer(engine,8000,path/'server.log') as server:
            server_pid=server.process.pid;owned.add(server_pid)
            for index in range(24):
                budget.request(name,index)
                deadline=budget.deadline(name)-6
                if instrumented:
                    session=json.loads((private/'session.json').read_text())
                    with recorded_factories(private,session['session'],session['build']):
                        row=await runner.play_match(config,index,decisions,events,deadline,path,path/'privileged/engine',labels,checkpoints={'a':checkpoint})
                else:
                    row=await runner.play_match(config,index,decisions,events,deadline,path,path/'privileged/engine',labels,checkpoints={'a':checkpoint})
                rows.append(row);battles.write(row)
                result=inspect_match(path,row,config,checkpoint,private);audit.write(result)
                print(f'{name} {index+1}/24: {row["status"]} winner={row["winner"]}; audit={result["blocking_errors"]}',flush=True)
                if result['blocking_errors']:raise ValueError('; '.join(result['blocking_errors']))
                if 'CRASH:' in (path/'server.log').read_text():raise ValueError('Server crash report')
    except BaseException as exc:
        failure=f'{type(exc).__name__}: {exc}'
        events.write({'kind':'verification_failure','message':failure})
    finally:
        stop=True;await task
        for writer in (decisions,battles,events,labels,audit):writer.close()
    listeners=[str(c.laddr) for c in psutil.net_connections(kind='tcp') if c.status=='LISTEN' and c.laddr.port==8000]
    remaining=[pid for pid in owned if psutil.pid_exists(pid)]
    if listeners or remaining:failure=f'Cleanup failed: listeners={listeners}, processes={remaining}'
    resources={'python_cpu_seconds':time.process_time()-cpu,'python_peak_sampled_rss_bytes':peak_python,
        'server_peak_sampled_rss_bytes':peak_server,'server_cpu_seconds_last_sample':server_cpu,
        'sample_seconds':.1,'owned_pids':sorted(owned),'remaining_owned_pids':remaining,'remaining_listeners':listeners}
    save(path/'resources.json',resources)
    summary=summarize(rows,budget.data['phases'][name]['requested'])
    summary.update(planned=24,reserved=24,never_requested=24-summary['requested'],resources=resources,
        failure=failure,labels=label_summary(read_jsonl(path/'privileged/labels.jsonl')),
        acceptance_audits=read_jsonl(path/'match-audits.jsonl'))
    try:summary['legacy_audit']=audit_labels(path)
    except Exception as exc:failure=failure or f'Legacy audit: {exc}';summary['failure']=failure
    save(path/'summary.json',summary)
    save(path/'phase-result.json',{'ok':failure is None and len(rows)==24,'failure':failure,
        'requested':summary['requested'],'completed':summary['completed']})
    return failure is None and len(rows)==24


def preflight(root, io):
    """Integrity plus zero-battle readiness, before any game phase may begin."""
    spec=json.loads(io.read_text(SPEC));validate_spec(spec)
    if io.hash(INPUTS)!=spec['input_manifest_sha256']:raise ValueError('Required input manifest differs from specification')
    io.copy(SPEC,root/'specification.json')
    checked=required_inputs(INPUTS,io)
    checked.update({name:io.hash(ROOT/name) for name in READINESS_INPUTS})
    (root/'inputs').mkdir()
    io.copy(ROOT/spec['checkpoint'],root/'inputs/initial.json')
    io.check('strict original c0 loader')
    checkpoint=load_checkpoint(root/'inputs/initial.json')
    if checkpoint.sha256!=spec['checkpoint_sha256']:raise ValueError('Required original initialization changed')
    from battlemind.adaptation_experiment import artifacts
    io.check('strict original V4 and V5 loaders');artifacts();io.check('after strict loaders')
    # inspect_server's existing diagnostics remain unchanged, under the worker watchdog.
    original=inspect_server(ROOT/'.local/pokemon-showdown',[ROOT/p for p in spec['teams']],8000)
    io.check('after original runtime/format/team validation')
    # One full derived validation here, including runtime, dependency bytes and patch.
    instrumented_env=recording_environment(DERIVED,root/'privileged/acceptance',io=io)
    build=json.loads(io.read_text(DERIVED/'acceptance-build.json'))
    if build['build_id']!=spec['instrumented_build_id']:raise ValueError('Wrong derived build')
    payload={'format':'gen1ou','teams':[{'path':str(ROOT/p),'text':io.read_text(ROOT/p)} for p in spec['teams']]}
    derived_rules=json.loads(io.command([executable('node'),str(ROOT/'scripts/inspect-server.cjs')],DERIVED,json.dumps(payload)))
    if derived_rules!=original['validation']:raise ValueError('Original/derived format/team/rule validation differs')
    operational_preflight(DERIVED,instrumented_env,root/'readiness',io)
    io.copy(DERIVED/'acceptance-build.json',root/'inputs/acceptance-build.json')
    manifest=json.loads(io.read_text(INPUTS))
    source={n:checked[n] for n in [*manifest['project_files'],*READINESS_INPUTS]}
    for name in source:
        io.copy(ROOT/name,root/'source-snapshot'/name)
        if io.hash(root/'source-snapshot'/name)!=source[name]:raise ValueError('Source changed during freeze: '+name)
    save(root/'required-inputs.json',checked)
    save(root/'preflight.json',{'original':original,'derived_rule_validation_equal':True,
        'instrumented_build_id':build['build_id'],'required_inventory_files':len(checked),
        'strict_loaders':['original reinforce c0','original V4 predictor','selected V5 checkpoint'],
        'full_historical_archive_scan':False,
        'derived_checks':'full verify_build plus dependency resolution and zero-battle handshake; no cached verdict'})
    save(root/'privileged/worker-environment.json',{k:v for k,v in instrumented_env.items() if k.startswith('BATTLEMIND_ACCEPTANCE_')})
    save(root/'freeze.json',{'schema':'bm-acceptance-live-freeze-2','source':source,
        'specification_sha256':io.hash(root/'specification.json'),'checkpoint_sha256':checkpoint.sha256,
        'required_inputs_sha256':io.hash(root/'required-inputs.json'),
        'derived_build_manifest_sha256':io.hash(root/'inputs/acceptance-build.json'),
        'teams':original['teams'],'full_historical_archive_scan':False})
    io.check('seal preflight')


def verification_report(root, io):
    check_freeze(root,io)
    save(root/'isolation-audit.json',isolation_audit(root));io.check('after isolation audit')
    checked=required_inputs(INPUTS,io)
    checked.update({name:io.hash(ROOT/name) for name in READINESS_INPUTS})
    if checked!=json.loads(io.read_text(root/'required-inputs.json')):raise ValueError('Required input preservation mismatch')
    verify_build(DERIVED,io=io)
    save(root/'preservation.json',{'files':checked,'full_historical_archive_scan':False,'changed':[]})
    summaries={name:json.loads(io.read_text(root/name/'summary.json')) for name in ('original','instrumented')}
    coverage=Counter()
    for summary in summaries.values():
        for entry in summary.get('acceptance_audits',[]):
            io.check('acceptance report')
            for attempt in entry.get('acceptance',{}).get('attempts',[]):
                if attempt['status']=='committed':
                    coverage['committed_attempts']+=1
                    if attempt['normalization']:
                        coverage['normalization:'+str(attempt['normalization'])+':'+str(attempt['accepted_choice'])]+=1
    save(root/'verification-report.json',{'schema':'bm-acceptance-live-report-2','phases':summaries,
        'coverage':dict(coverage),'policy_changes':False,'training_or_eligibility_updates':False,
        'unmatched_engine_randomness':True,'full_historical_archive_scan':False})
    # Only this new output, not the historical archive. Partial progress is retained.
    hashes={}
    for path in io.files(root):
        if path.name in ('ledger.json','artifact-hashes.json') or path.name.endswith('-io.jsonl'):continue
        hashes[path.relative_to(root).as_posix()]=io.hash(path)
    save(root/'artifact-hashes.json',hashes);io.check('finish reporting')


def worker(root, name, until):
    budget=Budget(root)
    if budget.data['schema']!='bm-acceptance-live-ledger-2':raise ValueError('Historical ledger cannot be resumed')
    p=budget.data[name]
    if p['state']!='running' or until!=budget.deadline(name):raise ValueError('Missing current worker reservation')
    with (root/f'{name}-io.jsonl').open('x',encoding='utf-8') as stream:
        def progress(row):
            stream.write(json.dumps(row)+'\n');stream.flush()
        io=DeadlineIO(until,progress=progress)
        (preflight if name=='preflight' else reporting)(root,io)


def reporting(root, io):
    """Mandatory report on success OR failure, inside the reserved worker.

    Full acceptance auditing gets at most 50 of 60 seconds. Ten seconds remain
    for counts and a concise Markdown closure; optional forensics are not run.
    A parent watchdog covers blocked reads as well as this cooperative deadline.
    """
    budget=Budget(root); audit_error=None
    if budget.data['preflight']['state']=='finished' and all(p['state']=='finished' for p in budget.data['phases'].values()):
        try:verification_report(root,DeadlineIO(io.until-10,clock=io.clock,progress=io.progress))
        except Exception as exc:audit_error=f'{type(exc).__name__}: {exc}'
    phases={}
    for name,p in budget.data['phases'].items():
        io.check('mandatory phase accounting')
        counts={k:p[k] for k in ('planned','reserved','requested')}
        counts['never_requested']=p['planned']-p['requested']
        path=root/name/'battles.jsonl'
        rows=[json.loads(line) for line in io.read_text(path).splitlines() if line] if path.exists() else []
        if len(rows)>p['requested']:raise ValueError('More records than actual requests')
        counts.update(summarize(rows,p['requested']));phases[name]=counts
    failure=budget.data.get('collection_stop_reason') or audit_error
    if not failure and any(p['state']!='finished' for p in budget.data['phases'].values()):failure='Required stage incomplete'
    report={'schema':'bm-acceptance-live-closure-3','failure':failure,'phases':phases,
        'full_report_available':(root/'verification-report.json').exists() and not audit_error,
        'audit_error':audit_error,'full_historical_archive_scan':False,'new_training_updates':0,
        'optional_forensics_performed':False}
    save(root/'report.json',report)
    lines=['# Acceptance run closure','',f'Failure: {failure or "none"}.','',
        '| Phase | Planned | Reserved | Requested | Completed | Never requested |',
        '|---|---:|---:|---:|---:|---:|']
    for name,p in phases.items():
        lines.append(f'| {name} | {p["planned"]} | {p["reserved"]} | {p["requested"]} | {p["completed"]} | {p["never_requested"]} |')
    lines+=['','Final durations and cleanup status are in the sealed ledger/process records.',
        'Request-bound evidence is unavailable for unstarted phases. No equivalence is inferred.',
        'No supplemental forensic scan or narrative investigation is included.']
    io.check('write mandatory Markdown')
    with (root/'REPORT.md').open('x',encoding='utf-8') as stream:stream.write('\n'.join(lines)+'\n')
    io.check('mandatory reporting complete')
    if audit_error:raise ValueError(audit_error)


def run_worker(root, name, budget, env=None):
    args=[sys.executable,'-B',str(Path(__file__).resolve()),'--output',str(root)]
    if name in ('preflight','reporting'):args+=['--worker',name,'--until',str(budget.deadline(name))]
    else:args+=['--phase',name]
    with (root/f'{name}-console.txt').open('x') as log:
        return supervise(args,DeadlineIO(budget.deadline(name)),log,env=env,
                         record=lambda row:save(root/f'{name}-process.json',row))


def finalize(root, budget, failure):
    """Constant-size fallback only. Never read battle logs or inspect an archive.

    The reporting worker owns all log reads under its 60s deadline. A killed
    worker leaves outcomes unavailable, never invented. Closed ledgers are sealed.
    """
    budget.reload()
    if budget.data['state'] in ('finished','stopped'):return
    budget.data['final_accounting_start']=budget.clock();budget.write()
    budget.stop_work(failure)
    for name,p in budget.data['phases'].items():
        if p['state']=='running':budget.finish(name,False,failure or 'Interrupted')
    if not failure and (budget.data['preflight']['state']!='finished' or budget.data['reporting']['state']!='finished'
                        or any(p['state']!='finished' for p in budget.data['phases'].values())):
        failure='Required stage incomplete'
    phases={}
    for name,p in budget.data['phases'].items():
        phases[name]={k:p[k] for k in ('planned','reserved','requested')}
        phases[name]['never_requested']=p['planned']-p['requested']
        phases[name].update(summarize([],0) if p['requested']==0 else
            {'recorded':None,'completed':None,'unrecorded':None,'reason':'Reporting unavailable; consult retained rows offline'})
    if not (root/'report.json').exists():
        save(root/'report.json',{'schema':'bm-acceptance-live-closure-3','failure':failure,'phases':phases,
            'full_report_available':False,'full_historical_archive_scan':False,'new_training_updates':0,
            'optional_forensics_performed':False})
    budget.close(failure)
    print(json.dumps({'status':budget.data['state'],'failure':budget.data['reason'],'phases':phases,
                      'total_seconds':budget.total(),'overhead_seconds':budget.overhead()},indent=2),flush=True)


def main(root,preflight_seconds=0.):
    if root.resolve()!=OUTPUT.resolve():raise ValueError('Replacement has one fixed fresh output directory')
    if preflight_seconds:raise ValueError('Replacement has no historical check debit or resume')
    root.mkdir(parents=True,exist_ok=False)
    # Reserve the fixed ceiling before any dependency/configuration reads. The
    # supervised preflight validates the full specification before passing.
    budget=Budget.create(root,{'phases':{'original':{'seconds':180},'instrumented':{'seconds':240}}});failure=None
    try:
        run_worker(root,'preflight',budget)
        budget.preflight_done(True)
        for name in ('original','instrumented'):
            budget.begin(name)
            env=dict(os.environ)
            if name=='instrumented':env.update(json.loads((root/'privileged/worker-environment.json').read_text()))
            if name=='original':
                env={k:v for k,v in env.items() if not k.startswith('BATTLEMIND_ACCEPTANCE_')}
            run_worker(root,name,budget,env)
            budget.reload()
            result=json.loads((root/name/'phase-result.json').read_text())
            budget.finish(name,result['ok'],result.get('failure'))
            if not result['ok'] or budget.data['phases'][name]['state']!='finished':
                raise ValueError(result.get('failure') or 'Phase incomplete')
    except BaseException as exc:
        failure=f'{type(exc).__name__}: {exc}'
        budget.reload()
        budget.preflight_done(False,failure)
    finally:
        budget.stop_work(failure)
        for name in budget.data['phases']:budget.finish(name,False,failure or 'Interrupted')
        try:
            budget.begin_reporting()
            run_worker(root,'reporting',budget)
            budget.finish_reporting(True)
        except BaseException as exc:
            failure=failure or f'Mandatory reporting failed: {type(exc).__name__}: {exc}'
            budget.finish_reporting(False,str(exc))
        finalize(root,budget,failure)
    return budget.data['state']=='finished'


def read_report(root):
    """Read saved values only; never finalize, rehash, resume or advance clocks."""
    return {'ledger':json.loads((root/'ledger.json').read_text()),
            'report':json.loads((root/'report.json').read_text()) if (root/'report.json').exists() else None}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=OUTPUT)
    parser.add_argument('--phase',choices=['original','instrumented'])
    parser.add_argument('--worker',choices=['preflight','reporting'])
    parser.add_argument('--until',type=float)
    parser.add_argument('--report',action='store_true',help='Read saved accounting without updating files or clocks')
    args=parser.parse_args()
    if args.report:
        if args.worker or args.phase:parser.error('--report cannot collect or run a worker')
        print(json.dumps(read_report(args.output),indent=2));ok=True
    elif args.worker:
        if args.until is None:parser.error('--until required for a reserved worker')
        worker(args.output,args.worker,args.until);ok=True
    elif args.phase:ok=asyncio.run(collect_phase(args.output,args.phase))
    else:ok=main(args.output)
    raise SystemExit(0 if ok else 1)
