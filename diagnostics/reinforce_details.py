"""Additional read-only tie, cap and table diagnostics; no learning or games."""
from collections import Counter
import csv
import json
import time
import numpy as np
from battlemind.environment import ROOT, sha256
from battlemind.labels import read_jsonl
from battlemind.schema import snapshot_from_dict
from battlemind.reinforce import features, load_checkpoint
from battlemind.heuristic import Gen1HeuristicAgent

start=time.monotonic();cpu=time.process_time()
out=ROOT/'runs/reinforce-audit-20260909/diagnosis'
run=ROOT/'runs/reinforce-main'
ledger=json.loads((run/'ledger.json').read_text())
cp=load_checkpoint(run/'selected.json');w=np.asarray(cp.parameters.actor)
greedy=Counter();initial_gaps=[];recovery=Counter();bad_status=Counter()
for record in ledger['runs']:
    if record['phase']!='final':continue
    for row in read_jsonl(run/record['path']/'decisions.jsonl'):
        if row['player']!='a':continue
        obs=snapshot_from_dict(row['observation']);s,x,prior=features(obs)
        z=prior+x@w.T@s;i=int(np.argmax(prior));j=int(np.argmax(z))
        if i!=j:
            greedy['changed']+=1
            greedy['initial_tie' if prior[i]==prior[j] else 'initial_strict_order']+=1
            initial_gaps.append(float(prior[i]-prior[j]))
        own=next(m for m in obs.own_team if m.active)
        chosen=next(a for a in obs.legal_actions if a.id==row['chosen_action'])
        if chosen.move_id in ('recover','softboiled'):
            recovery['selected']+=1
            if own.health.maximum and own.health.current==own.health.maximum:recovery['full_hp_selected']+=1
        foe=next((m for m in obs.opponent_revealed if m.active),None)
        if chosen.move_id in ('thunderwave','stunspore','sleeppowder','hypnosis','lovelykiss'):
            bad_status['selected']+=1
            if foe and foe.status not in ('healthy','fnt'):bad_status['target_already_statused']+=1

ex=json.loads((out/'exclusions.json').read_text())
cap=next(e for e in ex['episodes'] if e['exclusion']=='truncated')
path=run/cap['run'];rows=[r for r in read_jsonl(path/'decisions.jsonl') if r['player']=='a' and r['match']==cap['match']]
cap_states=[]
for row in (rows[0],rows[20],rows[-1]):
    obs=row['observation']
    cap_states.append({'decision_id':row['decision_id'],'turn':obs['turn'],
        'own_active':next(m for m in obs['own_team'] if m['active']),
        'foe_active':next((m for m in obs['opponent_revealed'] if m['active']),None),
        'legal_actions':obs['legal_actions'],'choice':row['chosen_action'],
        'public_history_tail':obs['public_history'][-8:]})
cap_summary={'run':cap['run'],'battle_key':cap['battle_key'],
    'engine_singleton_requests':sum(len(r['observation']['legal_actions'])==1 and r['chosen_action'].startswith('engine:') for r in rows),
    'raw_observer_states':cap_states,'outcome':None,'cap_status_preserved':True}
with (out/'additional.json').open('x',encoding='utf-8') as f:
    json.dump({'greedy_change':dict(greedy),'changed_initial_gap_mean':float(np.mean(initial_gaps)),
        'changed_initial_gap_max':max(initial_gaps),'selected_recovery_diagnostics':dict(recovery),
        'selected_status_diagnostics':dict(bad_status),'cap':cap_summary,
        'wall_seconds':time.monotonic()-start,'cpu_seconds':time.process_time()-cpu,
        'script_sha256':sha256(ROOT/'diagnostics/reinforce_details.py')},f,indent=2,allow_nan=False)

episodes=list(csv.DictReader((out/'training-episodes.csv').open(newline='',encoding='utf-8')))
updates=json.loads((out/'updates.json').read_text());credit=json.loads((out/'credit.json').read_text())
cases=json.loads((out/'cases.json').read_text());reference=json.loads((out/'reference.json').read_text())
lines=['# Retained REINFORCE audit — detailed tables','',
       'Diagnostic data only. No new games, historical fitting or artifact edits.', '',
       '## Training batches','',
       'Outcomes below are admitted episodes only. Unknown-commitment completed outcomes remain separately listed in exclusions.json.', '',
       '| Batch | Opponents | Admitted W/L/D | Unknown/cap | Actor gradient norm | Actor delta | Value explained variance |',
       '|---|---|---|---|---|---|---|']
for u in updates:
    b=u['batch'];es=[e for e in episodes if int(e['batch'])==b];ad=[e for e in es if e['exclusion']=='admitted']
    counts=Counter(e['training_reward'] for e in ad);reasons=Counter(e['exclusion'] for e in es)
    lines.append(f"| {b} | {', '.join(u['opponent_pool'])} | {counts['1']}/{counts['-1']}/{counts['0']} | {reasons['unknown_commitment_episode']}/{reasons['truncated']} | {u['actor_gradient_norm']:.6f} | {u['actor_delta_norm']:.6f} | {credit['by_batch'][str(b)]['explained_variance']:.6f} |")
lines+=['','## Initial versus V2','',
    'Conditional on request type or on V2 choosing that category. Same stored random draw, both generating arms together. No performance inference from agreement.', '',
    '| Group | Snapshots | Mean P(initial chooses V2 choice) | Initial sampled agreement | c6 sampled agreement |',
    '|---|---|---|---|---|']
for name,metrics in reference.items():
    if name not in ('all','ordinary','forced','engine_singleton','engine_with_alternatives') and not name.startswith('v2_choice:'):continue
    lines.append(f"| {name} | {metrics['p0_of_v2_choice']['n']} | {metrics['p0_of_v2_choice']['mean']:.4f} | {metrics['initial_sample_matches_v2']['mean']:.4f} | {metrics['selected_sample_matches_v2']['mean']:.4f} |")
lines+=['','## Representative decisions','',
    'First occurrences under the plan, not selected for impressive outcomes. Full snapshots, all action scores/probabilities, same-input V5 scores, draws and the next observer-public window are in cases.json. No hidden opposing information was used.', '']
for name,case in cases.items():
    obs=case['observation'];own=next(m for m in obs['own_team'] if m['active']);foe=next((m for m in obs['opponent_revealed'] if m['active']),None)
    lines += [f'### {name}', '', f"`{case['run']}` · `{case['decision_id']}` · turn {obs['turn']} · eventual winner {case['terminal_winner']} (a is the learner).", '',
        f"Visible own {own['species']}: {own['health']}, {own['status']}. Visible opponent: {foe}. Own effective stats remain unknown; unseen opposing moves remain unknown.", '',
        f"Common draw {case['draw']:.12f}: c0 {case['c0_same_draw']}; c6 {case['c6_same_draw']}. V2 chooses {case['v2_choice']}; V5 chooses {case['v5_choice']}.", '',
        '| Action | V2 score | Initial logit | c6 logit | P(c0) | P(c6) |','|---|---|---|---|---|---|']
    for a in case['actions']:
        lines.append(f"| {a['id']} | {a['v2_score']:.3f} | {a['initial_logit']:.5f} | {a['c6_logit']:.5f} | {a['p0']:.6f} | {a['p6']:.6f} |")
    lines+=['', 'Observed afterward: `'+json.dumps(case['after_public_events'])+'`.', '']
with (out/'details.md').open('x',encoding='utf-8') as f:f.write('\n'.join(lines)+'\n')
print(json.dumps({'greedy':dict(greedy),'recovery':dict(recovery),'status':dict(bad_status),
                  'cap_singleton_requests':cap_summary['engine_singleton_requests'],
                  'cap_last_state':cap_states[-1]},indent=2))
