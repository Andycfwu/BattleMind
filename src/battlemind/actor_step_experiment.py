"""Single-use, predeclared 1x/10x actor-step experiment; no resume or extra games."""
from collections import Counter
import json
from pathlib import Path
import shutil
import time

import psutil

from .actor_step import controlled_update
from .adaptation_experiment import artifacts
from .dataset import write_json
from .environment import ROOT, sha256, source_manifest, inspect_server
from .labels import read_jsonl
from .reinforce import Parameters, load_checkpoint, save_checkpoint
from .reinforce_experiment import Ledger, selection_score, verify_opponents
from .reinforce_training import audit_run, trajectories
from .runner import RunConfig, run

ARMS = ('control', 'treatment')
FINAL_ARMS = ('initial', *ARMS)
CONFIG = ROOT / 'configs/actor-step.json'
BLOCKING = ('crash', 'timeout', 'cancelled', 'not_started', 'unrecorded',
            'invalid_action_incidents', 'unexpected_client_warning_records', 'server_crash_reports')


def validate_spec(config: dict):
    # A single reviewed specification, not an exposed hyperparameter-search API.
    expected = json.loads(CONFIG.read_text())
    if config != expected or config['schema_version'] != 'actor-step-spec-1':
        raise ValueError('Only the frozen actor-step specification is supported')
    if config['games'] != {'training':864, 'selection':360, 'final':864} or config['seconds'] != {
        'training':1200, 'selection':600, 'final':1200, 'overhead':600}:
        raise ValueError('Audit allocations must remain exact')
    if config['maximum_games'] != 2088 or config['maximum_seconds'] != 3600:
        raise ValueError('Unauthorized ceiling')
    if (config['arms'] != {'control':1, 'treatment':10} or config['updates_per_arm'] != 6
        or config['candidates'] != [0,3,6] or config['archive_sequence'] != [0,0,0,2,0,4]
        or config['actor_lr'] != 30 or config['value_lr'] != .1 or config['concurrency'] != 1
        or (config['turn_cap'],config['timeout'],config['run_timeout']) != (300,60,300)):
        raise ValueError('Scientific settings changed')
    if config['teams'] != json.loads((ROOT/'configs/milestone2.json').read_text())['teams']:
        raise ValueError('Four-team pool changed')


def schedule(config: dict) -> list[dict]:
    result = []
    for batch in range(1,7):
        for arm in ARMS if batch % 2 else ARMS[::-1]:
            archive = config['archive_sequence'][batch-1]
            for j, opponent in enumerate(('v2','v5',f'{arm}-c{archive}')):
                result.append(dict(phase='training', arm=arm, batch=batch,
                    candidate=f'{arm}-c{batch-1}', opponent=opponent,
                    seed=config['seed']+100*batch+j, name=f'{arm}-b{batch}-vs-{opponent}'))
    for candidate in ('initial','control-c3','treatment-c3','treatment-c6','control-c6'):
        for j, opponent in enumerate(config['selection_panel']):
            result.append(dict(phase='selection', arm=candidate, candidate=candidate,
                opponent=opponent, seed=config['seed']+5000+j, name=f'{candidate}-vs-{opponent}'))
    for repeat in range(2):
        for j, opponent in enumerate(config['final_panel']):
            offset=(repeat+j)%3
            for arm in FINAL_ARMS[offset:]+FINAL_ARMS[:offset]:
                result.append(dict(phase='final', arm=arm, candidate=arm,
                    opponent=opponent, seed=config['seed']+10000+100*repeat+j,
                    name=f'{arm}-r{repeat}-vs-{opponent}'))
    return result


def candidate_path(root: Path, identity: str) -> Path:
    if identity in ('initial','historical-c0','control-c0','treatment-c0'):
        return root/'inputs/initial.json'
    if identity=='historical-c6':return root/'inputs/historical-c6.json'
    if identity in ARMS:return root/f'selected/{identity}.json'
    arm,number=identity.split('-c')
    if arm not in ARMS or int(number) not in range(1,7):raise ValueError('Unknown checkpoint identity')
    return root/f'checkpoints/{arm}/c{number}.json'


def opponent_record(root: Path, identity: str) -> dict:
    if identity=='v5':
        path=root/'inputs/v5.json';policy='learned-score'
    elif identity in ('random','max','v2'):
        path=None;policy={'random':'random','max':'max-base-power','v2':'gen1-heuristic'}[identity]
    else:
        path=candidate_path(root,identity);policy='reinforce'
    return {'identity':identity,'policy':policy,'checkpoint':str(path) if path else None,
            'sha256':sha256(path) if path else None}


def choose_checkpoints(root: Path, records: list[dict]) -> dict:
    scores={}
    for candidate in ('initial','control-c3','control-c6','treatment-c3','treatment-c6'):
        cells=[r for r in records if r['phase']=='selection' and r['arm']==candidate]
        if len(cells)!=3 or any(r['status']!='recorded' for r in cells):
            raise ValueError('Incomplete selection schedule')
        scores[candidate]=selection_score([b for r in cells for b in read_jsonl(root/r['path']/'battles.jsonl')])
    choices={}
    for arm in ARMS:
        ids=('initial',f'{arm}-c3',f'{arm}-c6')
        chosen=max(enumerate(ids),key=lambda pair:(*scores[pair[1]],-pair[0]))[1]
        choices[arm]={'identity':chosen,'sha256':sha256(candidate_path(root,chosen))}
    return {'scores':scores,'choices':choices,
        'rule':'most completed, then highest completed mean terminal R, then earliest c0/c3/c6'}


def readiness(config: dict) -> dict:
    start=time.monotonic()
    predictor,v5=artifacts()
    models={}
    for key in ('initial','historical_c6'):
        record=config[key];path=ROOT/record['path']
        if not path.is_file() or sha256(path)!=record['sha256']:
            raise ValueError(f'Required original {key} missing/changed; no regeneration')
        models[key]=load_checkpoint(path).sha256
    if load_checkpoint(ROOT/config['initial']['path']).parameters!=Parameters.initial():
        raise ValueError('Original initialization is not the specified zero residual')
    repair=json.loads((ROOT/'runs/reinforce-repair-20260909/verification.json').read_text())
    if not repair['ok'] or not repair['historical_full_source_audit']['audit']['ok']:
        raise ValueError('Required retained repair verification failed')
    for name,digest in repair['retained_checkpoints_loaded'].items():
        if load_checkpoint(ROOT/name).sha256!=digest:raise ValueError('Retained checkpoint changed: '+name)
    # Verify retained evidence without executing any old training or battle driver.
    manifests={}
    for name in ('reinforce-main','reinforce-repair-20260909'):
        root=ROOT/'runs'/name
        manifest=root/('artifact-hashes.json' if name=='reinforce-main' else 'hashes.json')
        records=json.loads(manifest.read_text())
        # Repair manifest also records metadata; its files member is explicit.
        if 'files' in records:records=records['files']
        for relative,digest in records.items():
            if not isinstance(digest,str) or len(digest)!=64:raise ValueError('Malformed retained hash manifest')
            base=ROOT if name=='reinforce-repair-20260909' else root
            if sha256(base/relative)!=digest:raise ValueError('Retained artifact changed: '+relative)
        manifests[manifest.relative_to(ROOT).as_posix()]=sha256(manifest)
    historical_keys={}
    for name in ('reinforce-main','reinforce-smoke'):
        historical_keys.update(json.loads((ROOT/'runs'/name/'ledger.json').read_text())['battle_partitions'])
    return {'ok':True,'predictor_sha256':predictor.sha256,'v5_sha256':v5.sha256,'models':models,
        'retained_checkpoints_loaded':len(repair['retained_checkpoints_loaded']),
        'manifests':manifests,'historical_battle_keys':sorted(historical_keys),
        'seconds':time.monotonic()-start}


def verify_frozen(root: Path, freeze: dict):
    if source_manifest()!=freeze['source']:raise ValueError('Frozen source changed')
    for name,digest in freeze['inputs'].items():
        if sha256(root/name)!=digest:raise ValueError('Frozen input changed: '+name)
    if sha256(ROOT/freeze['configuration']['document'])!=freeze['inputs']['specification.md']:
        raise ValueError('Scientific specification changed')


async def experiment(spec: Path, output: Path) -> dict:
    from .actor_step_report import build_report, audit_experiment, movement
    started=time.monotonic();cpu_started=time.process_time()
    output=output.resolve();spec=spec.resolve()
    if output.exists():raise ValueError('Fresh directory required; resume/retry is unsupported')
    config=json.loads(spec.read_text());validate_spec(config)
    output.mkdir(parents=True)
    ledger=Ledger(output,config,started=started)
    ledger.data.update(schema_version='actor-step-ledger-1',selection_reserved_before_training=True,
                       offline_preparation_reserve_seconds=config['offline_preparation_reserve_seconds'],
                       arm_planned_games={'training':{'control':432,'treatment':432},
                       'selection':{k:72 for k in ('initial','control-c3','control-c6','treatment-c3','treatment-c6')},
                       'final':{k:288 for k in FINAL_ARMS}})
    ledger.save();updates=[];failure=None;selection=None;freeze=None
    try:
        ready=readiness(config);write_json(output/'readiness.json',ready)
        for source,name in ((ROOT/config['initial']['path'],'inputs/initial.json'),
            (ROOT/config['historical_c6']['path'],'inputs/historical-c6.json'),
            (ROOT/'models/v4-supervised.json','inputs/predictor.json'),
            (ROOT/'runs/v5-acceptance/selected.json','inputs/v5.json'),
            (spec,'specification.json'),(ROOT/config['document'],'specification.md')):
            target=output/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        freeze={'schema_version':'actor-step-freeze-1','configuration':config,'source':source_manifest(),
            'inputs':{p.relative_to(output).as_posix():sha256(p) for p in output.rglob('*') if p.is_file() and p.name!='ledger.json'},
            'schedule':schedule(config)}
        write_json(output/'freeze.json',freeze)
        for name,digest in freeze['source'].items():
            target=output/'source-snapshot'/name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/name,target)
            if sha256(target)!=digest:raise ValueError('Source changed during copy')
        preflight=inspect_server(ROOT/'.local/pokemon-showdown',[ROOT/t for t in config['teams']],8000)
        write_json(output/'preflight.json',preflight)
        if ledger.elapsed()+config['offline_preparation_reserve_seconds']>=config['seconds']['overhead']:
            raise ValueError('Setup/preparation reserve exhausted')
        historical=set(ready['historical_battle_keys'])

        async def cell(entry: dict):
            verify_frozen(output,freeze)
            candidate=candidate_path(output,entry['candidate']);before=load_checkpoint(candidate).sha256
            opp=opponent_record(output,entry['opponent']);verify_opponents((opp,))
            path=output/entry['phase']/entry['name']
            index=ledger.reserve({**entry,'path':path.relative_to(output).as_posix(),
                'candidate_path':candidate.relative_to(output).as_posix(),'candidate_sha256':before,'opponent':opp})
            ledger.dispatch(index)
            print(f"{entry['phase']}: {entry['name']} (24 games)",flush=True)
            result=await run(RunConfig(agent_a='reinforce',agent_b=opp['policy'],battles=24,teams=tuple(config['teams']),
                checkpoint_a=str(candidate),checkpoint_b=opp['checkpoint'],
                predictor=str(output/'inputs/predictor.json') if opp['policy']=='learned-score' else None,
                seed=entry['seed'],turn_cap=300,timeout=60,run_timeout=min(300,ledger.remaining()-30)),path,True)
            try:audit=audit_run(path)
            except Exception as exc:audit={'ok':False,'error':repr(exc)}
            ledger.complete_run(index,path,result,audit)
            verify_frozen(output,freeze);verify_opponents((opp,))
            if sha256(candidate)!=before:raise ValueError('Learner changed during frozen rollout')
            if historical & ledger.data['battle_partitions'].keys():raise ValueError('Historical battle overlap')
            if not audit['ok'] or any(result.get(k) for k in BLOCKING):
                raise ValueError('Blocking integrity/protocol failure: '+str(audit))
            if ledger.remaining()<=0:raise ValueError('Phase time exhausted')
            return path

        plan=freeze['schedule'];ledger.begin('training')
        for batch in range(1,7):
            for arm in ARMS if batch%2 else ARMS[::-1]:
                entries=[e for e in plan if e['phase']=='training' and e['batch']==batch and e['arm']==arm]
                parent=load_checkpoint(candidate_path(output,f'{arm}-c{batch-1}'))
                pool=tuple(opponent_record(output,e['opponent']) for e in entries)
                write_json(output/f'batches/{arm}-b{batch}.json',{'parent_sha256':parent.sha256,
                    'arm':arm,'batch':batch,'opponents':pool,'schedule':entries,'multiplier':config['arms'][arm]})
                episodes=[];targets=[];paths=[]
                for entry in entries:
                    verify_opponents(pool);path=await cell(entry)
                    admitted,labels=trajectories(path,parent,'training')
                    episodes+=admitted;targets+=labels;paths.append(path.relative_to(output).as_posix())
                if not episodes:raise ValueError('No eligible completed trajectories; no update')
                params,metrics=controlled_update(parent,episodes,config['arms'][arm])
                saved=save_checkpoint(candidate_path(output,f'{arm}-c{batch}'),params,
                    {'experiment':'actor-step-1','arm':arm,'batch':batch,'phase':'training','run_paths':paths,
                     'actor_multiplier':config['arms'][arm],'parent_sha256':parent.sha256,'freeze_sha256':sha256(output/'freeze.json')})
                record={'arm':arm,'batch':batch,'parent_sha256':parent.sha256,'checkpoint_sha256':saved.sha256,
                    'metrics':metrics,'run_paths':paths,'opponent_pool':pool,
                    'target_exclusions':dict(Counter(t['exclusion'] or 'admitted' for t in targets))}
                write_json(output/f'batches/{arm}-targets-{batch}.json',targets)
                write_json(output/f'batches/{arm}-update-{batch}.json',record);updates.append(record)
                print(f"Update {arm} c{batch}: {len(episodes)}/72 eligible, actor delta {metrics['actor_delta_l2']:.6f}",flush=True)
        ledger.end();ledger.begin('selection')
        for entry in plan:
            if entry['phase']=='selection':await cell(entry)
        selection=choose_checkpoints(output,ledger.data['runs'])
        for arm,chosen in selection['choices'].items():
            target=output/f'selected/{arm}.json';target.parent.mkdir(exist_ok=True)
            shutil.copyfile(candidate_path(output,chosen['identity']),target)
        write_json(output/'selection.json',selection)
        ledger.end()
        write_json(output/'final-freeze.json',{'selection_sha256':sha256(output/'selection.json'),
            'arms':{arm:sha256(candidate_path(output,arm)) for arm in FINAL_ARMS},
            'panel':[opponent_record(output,i) for i in config['final_panel']]})
        ledger.begin('final')
        for entry in plan:
            if entry['phase']=='final':await cell(entry)
        ledger.end()
    except (Exception,KeyboardInterrupt) as exc:
        failure=f'{type(exc).__name__}: {exc}';print('STOP: '+failure,flush=True);ledger.end(failed=True)
    ledger.data['collection_stop_seconds']=ledger.elapsed();ledger.save()
    write_json(output/'updates.json',updates)
    report={};audit={'ok':False,'reason':'Not run'};diagnostics={}
    reporting_start=time.monotonic()
    def guard():
        overhead=ledger.elapsed()-sum(p['seconds'] for p in ledger.data['phases'].values())
        preparation=config['offline_preparation_reserve_seconds']
        if overhead+preparation>=config['seconds']['overhead'] or ledger.elapsed()+preparation>=config['maximum_seconds']:
            raise ValueError('Reporting/audit allocation exhausted')
    try:
        guard();report=build_report(output,ledger.data,config);write_json(output/'report.json',report)
        if freeze:
            audit=audit_experiment(output,ledger.data,check_hashes=False,guard=guard)
            if not audit['ok']:failure=failure or 'Post-collection audit failed'
            guard();diagnostics=movement(output,ledger.data,guard=guard)
            write_json(output/'movement.json',diagnostics)
        guard()
    except Exception as exc:
        failure=failure or f'Report/audit failure: {type(exc).__name__}: {exc}'
        audit={**audit,'reporting_error':repr(exc),'ok':False}
    write_json(output/'audit.json',audit)
    # All collection, optimizer, replay, report and content-hashing costs belong
    # to this one monotonic process duration, including the protected overhead.
    files=[p for p in sorted(output.rglob('*')) if p.is_file() and p.name not in ('ledger.json','summary.json','artifact-hashes.json')]
    hashes={p.relative_to(output).as_posix():sha256(p) for p in files}
    write_json(output/'artifact-hashes.json',hashes)
    listeners=[str(c.laddr) for c in psutil.net_connections(kind='tcp') if c.status=='LISTEN' and c.laddr.port==8000]
    if listeners:failure=failure or 'Server listener remains after cleanup'
    ledger.data.update(reporting_audit_seconds=time.monotonic()-reporting_start,
        python_process_cpu_seconds=time.process_time()-cpu_started,remaining_server_listeners=listeners,
        artifact_files=len(files),artifact_bytes=sum(p.stat().st_size for p in files))
    try:guard()
    except ValueError as exc:failure=failure or str(exc)
    ledger.data['process_plus_preparation_reserve_seconds']=ledger.elapsed()+config['offline_preparation_reserve_seconds']
    ledger.finish(failure)
    summary={'schema_version':'actor-step-experiment-1','status':ledger.data['status'],'failure':ledger.data['failure'],
        'ledger':ledger.data,'selection':selection,'updates':len(updates),'report':report,'audit':audit,'movement':diagnostics}
    write_json(output/'summary.json',summary)
    write_json(output/'closure-hashes.json',{name:sha256(output/name) for name in ('summary.json','ledger.json','artifact-hashes.json')})
    return {'status':summary['status'],'failure':summary['failure'],'output':str(output),'updates':len(updates),
        'selection':selection,'total_seconds':ledger.data['total_seconds'],'phases':report.get('phases',{}),'audit':audit}


def report_experiment(root: Path, audit=False) -> dict:
    from .actor_step_report import audit_experiment
    summary=json.loads((root/'summary.json').read_text())
    result=audit_experiment(root,summary['ledger']) if audit else {'ok':True,'performed':False,'read_only':True}
    return {**summary,'audit':result}
