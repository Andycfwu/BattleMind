"""Offline comparisons and replay audits for the frozen actor-step experiment."""
from collections import Counter, defaultdict
import json
from pathlib import Path
import time

import numpy as np

from .actor_step import controlled_update
from .environment import sha256
from .labels import read_jsonl
from .reinforce import load_checkpoint, features, softmax
from .reinforce_training import audit_run, trajectories
from .reinforce_experiment import bootstrap
from .reporting import summarize
from .schema import snapshot_from_dict


def aggregate(rows, requested):
    result=summarize([{**r,'match':i} for i,r in enumerate(rows)],requested)
    result['completed_mean_terminal_reward']=(result['a_wins']-result['b_wins'])/result['completed'] if result['completed'] else None
    result['incomplete_requested']=requested-result['completed']
    return result


def build_report(root: Path, ledger: dict, config: dict) -> dict:
    phases={};by_arm={};final_rows={};resources=[];labels=Counter();warnings=Counter()
    for phase in ('training','selection','final'):
        records=[r for r in ledger['runs'] if r['phase']==phase]
        allrows=[];groups=defaultdict(lambda:defaultdict(list));requests=Counter()
        for record in records:
            path=root/record['path']/'battles.jsonl'
            rows=read_jsonl(path) if path.exists() else []
            allrows+=rows;groups[record['arm']][record['opponent']['identity']]+=rows
            requests[record['arm'],record['opponent']['identity']]+=record['requested']
            if record['status']=='recorded':
                s=record['summary'];resources.append(s['resources'])
                labels.update({k:s['labels'][k] for k in ('attempts','verified_intended_choices','unknown_intended_choices')})
                warnings.update({k:s.get(k,0) or 0 for k in ('client_warning_records','known_gen1_annotation_warnings','unexpected_client_warning_records','server_crash_reports')})
        requested=sum(r['requested'] for r in records)
        phases[phase]={**aggregate(allrows,requested),'planned':config['games'][phase],
            'reserved':ledger['phases'][phase]['reserved'],'never_requested':config['games'][phase]-requested}
        by_arm[phase]={}
        for arm,planned in ledger['arm_planned_games'][phase].items():
            rows=[row for group in groups[arm].values() for row in group]
            actual=sum(v for (a,_),v in requests.items() if a==arm)
            by_arm[phase][arm]={'overall':{**aggregate(rows,actual),'planned':planned,'never_requested':planned-actual},
                'by_opponent':{opp:aggregate(rows,requests[arm,opp]) for opp,rows in groups[arm].items()}}
        if phase=='final':final_rows=dict(groups)
    comparisons={}
    for index,(left,right) in enumerate((('control','treatment'),('initial','treatment'),('initial','control'))):
        comparisons[f'{right}-minus-{left}']=bootstrap({'initial':final_rows.get(left,{}),
            'selected':final_rows.get(right,{})},config['bootstrap_seed']+index)
    return {'phases':phases,'by_arm':by_arm,'comparisons':comparisons,
        'labels':dict(labels),'warnings':dict(warnings),
        'resources':{'summed_python_cpu_seconds':sum(r['python_cpu_seconds'] for r in resources),
            'summed_last_server_cpu_seconds':sum(r['managed_server_cpu_seconds_last_sample'] or 0 for r in resources),
            'maximum_python_sampled_rss':max((r['python_peak_sampled_rss_bytes'] for r in resources),default=0),
            'maximum_server_sampled_rss':max((r['managed_server_peak_sampled_rss_bytes'] or 0 for r in resources),default=0)},
        'scope':'Fixed four-team pool, one training seed per condition; common policy seeds are not matched engine trajectories.'}


def audit_experiment(root: Path, ledger: dict, check_hashes=True, guard=lambda:None) -> dict:
    from .actor_step_experiment import (verify_frozen, candidate_path, schedule, choose_checkpoints,
                                       opponent_record, validate_spec)
    started=time.monotonic();errors=[];decisions=0;updates_checked=0
    freeze=json.loads((root/'freeze.json').read_text());config=freeze['configuration']
    validate_spec(config);verify_frozen(root,freeze)
    if freeze['schedule']!=schedule(config):raise ValueError('Frozen schedule differs from implementation')
    if check_hashes:
        for manifest in ('artifact-hashes.json','closure-hashes.json'):
            for name,digest in json.loads((root/manifest).read_text()).items():
                if sha256(root/name)!=digest:errors.append('Artifact hash mismatch: '+name)
    for name,digest in freeze['source'].items():
        if sha256(root/'source-snapshot'/name)!=digest:errors.append('Source archive changed: '+name)
    keys={};records=ledger['runs']
    for index,record in enumerate(records):
        guard()
        expected=freeze['schedule'][index]
        if any(record[k]!=expected[k] for k in expected if k!='opponent'):
            errors.append('Schedule metadata mismatch: '+record['path'])
        if record['opponent']!=opponent_record(root,expected['opponent']):errors.append('Frozen opponent mismatch')
        if record['status']!='recorded':errors.append('Unrecorded reserved/requested cell');continue
        path=root/record['path'];result=audit_run(path);decisions+=result['reinforce_decisions']
        if not result['ok']:errors.append('Private/policy audit failed: '+record['path'])
        meta=json.loads((path/'run.json').read_text());run_id=sha256(path/'run.json')
        if run_id!=record['run_id'] or meta['config']['seed']!=expected['seed']:
            errors.append('Run identity or seed mismatch')
        if (meta['reinforce_checkpoints']['a']['sha256']!=record['candidate_sha256']
            or sha256(root/record['candidate_path'])!=record['candidate_sha256']):errors.append('Frozen candidate mismatch')
        for row in read_jsonl(path/'battles.jsonl'):
            key=f"{run_id}:{row['match']}"
            if key in keys:errors.append('Repeated battle identity')
            keys[key]=record['phase']
    if keys!=ledger['battle_partitions']:errors.append('Phase identities differ from ledger')
    historical=set(json.loads((root/'readiness.json').read_text())['historical_battle_keys'])
    if historical&keys.keys():errors.append('Historical/development diagnostic overlap')
    for phase,p in ledger['phases'].items():
        cells=[r for r in records if r['phase']==phase]
        if sum(r['requested'] for r in cells)!=p['requested'] or sum(r['reserved'] for r in cells)!=p['reserved']:
            errors.append('Phase request/reservation mismatch')
    saved_updates=json.loads((root/'updates.json').read_text())
    for row in saved_updates:
        guard();arm=row['arm'];number=row['batch']
        parent=load_checkpoint(candidate_path(root,f'{arm}-c{number-1}'));episodes=[];targets=[]
        expected=[e for e in freeze['schedule'] if e['phase']=='training' and e['arm']==arm and e['batch']==number]
        if row['run_paths']!=[f"training/{e['name']}" for e in expected]:raise ValueError('Nontraining/stale batch source')
        pool=tuple(opponent_record(root,e['opponent']) for e in expected)
        batch_freeze=json.loads((root/f'batches/{arm}-b{number}.json').read_text())
        if batch_freeze['opponents']!=list(pool) or row['opponent_pool']!=list(pool):errors.append('Batch opponent pool changed')
        for path in row['run_paths']:
            batch,labels=trajectories(root/path,parent,'training');episodes+=batch;targets+=labels
        params,metrics=controlled_update(parent,episodes,config['arms'][arm])
        saved=load_checkpoint(candidate_path(root,f'{arm}-c{number}'))
        if (params!=saved.parameters or metrics!=row['metrics'] or saved.sha256!=row['checkpoint_sha256']
            or parent.sha256!=row['parent_sha256']):errors.append('Update reconstruction mismatch')
        if targets!=json.loads((root/f'batches/{arm}-targets-{number}.json').read_text()):errors.append('Target eligibility/reward mismatch')
        if dict(Counter(t['exclusion'] or 'admitted' for t in targets))!=row['target_exclusions']:errors.append('Exclusion mismatch')
        updates_checked+=1
    if ledger['phases']['training']['state']=='finished' and updates_checked!=12:errors.append('Missing completed update')
    if (root/'selection.json').exists():
        selected=json.loads((root/'selection.json').read_text())
        if selected!=json.loads(json.dumps(choose_checkpoints(root,records))):errors.append('Selection rule mismatch')
        final=json.loads((root/'final-freeze.json').read_text())
        if final['selection_sha256']!=sha256(root/'selection.json'):errors.append('Final selection changed')
        if final['panel']!=[opponent_record(root,i) for i in config['final_panel']]:errors.append('Final panel changed')
        for arm,digest in final['arms'].items():
            if sha256(candidate_path(root,arm))!=digest:errors.append('Evaluation mutated checkpoint')
    if (root/'report.json').exists() and build_report(root,ledger,config)!=json.loads((root/'report.json').read_text()):
        errors.append('Terminal accounting/report mismatch')
    return {'ok':not errors,'errors':errors,'replayed_decisions':decisions,'updates_reconstructed':updates_checked,
        'disjoint_battle_identities':len(keys),'historical_overlap':len(historical&keys.keys()),
        'full_schedule_recorded':len(records)==len(freeze['schedule']) and all(r['status']=='recorded' for r in records),
        'seconds':time.monotonic()-started,'read_only':True}


def draw_index(probabilities, draw):
    if type(draw) not in (int,float) or not np.isfinite(draw) or not 0<=draw<1:
        raise ValueError('Invalid or unavailable recorded draw')
    return min(int(np.searchsorted(np.cumsum(probabilities),draw,side='right')),len(probabilities)-1)


def movement(root: Path, ledger: dict, guard=lambda:None) -> dict:
    """Same-input descriptive diagnostics. No targets, optimizer calls or selection."""
    from .actor_step_experiment import candidate_path
    result={}
    for partition in ('training-diagnostic','final-descriptive'):
        identities=('initial','control-c3','control-c6','treatment-c3','treatment-c6') if partition=='training-diagnostic' else ('initial','control','treatment')
        if any(not candidate_path(root,i).exists() for i in identities):
            result[partition]={'available':False,'reason':'Required frozen checkpoints unavailable'};continue
        models={i:load_checkpoint(candidate_path(root,i)) for i in identities}
        matrices={i:np.asarray(m.parameters.actor) for i,m in models.items()}
        pairs=[('initial',i) for i in identities[1:]]+[(identities[1 if partition=='final-descriptive' else 2],identities[-1])]
        counts=Counter();stats=defaultdict(lambda:defaultdict(list))
        with (root/f'{partition}-distributions.jsonl').open('x',encoding='utf-8') as stream:
            for record in ledger['runs']:
                relevant=(record['phase']=='training' and record['batch']==1) if partition=='training-diagnostic' else record['phase']=='final'
                if not relevant or record['status']!='recorded':continue
                guard()
                for row in read_jsonl(root/record['path']/'decisions.jsonl'):
                    if row['player']!='a':continue
                    obs=snapshot_from_dict(row['observation']);s,a,prior=features(obs)
                    probabilities={i:softmax(prior+a@w.T@s) for i,w in matrices.items()}
                    draw=row.get('policy_evaluation',{}).get('draw')
                    choices={i:draw_index(p,draw) for i,p in probabilities.items()}
                    source=f"{record['arm']}/vs-{record['opponent']['identity']}"
                    for group in ('overall',source):
                        counts[group]+=1
                        for i,p in probabilities.items():
                            stats[group][i+'/entropy'].append(float(-p@np.log(p)))
                            stats[group][i+'/pmax'].append(float(p.max()))
                        for left,right in pairs:
                            p,q=probabilities[left],probabilities[right];key=f'{right}-vs-{left}'
                            values={'tv':float(.5*np.abs(p-q).sum()),'kl_left_to_right':float(p@np.log(p/q)),
                                'kl_right_to_left':float(q@np.log(q/p)),
                                'greedy_changed':int(p.argmax()!=q.argmax()),
                                'sampled_changed':int(choices[left]!=choices[right]),
                                'greedy_changed_from_exact_tie':int(p.argmax()!=q.argmax() and p[p.argmax()]==p[q.argmax()])}
                            for metric,value in values.items():stats[group][key+'/'+metric].append(value)
                    stream.write(json.dumps({'run_id':record['run_id'],'decision_id':row['decision_id'],
                        'snapshot_sha256':row['snapshot_sha256'],'generating_arm':record['arm'],'opponent':record['opponent']['identity'],
                        'draw':draw,'probabilities':{i:p.tolist() for i,p in probabilities.items()},
                        'sampled_choices':{i:obs.legal_actions[j].id for i,j in choices.items()}},allow_nan=False)+'\n')
        result[partition]={'available':True,'checkpoint_hashes':{i:m.sha256 for i,m in models.items()},
            'groups':{group:{'examples':counts[group],'metrics':{k:{'mean':float(np.mean(v)),
                'sum':float(np.sum(v)),'max':float(np.max(v)),'q50_95_99':np.quantile(v,[.5,.95,.99]).tolist()}
                for k,v in metrics.items()}} for group,metrics in stats.items()},
            'definition':'TV=0.5 sum |P-Q|; KL left-to-right=sum P log(P/Q), nats. Same stored uniform draw, right CDF boundary. Not counterfactual wins.',
            'snapshot_set':'All learner-a snapshots in both first training batches (including excluded episodes)' if partition=='training-diagnostic' else 'All final learner-a snapshots, descriptive after selection/freeze; not used for tuning'}
    return result
