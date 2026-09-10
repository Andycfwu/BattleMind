"""Read-only actor-step closure. No battles, training, or historical rewrites."""
import csv
import json
from pathlib import Path
import time

import numpy as np
import psutil

from battlemind.actor_step_experiment import report_experiment, candidate_path
from battlemind.environment import ROOT, sha256, source_manifest
from battlemind.labels import read_jsonl
from battlemind.reinforce import distribution, load_checkpoint
from battlemind.schema import snapshot_from_dict


def main():
    started=time.monotonic();cpu=time.process_time()
    root=ROOT/'runs/actor-step-acceptance';out=ROOT/'runs/actor-step-verification'
    if (out/'closure.json').exists():raise ValueError('Closure output already exists')
    summary=json.loads((root/'summary.json').read_text())
    before=json.loads((out/'before.json').read_text())['hashes']
    authorized={'src/battlemind/cli.py','README.md','docs/STATUS.md'}
    preserved=0
    for name,digest in before.items():
        if name in authorized:continue
        if sha256(ROOT/name)!=digest:raise ValueError('Preexisting artifact changed: '+name)
        preserved+=1
    hashes={p.relative_to(root).as_posix():sha256(p) for p in root.rglob('*') if p.is_file()}
    for manifest in ('artifact-hashes.json','closure-hashes.json'):
        for name,digest in json.loads((root/manifest).read_text()).items():
            if hashes[name]!=digest:raise ValueError('Experiment artifact changed: '+name)
    if source_manifest()!=json.loads((root/'freeze.json').read_text())['source']:
        raise ValueError('Frozen scientific source changed')
    first=report_experiment(root);second=report_experiment(root)
    if first!=second:raise ValueError('Repeated read-only report changed')
    # Independent inference checks of the first snapshot of every final game,
    # using retained rows in schedule order, regardless of terminal outcome.
    models={a:load_checkpoint(candidate_path(root,a)) for a in ('initial','control','treatment')}
    selected_rows={};decisions_checked=0;max_error=0.
    for r in summary['ledger']['runs']:
        if r['phase']!='final' or r['status']!='recorded':continue
        seen=set()
        for row in read_jsonl(root/r['path']/'decisions.jsonl'):
            if row['player']!='a' or row['match'] in seen:continue
            seen.add(row['match']);selected_rows[r['run_id'],row['decision_id']]=row
    for row in read_jsonl(root/'final-descriptive-distributions.jsonl'):
        source=selected_rows.get((row['run_id'],row['decision_id']))
        if source is None:continue
        obs=snapshot_from_dict(source['observation'])
        for name,model in models.items():
            p,*_=distribution(obs,model.parameters)
            error=float(np.max(np.abs(p-row['probabilities'][name])));max_error=max(max_error,error)
            if error!=0:raise ValueError('Distribution diagnostic differs from production inference')
            index=min(int(np.searchsorted(np.cumsum(p),row['draw'],side='right')),len(p)-1)
            if obs.legal_actions[index].id!=row['sampled_choices'][name]:raise ValueError('Choice diagnostic mismatch')
        decisions_checked+=1
    outcomes=[]
    for phase,arms in summary['report']['by_arm'].items():
        for arm,data in arms.items():
            for opponent,s in data['by_opponent'].items():
                outcomes.append({'phase':phase,'arm':arm,'opponent':opponent,**{k:s[k] for k in (
                    'requested','recorded','completed','a_wins','b_wins','draws','truncated','timeout','crash','cancelled','not_started','unrecorded','invalid_action_incidents','completed_mean_terminal_reward')}})
    with (out/'outcomes.csv').open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(outcomes[0]));writer.writeheader();writer.writerows(outcomes)
    exclusions=[]
    updates=json.loads((root/'updates.json').read_text())
    by_phase_arm={}
    for update in updates:
        targets=json.loads((root/f"batches/{update['arm']}-targets-{update['batch']}.json").read_text())
        for target in targets:
            run_id,match=target['battle_key'].split(':')
            record=next(r for r in summary['ledger']['runs'] if r.get('run_id')==run_id)
            exclusions.append({'arm':update['arm'],'batch':update['batch'],'opponent':record['opponent']['identity'],
                'battle_key':target['battle_key'],'reward':target['reward'],'exclusion':target['exclusion'] or 'admitted',
                'decisions':len(target['decision_ids'])})
    with (out/'training-admission.csv').open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(exclusions[0]));writer.writeheader();writer.writerows(exclusions)
    # Read-only reports must not alter even the finished ledger or stored summaries.
    after={p.relative_to(root).as_posix():sha256(p) for p in root.rglob('*') if p.is_file()}
    if after!=hashes:raise ValueError('Read-only verification changed experiment inputs')
    listeners=[str(c.laddr) for c in psutil.net_connections(kind='tcp') if c.status=='LISTEN' and c.laddr.port in (8000,8765)]
    if listeners:raise ValueError('Remaining server listener')
    result={'ok':True,'new_games':0,'new_model_updates':0,'preserved_preexisting_files':preserved,
        'experiment_files_unchanged':len(hashes),'audit':summary['audit'],
        'independent_snapshot_set':'First learner-a request in every recorded final game, all three checkpoints',
        'independent_snapshots_checked':decisions_checked,'maximum_probability_error':max_error,
        'two_read_only_reports_unchanged':True,'remaining_listeners':listeners,
        'checkpoint_hashes':{a:c.sha256 for a,c in models.items()},
        'seconds':time.monotonic()-started,'cpu_seconds':time.process_time()-cpu}
    (out/'closure.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    (out/'hashes.json').write_text(json.dumps({p.relative_to(ROOT).as_posix():sha256(p) for p in out.rglob('*') if p.is_file() and p.name!='hashes.json'},indent=2))
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
