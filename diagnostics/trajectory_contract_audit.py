"""Retained-only sampled-action audit. Does not import/call any optimizer or collector."""
from collections import Counter, defaultdict
from dataclasses import asdict
import csv
import importlib.metadata
import json
import math
from pathlib import Path
import random
import re
import subprocess
import time

import numpy as np
import psutil

from battlemind.environment import ROOT, sha256
from battlemind.labels import read_jsonl, snapshot_hash, expected_engine_choice, audit_labels
from battlemind.reinforce import ReinforceAgent, load_checkpoint
from battlemind.schema import snapshot_from_dict
from battlemind.adapter import resolve_action
from battlemind.runner import policy_seed, scheduled_match
from battlemind.adaptation_experiment import artifacts

OUT = ROOT/'runs/trajectory-contract-audit-20260910'


def save(name, obj):
    with (OUT/name).open('x', encoding='utf-8') as stream:
        json.dump(obj, stream, indent=2, allow_nan=False)


def csv_save(name, rows):
    with (OUT/name).open('x', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def strict_cdf(probabilities, draw):
    """Independent loop, strict '<' makes boundary ownership explicit."""
    cumulative = 0.0
    for index, value in enumerate(probabilities):
        cumulative += value
        if draw < cumulative:
            return index
    return len(probabilities)-1


def grouping(episodes, keys):
    groups = defaultdict(list)
    for row in episodes:
        groups[tuple(row[k] for k in keys)].append(row)
    result = []
    for key, rows in sorted(groups.items(), key=str):
        excluded = [r for r in rows if r['exclusion']]
        complete = [r for r in rows if r['status']=='completed']
        result.append({**dict(zip(keys, key)), 'episodes':len(rows),
            'completed':len(complete), 'excluded':len(excluded),
            'unknown_commitment_episodes':sum(r['exclusion']=='unknown_commitment_episode' for r in rows),
            'excluded_decisions':sum(r['decisions'] for r in excluded),
            'verified_records_in_excluded':sum(r['verified'] for r in excluded),
            'unknown_records':sum(r['unknown'] for r in rows),
            'mean_decisions':sum(r['decisions'] for r in rows)/len(rows),
            'wins':sum(r['winner']=='a' for r in complete),
            'losses':sum(r['winner']=='b' for r in complete),
            'draws':sum(r['winner']=='draw' for r in complete)})
    return result


def run():
    started=time.monotonic(); cpu=time.process_time(); peak=0
    before=json.loads((OUT/'inputs-before.json').read_text())['hashes']
    versions=json.loads((ROOT/'configs/versions.json').read_text())
    assert importlib.metadata.version('poke-env')==versions['poke_env']=='0.16.1'
    pin=subprocess.check_output(['git','-C',str(ROOT/'.local/pokemon-showdown'),'rev-parse','HEAD'],text=True).strip()
    assert pin==versions['showdown_commit']
    engine_diff=subprocess.check_output(['git','-C',str(ROOT/'.local/pokemon-showdown'),'diff','--name-only','HEAD'],text=True)
    assert not engine_diff, engine_diff
    predictor,v5=artifacts()  # Intended strict V4/V5 loaders; no fitting.
    manifest_checks={}; loaded={}; source_checks={}
    totals=Counter(); contexts=Counter(); episode_rows=[]; discrepancy_rows=[]; samples=[]
    all_targets={}; all_events=Counter(); critical_events=[]; cdf_ties=0
    for experiment in ('reinforce-main','actor-step-acceptance'):
        base=ROOT/'runs'/experiment
        manifest_path=(base/'artifact-hashes.json' if experiment=='reinforce-main'
                       else ROOT/'runs/actor-step-verification/experiment-content-hashes.json')
        manifest=json.loads(manifest_path.read_text())
        for rel,digest in manifest.items():
            assert before[(base/rel).relative_to(ROOT).as_posix()]==digest, (experiment,rel)
        manifest_checks[experiment]={'path':str(manifest_path.relative_to(ROOT)),
                                    'sha256':sha256(manifest_path),'entries':len(manifest)}
        # Original full source is retained; no attempt to bypass repaired compatibility.
        frozen=json.loads((base/'freeze.json').read_text())['source']
        for rel,digest in frozen.items():
            assert sha256(base/'source-snapshot'/rel)==digest,(experiment,rel)
        source_checks[experiment]={name:sha256(ROOT/'src/battlemind'/name)==sha256(base/'source-snapshot/src/battlemind'/name)
            for name in ('runner.py','adapter.py','labels.py','schema.py','reinforce_training.py')}
        assert all(source_checks[experiment].values())
        for p in (base/'batches').glob('*targets*.json'):
            for row in json.loads(p.read_text()):
                assert row['battle_key'] not in all_targets
                all_targets[row['battle_key']]=row
        ledger=json.loads((base/'ledger.json').read_text())
        for cell in ledger['runs']:
            path=base/cell['path']; phase=path.parent.name
            meta=json.loads((path/'run.json').read_text()); run_hash=sha256(path/'run.json')
            audit_labels(path)  # Rebuild exact original commitment/execution joins, read-only.
            cps={side:load_checkpoint(path/info['path']) for side,info in meta['reinforce_checkpoints'].items()}
            for side,cp in cps.items():
                assert cp.sha256==meta['reinforce_checkpoints'][side]['sha256']
                loaded[str((path/meta['reinforce_checkpoints'][side]['path']).relative_to(ROOT))]=cp.sha256
            rows=read_jsonl(path/'decisions.jsonl')
            events=read_jsonl(path/'events.jsonl'); all_events.update(e['kind'] for e in events)
            submitted=Counter((e['match'],e['player'],e['request_id']) for e in events if e['kind']=='submitted')
            critical_events.extend({'run':str(path.relative_to(ROOT)),**e} for e in events
                                   if e['kind'] in {'server_error','adapter_exception'})
            labels={r['decision_id']:r for r in read_jsonl(path/'privileged/labels.jsonl')}
            grouped=defaultdict(list)
            for row in rows: grouped[(row['match'],row['player'])].append(row)
            totals[experiment+':cells']+=1
            for battle in read_jsonl(path/'battles.jsonl'):
                match=battle['match']; totals[experiment+':battles']+=1
                assert battle['invalid_actions']==0
                assignments,challenger=scheduled_match(match+meta['config']['schedule_offset'],4)
                assert assignments==battle['team_indices'] and challenger==battle['challenger']
                histories=json.loads((path/f'privileged/{match:03d}-histories.json').read_text())
                engine_path=path/battle['engine_record']['path']; assert sha256(engine_path)==battle['engine_record']['sha256']
                record=json.loads(engine_path.read_text())
                committed=defaultdict(list)
                for i,line in enumerate(record['inputLog']):
                    m=re.fullmatch(r'>(p[12]) (move .+|switch \d+)',line)
                    if m:committed[m[1]].append((i,m[2]))
                for side in ('a','b'):
                    attempts=grouped[(match,side)]
                    assert read_jsonl(path/f'privileged/attempts/{match:03d}-{side}.jsonl')==attempts
                    ids=[r['observation']['request_id'] for r in attempts]
                    assert ids==sorted(set(ids)), (path,match,side,'request order')
                    actions=committed[battle['player_roles'][side]]
                    assert len(actions)==len(attempts),(path,match,side,'sequence length')
                    # Equal lengths and sends are necessary; no assertion that these alone prove alignment.
                    policy=ReinforceAgent(cps[side],policy_seed(meta['config']['seed'],match,side)) if side in cps else None
                    rng=random.Random(policy_seed(meta['config']['seed'],match,side))
                    first=None; unknown=verified=0; earlier_history=[]; row_details=[]
                    for index,row in enumerate(attempts):
                        obs=row['observation']; label=labels[row['decision_id']]
                        assert submitted[(match,side,obs['request_id'])]==1
                        assert snapshot_hash(obs)==row['snapshot_sha256']==label['snapshot_sha256']
                        assert obs['public_history'][:len(earlier_history)]==earlier_history
                        assert histories[side][:len(obs['public_history'])]==obs['public_history']
                        earlier_history=obs['public_history']
                        frozen_obs=snapshot_from_dict(obs)
                        legal=obs['legal_actions']; ids=[a['id'] for a in legal]
                        assert len(ids)==len(set(ids)) and set(ids)==set(row['legal_mapping'])
                        assert len(set(row['legal_mapping'].values()))==len(ids)
                        assert resolve_action(row['chosen_action'],frozen_obs,row['legal_mapping'])==row['command']
                        for action in legal:
                            command=row['legal_mapping'][action['id']]
                            m=re.fullmatch(r'/choose (move|switch) ([1-6])\|(\d+)',command)
                            assert m and int(m[3])==obs['request_id']
                            assert m[1]==('switch' if action['kind']=='switch' else 'move')
                            if obs['request_kind']=='forced_switch':assert action['kind']=='switch'
                        action=next(a for a in legal if a['id']==row['chosen_action'])
                        expected=expected_engine_choice(row); ordinal=actions[index][1]
                        literal=expected==ordinal
                        if not literal and first is None:first=index
                        if label['commit_status']=='verified':verified+=1
                        else:unknown+=1
                        context=('forced_replacement' if obs['request_kind']=='forced_switch' else
                                 'engine' if action['kind']=='engine' else action['kind'])
                        if policy:
                            result=policy.act(frozen_obs)
                            assert json.loads(json.dumps(asdict(result)))==row['policy_evaluation']
                            assert result.chosen_action==row['chosen_action']
                            assert rng.random()==result.draw
                            assert tuple(ids)==result.legal_ids
                            p=result.probabilities; chosen=ids.index(row['chosen_action'])
                            assert strict_cdf(p,result.draw)==chosen
                            assert math.isfinite(math.log(p[chosen]))
                            cdf_ties+=int(result.draw in np.cumsum(p)[:-1])
                            totals[experiment+':replayed']+=1
                            contexts[(experiment,phase,context,label['commit_status'])]+=1
                        category=('verified_exact' if label['commit_status']=='verified' else
                                  'first_normalization_candidate' if first==index and ordinal in {'move wrap','move clamp','move fight'}
                                  and obs['maybe_locked'] and action['kind']=='move' else
                                  'unknown_suffix_literal' if literal else 'unknown_suffix_mismatch')
                        active=next(m for m in obs['own_team'] if m['active'])
                        row_details.append({'index':index,'decision_id':row['decision_id'],'request_id':obs['request_id'],
                            'turn':obs['turn'],'kind':context,'sampled':row['chosen_action'],'expected':expected,
                            'ordinal_engine_choice':ordinal,'engine_input_index':actions[index][0],
                            'category':category,'original_commit_status':label['commit_status'],
                            'original_unknown_reason':label['unknown_reason'],'original_execution':label['execution']['status'],
                            'maybe_locked':obs['maybe_locked'],'maybe_disabled':obs['maybe_disabled'],
                            'active_species':active['species'],'active_status':active['status'],
                            'legal_count':len(legal),'public_history_length':len(obs['public_history']),
                            'snapshot_sha256':row['snapshot_sha256'],
                            'sampled_probability':row['policy_evaluation']['probabilities'][ids.index(row['chosen_action'])] if policy else None})
                    if phase=='training' and side=='a':
                        key=f'{run_hash}:{match}'; target=all_targets[key]
                        reason=(battle['status'] if battle['status']!='completed' else
                                'unknown_commitment_episode' if unknown else None)
                        assert target['exclusion']==reason
                        assert target['decision_ids']==[r['decision_id'] for r in attempts]
                        assert target['checkpoint_sha256']==cps[side].sha256
                        assert target['reward']==(None if reason else {'a':1,'b':-1,'draw':0}[battle['winner']])
                        name=path.name; arm='original' if experiment=='reinforce-main' else name.split('-b')[0]
                        batch=int(re.search(r'(?:^|-)b(\d+)',name)[1])
                        opponent=name.split('-vs-')[1]
                        parent=json.loads((base/'batches'/f'{"" if arm=="original" else arm+"-"}b{batch}.json').read_text())
                        assert parent['parent_sha256']==cps[side].sha256
                        ep={'experiment':experiment,'arm':arm,'batch':batch,'opponent':opponent,
                            'opponent_group':opponent if opponent in ('v2','v5') else 'archive',
                            'run':str(path.relative_to(ROOT)),'run_sha256':run_hash,'match':match,'battle_key':key,
                            'team_a':assignments['a'],'team_b':assignments['b'],'challenger':challenger,
                            'status':battle['status'],'winner':battle['winner'],'exclusion':reason,
                            'decisions':len(attempts),'verified':verified,'unknown':unknown,
                            'first_mismatch_index':first,'first_expected':row_details[first]['expected'] if first is not None else None,
                            'first_ordinal':row_details[first]['ordinal_engine_choice'] if first is not None else None,
                            'maybe_locked_decisions':sum(r['maybe_locked'] for r in row_details),
                            'length_bin':'1-25' if len(attempts)<=25 else '26-50' if len(attempts)<=50 else '51-100' if len(attempts)<=100 else '101+',
                            'checkpoint_sha256':cps[side].sha256}
                        episode_rows.append(ep)
                        if reason:
                            for detail in row_details:
                                discrepancy_rows.append({**ep,**detail})
                            if first is not None and len(samples)<12:
                                r=attempts[first]; start=len(r['observation']['public_history'])
                                end=len(attempts[first+1]['observation']['public_history']) if first+1<len(attempts) else len(histories[side])
                                samples.append({'episode':ep,'record':r,'original_label':labels[r['decision_id']],
                                    'same_ordinal_engine_entry':actions[first],
                                    'public_before':r['observation']['public_history'][-10:],
                                    'public_after':histories[side][start:end]})
            peak=max(peak,psutil.Process().memory_info().rss)
            print(f'{experiment}/{path.parent.name}/{path.name}: replay/commitment audit passed',flush=True)
    csv_save('episodes.csv',episode_rows);csv_save('excluded-decisions.csv',discrepancy_rows)
    save('examples.json',samples)
    grouped={name:grouping(episode_rows,keys) for name,keys in {
        'arm':['experiment','arm'],'opponent':['experiment','arm','opponent_group'],
        'batch':['experiment','arm','batch','opponent'], 'team_pairing':['experiment','arm','team_a','team_b','challenger'],
        'outcome':['experiment','arm','winner'], 'length':['experiment','arm','length_bin'],
        'admission':['experiment','arm','exclusion']}.items()}
    save('exclusion-groups.json',grouped)
    save('summary.json',{'schema_version':'trajectory-contract-diagnostic-1','new_games':0,'training_updates':0,
        'totals':dict(totals),'training_episodes':len(episode_rows),
        'training_exclusions':dict(Counter(r['exclusion'] or 'admitted' for r in episode_rows)),
        'first_mismatch_normalizations':dict(Counter(r['first_ordinal'] for r in episode_rows if r['first_ordinal'])),
        'excluded_decision_categories':dict(Counter(r['category'] for r in discrepancy_rows)),
        'excluded_execution':dict(Counter(r['original_execution'] for r in discrepancy_rows)),
        'contexts':[{'experiment':k[0],'phase':k[1],'context':k[2],'commit_status':k[3],'n':v} for k,v in contexts.items()],
        'events':dict(all_events),'critical_events':critical_events,'cdf_exact_internal_boundary_draws':cdf_ties,
        'sampling_errors':0,'equal_sequence_lengths':True,'unique_ordered_request_ids':True,
        'one_send_completion_per_attempt':True,'original_label_audits_unchanged':True,
        'raw_request_reconstruction':'unavailable: sanitized snapshot/mapping retained, original request JSON not journaled',
        'checkpoint_loads':loaded,'v4_sha256':predictor.sha256,'v5_sha256':v5.sha256,
        'manifests':manifest_checks,'source_contract_modules_unchanged':source_checks,
        'showdown_commit':pin,'poke_env':versions['poke_env'],
        'seconds':time.monotonic()-started,'cpu_seconds':time.process_time()-cpu,'peak_observed_rss_bytes':peak})


if __name__=='__main__':
    run()
