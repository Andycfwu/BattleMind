"""One authorized instrumented-only verification; no learning or eligibility updates."""
import time
ENTRY_MONOTONIC=time.monotonic()  # Include imports in the parent's allocation.
import argparse
import asyncio
import ast
from collections import Counter
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys

if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from battlemind.environment import ROOT, executable, inspect_server
from battlemind.acceptance_build import recording_environment, verify_build
from battlemind.acceptance import read_chain
from battlemind.adaptation_experiment import artifacts
from battlemind.reinforce import load_checkpoint
from battlemind.labels import audit_labels, label_summary, read_jsonl
from battlemind.reporting import summarize
from diagnostics import acceptance_live_verify as live
from diagnostics.acceptance_preflight import DeadlineIO, required_inputs, supervise
from diagnostics.acceptance_readiness import operational_preflight, listeners

SPEC=ROOT/'configs/acceptance-instrumented-only.json'
INPUTS=ROOT/'configs/acceptance-instrumented-only-inputs.json'
OUTPUT=ROOT/'runs/acceptance-instrumented-only-1'
DERIVED=ROOT/'.local/pokemon-showdown-acceptance-v2-r5'
REFERENCE=ROOT/'runs/acceptance-live-verification-replacement-1/original'
ALLOCATIONS={'preflight':100,'instrumented':240,'reporting':60}
save=live.save


def validate_spec(spec):
    expected={'maximum_games':24,'maximum_wall_seconds':420,'concurrency':1,'host':'127.0.0.1',
        'format':'gen1ou','turn_cap':300,'game_timeout_seconds':60,'policy_seed':260911,
        'policies':['reinforce-original-c0','random'],'training_updates':False,'eligibility_changes':False,
        'resume':False,'retries':False,'borrow_allocations':False,'phase_seconds':ALLOCATIONS,'cleanup_seconds':20,
        'output':OUTPUT.relative_to(ROOT).as_posix(),'derived':DERIVED.relative_to(ROOT).as_posix(),
        'reference':REFERENCE.relative_to(ROOT).as_posix()}
    if any(spec.get(k)!=v for k,v in expected.items()):raise ValueError('Unauthorized schedule/budget/settings')
    previous=json.loads((ROOT/'configs/acceptance-live-replacement.json').read_text())
    for key in ('teams','checkpoint','checkpoint_sha256','policies','policy_seed','format','turn_cap',
                'game_timeout_seconds','stop_rules','ordinary_cap','minimum_live_coverage'):
        if spec[key]!=previous[key]:raise ValueError('Verification science changed: '+key)


class Budget:
    """Single-use 24-game ledger. Reserved capacity is never an actual request."""
    def __init__(self,root,clock=time.monotonic):
        self.path=root/'ledger.json';self.clock=clock;self.reload()
        if self.data['schema']!='bm-acceptance-instrumented-ledger-1':raise ValueError('Incompatible ledger')

    @classmethod
    def create(cls,root,started=None,clock=time.monotonic):
        started=clock() if started is None else started
        save(root/'ledger.json',{'schema':'bm-acceptance-instrumented-ledger-1','state':'running',
            'started_monotonic':started,'maximum_seconds':420,'maximum_games':24,'cleanup_reserve_seconds':20,
            'preflight':{'state':'running','start':started,'maximum_seconds':100},
            'reporting':{'state':'reserved','maximum_seconds':60},
            'phases':{'instrumented':{'state':'reserved','planned':24,'reserved':24,'requested':0,
                'requested_indices':[],'maximum_seconds':240}},'all_allocations_reserved':True})
        return cls(root,clock)

    def reload(self):self.data=json.loads(self.path.read_text())
    def write(self):
        path=self.path.with_suffix('.pending');path.write_text(json.dumps(self.data,indent=2));path.replace(self.path)
    def stage(self,name):return self.data['phases'][name] if name=='instrumented' else self.data[name]
    def active(self):
        if self.data['state']!='running' or 'collection_stop' in self.data:raise ValueError('Consumed/stopped experiment')
    def deadline(self,name):
        phase=self.stage(name);reserved=80 if name in ('preflight','instrumented') else 20
        return min(phase['start']+phase['maximum_seconds'],self.data['started_monotonic']+420-reserved)
    def begin(self,name):
        if self.data['state']!='running' or self.stage(name)['state']!='reserved':raise ValueError('Consumed stage')
        if name=='instrumented':
            self.active()
            if self.data['preflight']['state']!='finished':raise ValueError('Preflight has not passed')
        self.stage(name).update(state='running',start=self.clock());self.write()
    def request(self,name,index):
        self.active();p=self.stage(name)
        if name!='instrumented' or p['state']!='running' or index!=p['requested'] or index>=24:
            raise ValueError('Invalid/repeated request')
        if self.data['preflight']['state']!='finished':raise ValueError('Preflight has not passed')
        if self.clock()+66>self.deadline(name):raise ValueError('Conservative reservation guard')
        p['requested']+=1;p['requested_indices'].append(index);self.write()
    def finish(self,name,ok,reason=None):
        p=self.stage(name)
        if p['state']!='running':return
        now=self.clock();overrun=max(0,now-self.deadline(name))
        p.update(state='finished' if ok and not overrun else 'stopped',stop=now,seconds=now-p['start'],
                 overrun_seconds=overrun,reason=reason or ('Stage deadline exceeded' if overrun else None));self.write()
    def stop_collection(self,reason=None):
        if 'collection_stop' not in self.data:
            self.data.update(collection_stop=self.clock(),collection_failure=reason);self.write()
    def close(self,reason=None):
        if self.data['state']!='running':return
        self.stop_collection(reason)
        for name in ALLOCATIONS:self.finish(name,False,reason or 'Interrupted')
        if any(self.stage(n)['state']!='finished' for n in ALLOCATIONS):reason=reason or 'Required stage incomplete'
        now=self.clock();elapsed=now-self.data['started_monotonic']
        if elapsed>420:reason=reason or 'Aggregate deadline exceeded'
        self.data.update(state='stopped' if reason else 'finished',reason=reason,stop_monotonic=now,
            total_seconds=elapsed,overrun_seconds=max(0,elapsed-420),
            overhead_seconds=elapsed-self.stage('instrumented').get('seconds',0),
            post_collection_seconds=now-self.data['collection_stop']);self.write()


def freeze_check(root,io):
    frozen=live.check_freeze(root,io)
    if io.hash(DERIVED/'acceptance-build.json')!=frozen['derived_build_manifest_sha256']:raise ValueError('Build manifest changed')
    return frozen


def reference_check(io):
    """Read-only original 24-game compatibility/replay, never a new control run."""
    metadata=json.loads(io.read_text(REFERENCE/'run.json'));config=metadata['config']
    spec=json.loads(io.read_text(SPEC))
    expected={'agent_a':'reinforce','agent_b':'random','battles':24,'seed':260911,'concurrency':1,
        'format':'gen1ou','port':8000,'turn_cap':300,'timeout':60,'teams':spec['teams']}
    if any(config.get(k)!=v for k,v in expected.items()):raise ValueError('Original reference configuration differs')
    science={n:h for n,h in metadata['code_sha256'].items() if n.startswith('src/battlemind/') and n!='src/battlemind/acceptance_build.py'}
    for name,digest in science.items():
        if io.hash(ROOT/name)!=digest:raise ValueError('Original policy/adapter/scientific source differs: '+name)
    checkpoint=load_checkpoint(REFERENCE/'reinforce-a.json')
    if checkpoint.sha256!=spec['checkpoint_sha256']:raise ValueError('Original policy checkpoint differs')
    cfg=live.runner.RunConfig(**{**config,'teams':tuple(config['teams'])})
    rows=read_jsonl(REFERENCE/'battles.jsonl')
    if len(rows)!=24 or [r['match'] for r in rows]!=list(range(24)) or any(r['status']!='completed' for r in rows):
        raise ValueError('Original reference schedule incomplete')
    decisions=0
    for row in rows:
        io.check('reference replay');decisions+=live.replay_match(REFERENCE,row['match'],cfg,checkpoint)['decisions']
    legacy=audit_labels(REFERENCE);io.check('reference label audit')
    hashes={p.relative_to(ROOT).as_posix():io.hash(p) for p in io.files(REFERENCE)}
    return {'compatible':True,'games':24,'replayed_decisions':decisions,'legacy_audit':legacy,
        'run_sha256':io.hash(REFERENCE/'run.json'),'files':hashes,'science_files':science,
        'differences':'Original phase ceiling 180s vs instrumented 240s; instrumentation and dependency packaging; unmatched simulator randomness'}


def preflight(root,io):
    spec=json.loads(io.read_text(SPEC));validate_spec(spec)
    if io.hash(INPUTS)!=spec['input_manifest_sha256']:raise ValueError('Input manifest changed')
    io.copy(SPEC,root/'specification.json');checked=required_inputs(INPUTS,io)
    (root/'inputs').mkdir();io.copy(ROOT/spec['checkpoint'],root/'inputs/initial.json')
    checkpoint=load_checkpoint(root/'inputs/initial.json');artifacts();io.check('strict model loaders')
    if checkpoint.sha256!=spec['checkpoint_sha256']:raise ValueError('Wrong initialization')
    original=inspect_server(ROOT/'.local/pokemon-showdown',[ROOT/p for p in spec['teams']],8000)
    reference=reference_check(io);save(root/'reference.json',reference)
    env=recording_environment(DERIVED,root/'privileged/acceptance',io=io)
    build=json.loads(io.read_text(DERIVED/'acceptance-build.json'))
    if build['build_id']!=spec['instrumented_build_id']:raise ValueError('Wrong derived build')
    payload={'format':'gen1ou','teams':[{'path':str(ROOT/p),'text':io.read_text(ROOT/p)} for p in spec['teams']]}
    validation=json.loads(io.command([executable('node'),str(ROOT/'scripts/inspect-server.cjs')],DERIVED,json.dumps(payload)))
    if validation!=original['validation']:raise ValueError('Original/derived official diagnostics differ')
    operational_preflight(DERIVED,env,root/'readiness',io)
    io.copy(DERIVED/'acceptance-build.json',root/'inputs/acceptance-build.json')
    manifest=json.loads(io.read_text(INPUTS));source={n:checked[n] for n in manifest['project_files']}
    for name,digest in source.items():
        io.copy(ROOT/name,root/'source-snapshot'/name)
        if io.hash(root/'source-snapshot'/name)!=digest:raise ValueError('Source changed during freeze')
    save(root/'required-inputs.json',checked)
    save(root/'privileged/worker-environment.json',{k:v for k,v in env.items() if k.startswith('BATTLEMIND_ACCEPTANCE_')})
    save(root/'freeze.json',{'schema':'bm-acceptance-instrumented-freeze-1','source':source,
        'specification_sha256':io.hash(root/'specification.json'),'checkpoint_sha256':checkpoint.sha256,
        'required_inputs_sha256':io.hash(root/'required-inputs.json'),
        'derived_build_manifest_sha256':io.hash(root/'inputs/acceptance-build.json'),
        'reference_sha256':io.hash(root/'reference.json'),'teams':original['teams']})
    io.check('preflight complete')


def coverage(audits,root,io):
    counts=Counter();branches=Counter();examples={};statuses=Counter();all_decisions=0
    session=json.loads(io.read_text(root/'privileged/acceptance/session.json'))
    for audit in audits:
        io.check('coverage audit')
        all_decisions+=audit['replay']['decisions']
        report=audit.get('acceptance',{})
        if report.get('integrity')!='valid':counts['invalid_or_incomplete_games']+=1;continue
        counts['valid_games']+=1;own={}
        for side in ('a','b'):
            chain=read_chain(root/f'privileged/acceptance/{audit["match"]:03d}-{side}.client.jsonl',session['session'],session['build'],'client')
            own.update({e['attempt']:e['decision'] for e in chain if e['kind']=='attempt'})
        for a in report['attempts']:
            statuses[a['status']]+=1
            if a['status']!='committed':continue
            decision=own[a['attempt']];reason=a['normalization'];choice=a['accepted_choice']
            category=None
            if reason:
                branches[reason+':'+choice]+=1
                if reason=='locked_move' and choice in ('move wrap','move clamp','move recharge'):
                    category={'move wrap':'wrap_continuation','move clamp':'clamp_continuation','move recharge':'recharge'}[choice]
                elif reason=='gen1_fight':category='gen1_fight'
                elif reason=='no_enabled_moves':category='struggle'
            elif a['sampled_id'].startswith('switch:'):
                category='forced_replacement' if decision['observation']['request_kind']=='forced_switch' else 'voluntary_switch'
            elif a['sampled_id'].startswith('move:'):category='ordinary_move'
            else:category='engine_action:'+a['sampled_id'].split(':')[1]
            if category:
                counts[category]+=1
                examples.setdefault(category,{'match':audit['match'],**a})
            semantic='move '+a['sampled_id'].split(':')[1]
            if reason and semantic!=choice:counts['normalized_choice_differs_from_sampled_id']+=1
    return {'counts':dict(counts),'statuses':dict(statuses),'normalization_branches':dict(branches),
        'examples':examples,'replayed_decisions':all_decisions,
        'unobserved':[name for name in [*json.loads(io.read_text(SPEC))['minimum_live_coverage'],'recharge','struggle'] if not counts[name]],
        'execution':'Acceptance and commitment do not establish execution or effect'}


def audit_run(root,io):
    frozen=freeze_check(root,io)
    checked=required_inputs(INPUTS,io)
    if checked!=json.loads(io.read_text(root/'required-inputs.json')):raise ValueError('Inputs changed')
    verify_build(DERIVED,io=io)
    reference=json.loads(io.read_text(root/'reference.json'))
    if io.hash(root/'reference.json')!=frozen['reference_sha256']:raise ValueError('Reference freeze changed')
    for name,digest in reference['files'].items():
        if io.hash(ROOT/name)!=digest:raise ValueError('Retained control changed')
    if set(reference['files'])!={p.relative_to(ROOT).as_posix() for p in io.files(REFERENCE)}:raise ValueError('Retained control membership changed')
    phase=root/'instrumented';rows=read_jsonl(phase/'battles.jsonl');audits=read_jsonl(phase/'match-audits.jsonl')
    if [r['match'] for r in rows]!=list(range(len(rows))):raise ValueError('Schedule indices differ')
    for row in rows:
        teams,challenger=live.runner.scheduled_match(row['match'],4)
        if row['team_indices']!=teams or row['challenger']!=challenger:raise ValueError('Team/side schedule differs')
    ledger=Budget(root).data;requested=ledger['phases']['instrumented']['requested']
    if len(rows)>requested:raise ValueError('More rows than requests')
    legacy=audit_labels(phase);io.check('legacy label audit')
    linked=coverage(audits,root,io)
    isolation=live.isolation_audit(root);io.check('private isolation replay')
    remaining=listeners(8000)
    if remaining:raise ValueError('Listener remained after collection')
    resources=json.loads(io.read_text(phase/'resources.json'))
    if resources['remaining_owned_pids'] or resources['remaining_listeners']:raise ValueError('Incomplete cleanup')
    matches_by_id={a['match']:a for a in audits}
    functional=(requested==len(rows)==24 and all(r['status']=='completed' for r in rows)
        and len(matches_by_id)==24 and all(not a['blocking_errors'] for a in audits)
        and linked['counts'].get('valid_games')==24 and linked['statuses'].get('committed',0)==linked['replayed_decisions']
        and isolation['status']=='passed')
    result={'functional_recording_passed':functional,'coverage':linked,'legacy_audit':legacy,'isolation':isolation,
        'reference_compatible':reference['compatible'],'inputs_preserved':True,'schedule_checked':len(rows),
        'acceptance_audit_seconds':sum(a.get('acceptance_validation_seconds',0) for a in audits),
        'known_warnings':sum(a['known_warnings'] for a in audits),'unexpected_warnings':sum(len(a['unexpected_warnings']) for a in audits),
        'legacy_labels':label_summary(read_jsonl(phase/'privileged/labels.jsonl')),'resources':resources,
        'match_failures':{str(a['match']):a['blocking_errors'] for a in audits if a['blocking_errors']},
        'unmatched_randomness':True,'eligibility_changes':False,'full_historical_scan':False}
    save(root/'verification.json',result)
    hashes={};sizes={}
    for p in io.files(root):
        if p.name in ('ledger.json','artifact-hashes.json') or p.name.endswith('-io.jsonl') or p.name.endswith('-console.txt'):continue
        name=p.relative_to(root).as_posix();hashes[name]=io.hash(p);sizes[name]=p.stat().st_size
    save(root/'artifact-hashes.json',hashes)
    save(root/'artifact-sizes.json',{'files':sizes,'total_bytes':sum(sizes.values()),
        'private_acceptance_bytes':sum(size for name,size in sizes.items() if name.startswith('privileged/acceptance/')),
        'scope':'Files hashed in this run; excludes active ledger/I/O/console logs and later closure files'})
    io.check('finish audit/hash')
    return result


def reporting(root,io):
    budget=Budget(root);error=None;verification=None
    if (root/'instrumented/battles.jsonl').exists():
        try:verification=audit_run(root,DeadlineIO(io.until-10,clock=io.clock,progress=io.progress))
        except Exception as exc:error=f'{type(exc).__name__}: {exc}'
    io.check('mandatory accounting')
    p=budget.stage('instrumented');path=root/'instrumented/battles.jsonl'
    rows=[json.loads(line) for line in io.read_text(path).splitlines() if line] if path.exists() else []
    counts=summarize(rows,p['requested']);counts.update(planned=24,reserved=24,never_requested=24-p['requested'])
    failure=budget.data.get('collection_failure') or error
    functional=bool(verification and verification['functional_recording_passed'] and not failure)
    result={'schema':'bm-acceptance-instrumented-report-1','counts':counts,'failure':failure,'audit_error':error,
        'functional_recording_passed':functional,'verification':verification,'training_updates':0,'eligibility_changes':False,
        'target_coverage_complete':functional and not set(json.loads(io.read_text(SPEC))['minimum_live_coverage']).intersection(verification['coverage']['unobserved']),
        'all_listed_cases_observed':functional and not verification['coverage']['unobserved'],
        'optional_forensics':False,'reference_games_newly_requested':0}
    detail=root/'instrumented/phase-result.json'
    result['collection_detail']=json.loads(io.read_text(detail)) if detail.exists() else None
    sizes=root/'artifact-sizes.json'
    result['artifact_sizes']=json.loads(io.read_text(sizes)) if sizes.exists() else None
    save(root/'report.json',result)
    text=['# Instrumented-only verification','',f'Functional recording passed: {functional}. Failure: {failure}.',
        f'Requested {counts["requested"]}; completed {counts["completed"]}; never requested {counts["never_requested"]}.',
        f'c0 wins/losses/draws: {counts["a_wins"]}/{counts["b_wins"]}/{counts["draws"]}.',
        '','No training or eligibility changes. Retained original games were not rerun.',
        'Final timings are in the sealed ledger; normalized acceptance is not execution or engine equivalence.']
    if verification:
        text+=['','Coverage: '+json.dumps(verification['coverage'],sort_keys=True),
            '',f'Policy isolation: {verification["isolation"]["status"]}. Known/unexpected warnings: {verification["known_warnings"]}/{verification["unexpected_warnings"]}.']
    io.check('mandatory Markdown');(root/'REPORT.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    io.check('report complete')
    if error:raise ValueError(error)


def worker(root,name,until):
    budget=Budget(root)
    if budget.data['state']!='running' or budget.stage(name)['state']!='running' or until!=budget.deadline(name):
        raise ValueError('Missing/consumed worker reservation')
    if name=='instrumented':
        # Process-local orchestration parameters only. Reuse the unchanged
        # collector, request hooks, policies, audit and cleanup implementations.
        live.Budget=Budget;live.DERIVED=DERIVED
        if not asyncio.run(live.collect_phase(root,name)):raise ValueError('Collection did not complete cleanly')
        return
    with (root/f'{name}-io.jsonl').open('x',encoding='utf-8') as stream:
        def progress(row):stream.write(json.dumps(row)+'\n');stream.flush()
        (preflight if name=='preflight' else reporting)(root,DeadlineIO(until,progress=progress))


def run_worker(root,name,budget):
    env=dict(os.environ)
    if name=='instrumented':env.update(json.loads((root/'privileged/worker-environment.json').read_text()))
    with (root/f'{name}-console.txt').open('x',encoding='utf-8') as log:
        supervise([sys.executable,'-B',str(Path(__file__).resolve()),'--worker',name,'--output',str(root),
            '--until',str(budget.deadline(name))],DeadlineIO(budget.deadline(name)),log,env=env,
            record=lambda row:save(root/f'{name}-process.json',row))


def main(root,started=None):
    if root.resolve()!=OUTPUT.resolve():raise ValueError('One fixed fresh output only')
    root.mkdir(parents=True,exist_ok=False);budget=Budget.create(root,started=started);failure=None
    try:
        run_worker(root,'preflight',budget);budget.finish('preflight',True)
        if budget.stage('preflight')['state']!='finished':raise ValueError('Preflight deadline')
        budget.begin('instrumented');run_worker(root,'instrumented',budget)
        budget.reload();budget.finish('instrumented',True)
        if budget.stage('instrumented')['state']!='finished':raise ValueError('Collection deadline')
    except BaseException as exc:
        failure=f'{type(exc).__name__}: {exc}';budget.reload()
        budget.finish('preflight',False,failure);budget.finish('instrumented',False,failure)
    finally:
        budget.stop_collection(failure)
        try:
            budget.begin('reporting');run_worker(root,'reporting',budget);budget.finish('reporting',True)
        except BaseException as exc:
            failure=failure or f'Reporting: {type(exc).__name__}: {exc}';budget.finish('reporting',False,str(exc))
        # Constant-size closure only. No supplemental reads/scans after reporting.
        budget.close(failure)
        if not (root/'report.json').exists():
            p=budget.stage('instrumented')
            save(root/'report.json',{'failure':budget.data['reason'],'functional_recording_passed':False,
                'requested':p['requested'],'never_requested':24-p['requested'],
                'completed':0 if p['requested']==0 else None,'reason':'Reporting unavailable'})
    print(json.dumps(budget.data,indent=2));return budget.data['state']=='finished'


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=OUTPUT)
    parser.add_argument('--worker',choices=list(ALLOCATIONS));parser.add_argument('--until',type=float)
    parser.add_argument('--report',action='store_true');args=parser.parse_args()
    if args.report:
        if args.worker:parser.error('Read-only reporting cannot run workers')
        print(json.dumps({'ledger':json.loads((args.output/'ledger.json').read_text()),
            'report':json.loads((args.output/'report.json').read_text())},indent=2))
    elif args.worker:
        if args.until is None:parser.error('Missing deadline')
        worker(args.output,args.worker,args.until)
    else:raise SystemExit(0 if main(args.output,ENTRY_MONOTONIC) else 1)
