"""One bounded research experiment, distinct from historical V5/V6 ledgers."""
from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path
import shutil
import time

import numpy as np

from .adaptation_experiment import artifacts
from .dataset import write_json
from .environment import ROOT, sha256, source_manifest
from .labels import read_jsonl
from .reinforce import Parameters, load_checkpoint, save_checkpoint, distribution
from .reinforce_training import audit_run, trajectories, update
from .runner import RunConfig, run
from .reporting import summarize
from .schema import snapshot_from_dict

PHASES=('training','selection','final')


class Ledger:
    """Single use; monotonic stop boundaries, protected phase allocations, no resume."""
    def __init__(self, root: Path, config: dict, clock=time.monotonic, started=None):
        self.root,self.config,self.clock=root,config,clock
        self.start=clock() if started is None else started
        self.active=None;self.phase_start=None;self.closed=False
        if (root/'ledger.json').exists():raise ValueError('Consumed ledger cannot resume')
        if sum(config['games'].values())>config['maximum_games'] or sum(config['seconds'].values())>config['maximum_seconds']:
            raise ValueError('Allocations exceed aggregate ceiling')
        self.data={'schema_version':'reinforce-ledger-1','status':'running','final_reserved_before_training':True,
            'planned_games':sum(config['games'].values()),'maximum_seconds':config['maximum_seconds'],
            'phases':{p:{'planned':config['games'][p],'reserved':0,'requested':0,'seconds':0.0,'state':'reserved'} for p in PHASES},
            'runs':[],'battle_partitions':{},'failure':None}
        self.save()

    def elapsed(self):return self.clock()-self.start

    def save(self):
        temporary=self.root/'ledger.pending.json'
        temporary.write_text(json.dumps(self.data,indent=2,allow_nan=False))
        temporary.replace(self.root/'ledger.json')

    def begin(self,phase):
        if self.closed or self.active or self.data['phases'][phase]['state']!='reserved' or any(self.data['phases'][p]['state']!='finished' for p in PHASES[:PHASES.index(phase)]):
            raise ValueError('Invalid phase order/resume')
        if self.elapsed()-sum(p['seconds'] for p in self.data['phases'].values())>=self.config['seconds']['overhead']:
            raise ValueError('Setup/reporting reserve exhausted')
        self.active=phase;self.phase_start=self.clock()
        self.data['phases'][phase].update(state='running',start_seconds=self.elapsed());self.save()

    def remaining(self):
        if self.active is None:raise ValueError('No active phase')
        return min(self.config['seconds'][self.active]-(self.clock()-self.phase_start),self.config['maximum_seconds']-self.elapsed())

    def reserve(self,metadata,games=24):
        if self.closed or not self.active:raise ValueError('Cannot request outside active phase')
        phase=self.data['phases'][self.active]
        if games!=24 or phase['reserved']+games>phase['planned'] or self.remaining()<90:
            raise ValueError('Game/time budget exhausted; no borrowing or retry')
        phase['reserved']+=games
        record={**metadata,'phase':self.active,'reserved':games,'requested':0,'status':'reserved'}
        self.data['runs'].append(record);self.save()
        return len(self.data['runs'])-1

    def dispatch(self,index):
        record=self.data['runs'][index]
        if record['status']!='reserved':raise ValueError('Duplicate dispatch')
        record.update(requested=record['reserved'],status='requested')
        self.data['phases'][record['phase']]['requested']+=record['requested'];self.save()

    def complete_run(self,index,path,summary,audit):
        record=self.data['runs'][index]
        if record['status']!='requested':raise ValueError('Duplicate/missing request')
        rows=read_jsonl(path/'battles.jsonl');run_id=sha256(path/'run.json')
        keys=[f"{run_id}:{row['match']}" for row in rows]
        if len(keys)!=record['requested'] or len(set(keys))!=len(keys) or set(keys)&self.data['battle_partitions'].keys():
            raise ValueError('Missing/overlapping phase identities')
        self.data['battle_partitions'].update({key:record['phase'] for key in keys})
        record.update(status='recorded',run_id=run_id,summary=summary,audit=audit);self.save()

    def end(self,failed=False):
        if self.active is None:return
        phase=self.data['phases'][self.active]
        duration=self.clock()-self.phase_start
        phase.update(seconds=duration,stop_seconds=self.elapsed(),state='failed' if failed else 'finished')
        old=self.active;self.active=None;self.save()
        if not failed and (phase['requested']!=phase['planned'] or duration>self.config['seconds'][old]):
            phase['state']='failed';self.save();raise ValueError('Phase schedule or wall allocation incomplete')

    def finish(self,failure=None):
        if self.closed:return
        self.end(failed=True)
        total=self.elapsed();overhead=total-sum(p['seconds'] for p in self.data['phases'].values())
        if total>self.config['maximum_seconds'] or overhead>self.config['seconds']['overhead']:
            failure=failure or 'Aggregate/reporting budget exhausted'
        if any(p['state']!='finished' for p in self.data['phases'].values()):failure=failure or 'Incomplete phases'
        self.data.update(status='failed' if failure else 'finished',failure=failure,total_seconds=total,overhead_seconds=overhead)
        self.closed=True;self.save()


def validate_spec(config):
    mode=config.get('kind')
    if mode not in {'smoke','main'} or config.get('schema_version')!='reinforce-spec-1':raise ValueError('Unsupported research spec')
    max_games,max_seconds=(48,300) if mode=='smoke' else (2400,3600)
    if config['maximum_games']>max_games or config['maximum_seconds']>max_seconds:raise ValueError('User ceiling exceeded')
    rounds=config['updates']
    if mode=='smoke':expected={'training':24,'selection':0,'final':24}
    else:
        if not 2<=rounds<=20 or config['games']['final']<576:raise ValueError('Invalid research rounds/final reservation')
        expected={'training':rounds*72,'selection':216,'final':576}
    if config['games']!=expected or config['teams']!=json.loads((ROOT/'configs/milestone2.json').read_text())['teams']:
        raise ValueError('Schedule must preserve complete four-team blocks')
    if config['candidates']!=[0,rounds//2,rounds] and mode=='main':raise ValueError('Selection candidates not predeclared')
    if config['actor_lr']!=(.3 if mode=='smoke' else 30.0) or config['value_lr']!=.1:raise ValueError('New hyperparameters need a new reviewed specification')


def selection_score(rows):
    """Completion count first; then conditional mean reward; then earlier checkpoint."""
    complete=[r for r in rows if r['status']=='completed']
    return len(complete),sum({'a':1,'b':-1,'draw':0}[r['winner']] for r in complete)/len(complete) if complete else -2


def verify_opponents(pool):
    if not isinstance(pool,tuple) or not 1<=len(pool)<=6:raise ValueError('Frozen bounded opponent tuple required')
    for opp in pool:
        if opp['checkpoint'] and sha256(Path(opp['checkpoint']))!=opp['sha256']:
            raise ValueError('Frozen opponent checkpoint changed')


async def experiment(spec: Path, output: Path) -> dict:
    started=time.monotonic();spec=spec.resolve();output=output.resolve()
    if output.exists():raise ValueError('Fresh experiment required; no resume/retry')
    config=json.loads(spec.read_text());validate_spec(config)
    predictor,reference=artifacts()  # Original V4/V5 compatibility, no regeneration.
    output.mkdir(parents=True)
    ledger=Ledger(output,config,started=started)
    for source,destination in ((ROOT/'models/v4-supervised.json','predictor.json'),(ROOT/'runs/v5-acceptance/selected.json','v5-reference.json'),(spec,'specification.json'),(ROOT/config['document'],'specification.md')):
        shutil.copyfile(source,output/destination)
    freeze={'source':source_manifest(),'spec_sha256':sha256(spec),'document_sha256':sha256(ROOT/config['document']),
        'predictor_sha256':predictor.sha256,'v5_sha256':reference.sha256,'configuration':config}
    write_json(output/'freeze.json',freeze)
    for name,digest in freeze['source'].items():
        target=output/'source-snapshot'/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/name,target)
        if sha256(target)!=digest:raise ValueError('Source changed during freeze')
    checkpoints={0:output/'checkpoints/c0.json'}
    save_checkpoint(checkpoints[0],Parameters.initial(),{'kind':'zero residual; V2 softmax prior; no imitation','freeze_sha256':sha256(output/'freeze.json')})
    updates=[];failure=None;selection=None

    def verify():
        if source_manifest()!=freeze['source'] or sha256(spec)!=freeze['spec_sha256'] or sha256(ROOT/config['document'])!=freeze['document_sha256']:
            raise ValueError('Frozen code/spec changed during collection')
        if sha256(output/'predictor.json')!=predictor.sha256 or sha256(output/'v5-reference.json')!=reference.sha256:
            raise ValueError('Frozen reference artifacts changed')

    def opponent(identity):
        if identity.startswith('c'):
            p=checkpoints[int(identity[1:])];return {'identity':identity,'policy':'reinforce','checkpoint':str(p),'sha256':sha256(p)}
        if identity=='v5':return {'identity':'v5','policy':'learned-score','checkpoint':str(output/'v5-reference.json'),'sha256':reference.sha256}
        return {'identity':identity,'policy':{'v2':'gen1-heuristic','random':'random','max':'max-base-power'}[identity],'checkpoint':None,'sha256':None}

    async def cell(name,candidate,opp,seed):
        verify();before=sha256(candidate)
        verify_opponents((opp,))
        path=output/ledger.active/name
        index=ledger.reserve({'path':path.relative_to(output).as_posix(),'candidate':candidate.relative_to(output).as_posix(),
            'candidate_sha256':before,'opponent':opp,'seed':seed})
        ledger.dispatch(index)
        print(f'{ledger.active}: {name} (24 games)',flush=True)
        result=await run(RunConfig(agent_a='reinforce',agent_b=opp['policy'],battles=24,teams=tuple(config['teams']),
            predictor=str(output/'predictor.json') if opp['policy']=='learned-score' else None,
            checkpoint_a=str(candidate),checkpoint_b=opp['checkpoint'],seed=seed,turn_cap=300,timeout=60,
            run_timeout=min(300,ledger.remaining()-30)),path,True)
        try:audit=audit_run(path)
        except Exception as exc:audit={'ok':False,'error':repr(exc)}
        ledger.complete_run(index,path,result,audit)
        verify()
        if sha256(candidate)!=before or (opp['checkpoint'] and sha256(Path(opp['checkpoint']))!=opp['sha256']):raise ValueError('Model changed during frozen rollout')
        if not audit['ok'] or any(result.get(k) for k in ('crash','timeout','cancelled','not_started','unrecorded','invalid_action_incidents','unexpected_client_warning_records','server_crash_reports')):
            raise ValueError('Blocking run/audit/protocol failure: '+str(audit))
        # Caps are retained and excluded from rewards; validated later independent cells continue.
        if ledger.remaining()<=0:raise ValueError('Phase time exhausted')
        return path

    try:
        ledger.begin('training')
        for number in range(1,config['updates']+1):
            parent=load_checkpoint(checkpoints[number-1]);frozen=[]
            if config['kind']=='smoke':identities=['c0']
            else:
                # Fixed references plus alternating initialization/recent archived learner.
                archived=0 if number%2 or number<=2 else number-2
                identities=['v2','v5',f'c{archived}']
            pool=tuple(opponent(i) for i in identities)
            write_json(output/f'batches/b{number}.json',{'parent_sha256':parent.sha256,'opponents':pool,'seed':config['seed']+number*100,'admission':'references + c0/recent even archive; at most 4 retained pool identities'})
            episodes=[];targets=[];paths=[]
            for j,opp in enumerate(pool):
                verify_opponents(pool)
                path=await cell(f'b{number}-vs-{opp["identity"]}',checkpoints[number-1],opp,config['seed']+number*100+j)
                batch,label_rows=trajectories(path,parent,'training')
                episodes+=batch;targets+=label_rows;paths.append(path.relative_to(output).as_posix())
            if not episodes:raise ValueError('No eligible completed training trajectories')
            params,metrics=update(parent,episodes,config['actor_lr'],config['value_lr'])
            checkpoints[number]=output/f'checkpoints/c{number}.json'
            saved=save_checkpoint(checkpoints[number],params,{'phase':'training','parent_sha256':parent.sha256,'batch':number,'run_paths':paths})
            record={'batch':number,'parent_sha256':parent.sha256,'checkpoint_sha256':saved.sha256,'metrics':metrics,
                'run_paths':paths,'opponent_pool':pool,'target_exclusions':dict(Counter(t['exclusion'] or 'admitted' for t in targets))}
            write_json(output/f'batches/targets-{number}.json',targets)
            write_json(output/f'batches/update-{number}.json',record);updates.append(record)
            print(f'Update {number}: {len(episodes)} completed trajectories, actor delta={metrics["actor_delta_l2"]:.6f}',flush=True)
        ledger.end();ledger.begin('selection')
        selection_rows={}
        if config['kind']=='main':
            for number in config['candidates']:
                rows=[]
                for j,identity in enumerate(('v2','v5','c0')):
                    path=await cell(f'c{number}-vs-{identity}',checkpoints[number],opponent(identity),config['seed']+5000+j)
                    rows+=read_jsonl(path/'battles.jsonl')
                selection_rows[number]=selection_score(rows)
            chosen=max(config['candidates'],key=lambda n:(*selection_rows[n],-n))
        else:chosen=config['updates']
        selection={'chosen':chosen,'checkpoint_sha256':sha256(checkpoints[chosen]),'scores':selection_rows,
            'rule':'most completed scheduled games, then highest completed mean reward, then earliest checkpoint; no capped reward'}
        shutil.copyfile(checkpoints[chosen],output/'selected.json');write_json(output/'selection.json',selection)
        ledger.end();ledger.begin('final')
        panel=('v2',) if config['kind']=='smoke' else ('random','max','v2','v5','c0',f"c{config['updates']//2}")
        arms=('selected',) if config['kind']=='smoke' else ('initial','selected')
        write_json(output/'final-freeze.json',{'initial_sha256':sha256(checkpoints[0]),'selected_sha256':sha256(output/'selected.json'),
            'panel':[opponent(i) for i in panel],'arms':arms,'selection_sha256':sha256(output/'selection.json')})
        for repeat in range(1 if config['kind']=='smoke' else 2):
            for j,identity in enumerate(panel):
                for arm in arms:
                    candidate=checkpoints[0] if arm=='initial' else output/'selected.json'
                    await cell(f'{arm}-r{repeat}-vs-{identity}',candidate,opponent(identity),config['seed']+10000+100*repeat+j)
        ledger.end()
    except Exception as exc:
        failure=f'{type(exc).__name__}: {exc}';print(f'STOP: {failure}',flush=True);ledger.end(failed=True)
    ledger.data['collection_stop_seconds']=ledger.elapsed()
    write_json(output/'updates.json',updates)
    # Reporting is included in the separately protected overhead allocation.
    try:result=build_report(output,ledger.data,config)
    except Exception as exc:
        failure=failure or f'Reporting failure: {exc}'
        result={'error':repr(exc),'phases':ledger.data['phases']}
    write_json(output/'report.json',result)
    hashes={p.relative_to(output).as_posix():sha256(p) for p in sorted(output.rglob('*')) if p.is_file() and p.name not in {'ledger.json','summary.json','artifact-hashes.json'}}
    write_json(output/'artifact-hashes.json',hashes)
    ledger.finish(failure)
    summary={'schema_version':'reinforce-experiment-1','status':ledger.data['status'],'failure':ledger.data['failure'],
        'ledger':ledger.data,'updates':len(updates),'selection':selection,'report':result}
    write_json(output/'summary.json',summary)
    return {'status':summary['status'],'failure':summary['failure'],'updates':len(updates),'selection':selection,'total_seconds':ledger.data['total_seconds'],'output':str(output),'phases':result['phases']}


def build_report(root,ledger,config):
    phases={};by_opponent={};final_rows={};resources=[];labels=Counter();warnings=Counter()
    for phase in PHASES:
        records=[r for r in ledger['runs'] if r['phase']==phase]
        requested=sum(r['requested'] for r in records);rows=[]
        for r in records:
            path=root/r['path']
            if not (path/'battles.jsonl').exists():continue
            games=read_jsonl(path/'battles.jsonl')
            # Remap only aggregation indices; retain actual identities in the ledger.
            offset=len(rows)
            rows.extend({**g,'match':offset+i} for i,g in enumerate(games))
            by_opponent.setdefault(phase,{}).setdefault(r['opponent']['identity'],[]).extend(games)
            if r['status']=='recorded':
                s=r['summary'];resources.append(s['resources'])
                labels.update({k:s['labels'][k] for k in ('attempts','verified_intended_choices','unknown_intended_choices')})
                warnings.update({k:s.get(k,0) or 0 for k in ('client_warning_records','known_gen1_annotation_warnings','unexpected_client_warning_records','server_crash_reports')})
            if phase=='final':
                arm=Path(r['path']).name.split('-r')[0]
                final_rows.setdefault(arm,{}).setdefault(r['opponent']['identity'],[]).extend(games)
        phases[phase]={**summarize(rows,requested),'planned':config['games'][phase],
            'reserved':ledger['phases'][phase]['reserved'],'never_requested':config['games'][phase]-requested}
    def aggregate(rows):return summarize([{**r,'match':i} for i,r in enumerate(rows)],len(rows))
    final={arm:{'by_opponent':{opp:aggregate(rows) for opp,rows in groups.items()},'overall':aggregate([r for rows in groups.values() for r in rows])} for arm,groups in final_rows.items()}
    interval=bootstrap(final_rows,config['seed']+20000)
    differences=Counter();comparisons=0
    if (root/'selected.json').exists():
        initial=load_checkpoint(root/'checkpoints/c0.json');selected=load_checkpoint(root/'selected.json')
        with (root/'decision-differences.jsonl').open('x',encoding='utf-8') as stream:
            for record in ledger['runs']:
                if record['phase']!='final' or record['status']!='recorded':continue
                for row in read_jsonl(root/record['path']/'decisions.jsonl'):
                    if row['player']!='a':continue
                    obs=snapshot_from_dict(row['observation'])
                    pi,*_=distribution(obs,initial.parameters);ps,*_=distribution(obs,selected.parameters)
                    evaluation=row.get('policy_evaluation')
                    if not isinstance(evaluation,dict) or 'draw' not in evaluation:
                        raise ValueError('Missing recorded policy draw for '+row['decision_id'])
                    draw=evaluation['draw']
                    if type(draw) not in (int,float) or not np.isfinite(draw) or not 0<=draw<1:
                        raise ValueError('Invalid recorded policy draw for '+row['decision_id'])
                    # Match ReinforceAgent.act at exact CDF boundaries too.
                    ai=min(int(np.searchsorted(np.cumsum(pi),draw,side='right')),len(pi)-1)
                    az=min(int(np.searchsorted(np.cumsum(ps),draw,side='right')),len(ps)-1)
                    differences['argmax_changed']+=int(pi.argmax()!=ps.argmax());differences['shared_draw_changed']+=int(ai!=az)
                    comparisons+=1
                    stream.write(json.dumps({'run_id':record['run_id'],'decision_id':row['decision_id'],'snapshot_sha256':row['snapshot_sha256'],
                        'initial_probabilities':pi.tolist(),'selected_probabilities':ps.tolist(),'shared_draw':draw,
                        'initial_choice':obs.legal_actions[ai].id,'selected_choice':obs.legal_actions[az].id})+'\n')
    return {'phases':phases,'by_opponent':{phase:{o:aggregate(rows) for o,rows in groups.items()} for phase,groups in by_opponent.items()},
        'final':final,'uncertainty':interval,'same_snapshot':{'examples':comparisons,**differences},'labels':dict(labels),'warnings':dict(warnings),
        'resources':{'summed_python_cpu_seconds':sum(r['python_cpu_seconds'] for r in resources),
            'summed_last_server_cpu_seconds':sum(r['managed_server_cpu_seconds_last_sample'] or 0 for r in resources),
            'maximum_python_sampled_rss':max((r['python_peak_sampled_rss_bytes'] for r in resources),default=0),
            'maximum_server_sampled_rss':max((r['managed_server_peak_sampled_rss_bytes'] or 0 for r in resources),default=0)},
        'scope':'Fixed four teams; unmatched simulator randomness; capped episodes have no reward. No human/generation generalization.'}


def bootstrap(groups,seed):
    if set(groups)!={'initial','selected'}:return {'available':False,'reason':'Both final arms required'}
    opponents=sorted(set(groups['initial'])&set(groups['selected']))
    blocks=[]
    for opp in opponents:
        a,b=groups['initial'][opp],groups['selected'][opp]
        if len(a)!=48 or len(b)!=48:return {'available':False,'reason':'Incomplete requested final schedule'}
        blocks.append([(a[i:i+4],b[i:i+4]) for i in range(0,48,4)])
    if len(opponents)!=6:return {'available':False,'reason':'Incomplete fixed panel'}
    rng=np.random.default_rng(seed);samples=[];bounds=[]
    def stats(rows):
        complete=[r for r in rows if r['status']=='completed'];reward=sum({'a':1,'b':-1,'draw':0}[r['winner']] for r in complete)
        n=len(rows);missing=n-len(complete)
        return reward/len(complete) if complete else None,(reward-missing)/n,(reward+missing)/n
    for _ in range(1000):
        a=[];b=[]
        for pairs in blocks:
            for i in rng.integers(0,len(pairs),len(pairs)):
                a.extend(pairs[i][0]);b.extend(pairs[i][1])
        x,y=stats(a),stats(b)
        if x[0] is not None and y[0] is not None:samples.append(y[0]-x[0])
        bounds.append((y[1]-x[2],y[2]-x[1]))
    original_a=[r for rows in groups['initial'].values() for r in rows];original_b=[r for rows in groups['selected'].values() for r in rows]
    x,y=stats(original_a),stats(original_b)
    return {'available':True,'seed':seed,'resamples':1000,'schedule_blocks':72,'method':'stratified four-game team/side-block bootstrap; shared block indices, not engine RNG',
        'completed_reward_difference':y[0]-x[0] if x[0] is not None and y[0] is not None else None,
        'completed_reward_interval':np.quantile(samples,[.025,.975]).tolist() if samples else None,
        'all_requested_unknown_reward_bounds':[y[1]-x[2],y[2]-x[1]],
        'unknown_bound_interval':[float(np.quantile(np.array(bounds)[:,0],.025)),float(np.quantile(np.array(bounds)[:,1],.975))],
        'limitation':'Conditional completed-game estimates can be selection-biased; bounds are sensitivity analysis, never imputed game rewards.'}


def report_experiment(root: Path,audit=False):
    summary=json.loads((root/'summary.json').read_text());errors=[];checked=0
    if audit:
        for name,digest in json.loads((root/'artifact-hashes.json').read_text()).items():
            if sha256(root/name)!=digest:errors.append('Hash mismatch: '+name)
        freeze=json.loads((root/'freeze.json').read_text())
        if source_manifest()!=freeze['source']:errors.append('Experiment full source no longer matches; historical source needed for full audit')
        records=summary['ledger']['runs'];keys=[]
        for r in records:
            if r['status']!='recorded':errors.append('Missing recorded run');continue
            result=audit_run(root/r['path']);checked+=result['reinforce_decisions']
            keys.extend((f"{r['run_id']}:{b['match']}",r['phase']) for b in read_jsonl(root/r['path']/'battles.jsonl'))
        if len(dict(keys))!=len(keys) or dict(keys)!=summary['ledger']['battle_partitions']:errors.append('Phase identity mismatch')
        for row in json.loads((root/'updates.json').read_text()):
            number=row['batch'];parent=load_checkpoint(root/f'checkpoints/c{number-1}.json');episodes=[]
            for name in row['run_paths']:
                if not name.startswith('training/'):raise ValueError('Nontraining source in update')
                batch,_=trajectories(root/name,parent,'training');episodes+=batch
            params,metrics=update(parent,episodes,freeze['configuration']['actor_lr'],freeze['configuration']['value_lr'])
            if params!=load_checkpoint(root/f'checkpoints/c{number}.json').parameters or metrics!=row['metrics']:errors.append('Outcome-driven update reconstruction mismatch')
    return {**summary,'audit':{'ok':not errors,'errors':errors,'replayed_decisions':checked,'read_only':True}}
