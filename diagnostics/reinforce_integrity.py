"""Read-only retained experiment integrity. No server/collection command is called."""
import json
from pathlib import Path
import subprocess
import time
from battlemind.environment import ROOT, sha256, source_manifest
from battlemind.reinforce import load_checkpoint
from battlemind.reinforce_experiment import report_experiment, selection_score
from battlemind.labels import read_jsonl

started=time.monotonic();cpu=time.process_time()
output=ROOT/'runs/reinforce-audit-20260909';output.mkdir(exist_ok=False)
def write(name,value):
    with (output/name).open('x',encoding='utf-8') as stream:json.dump(value,stream,indent=2,allow_nan=False)
original=ROOT/'runs/reinforce-main'
tracked=subprocess.check_output(['git','ls-files'],text=True).splitlines()
baseline={name:sha256(ROOT/name) for name in tracked}
write('inputs-before.json',{'git_head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
    'tracked':baseline,'historical_control_files':{str(p.relative_to(ROOT)):sha256(p) for p in
    (original/'ledger.json',original/'summary.json',original/'artifact-hashes.json',ROOT/'runs/reinforce-smoke/artifact-hashes.json')},
    'plan_sha256':sha256(ROOT/'diagnostics/REINFORCE-AUDIT-PLAN.md')})
print('Full read-only decision/commitment/update audit...',flush=True)
report=report_experiment(original,True)
assert report['audit']['ok'],report['audit']
ledger=json.loads((original/'ledger.json').read_text())
assert ledger==report['ledger']
freeze=json.loads((original/'freeze.json').read_text())
assert source_manifest()==freeze['source']
assert sha256(ROOT/freeze['configuration']['document'])==freeze['document_sha256']
assert sha256(ROOT/'configs/reinforce-main.json')==freeze['spec_sha256']
for name,digest in freeze['source'].items():assert sha256(original/'source-snapshot'/name)==digest
checkpoints={str(i):load_checkpoint(original/f'checkpoints/c{i}.json').sha256 for i in range(13)}
assert load_checkpoint(original/'selected.json').sha256==checkpoints['6']
partition_keys={};selection_rows={0:[],6:[],12:[]};terminal_checks=0
for record in ledger['runs']:
    path=original/record['path'];rows=read_jsonl(path/'battles.jsonl');meta=json.loads((path/'run.json').read_text())
    assert sha256(path/'run.json')==record['run_id']
    assert meta['reinforce_checkpoints']['a']['sha256']==record['candidate_sha256']
    assert sha256(original/record['candidate'])==record['candidate_sha256']
    if record['phase']=='selection':selection_rows[int(Path(record['candidate']).stem[1:])]+=rows
    for row in rows:
        key=f"{record['run_id']}:{row['match']}";assert key not in partition_keys
        partition_keys[key]=record['phase']
        if row['status']=='completed':
            expected={'a':{'a':'win','b':'loss'},'b':{'a':'loss','b':'win'},'draw':{'a':'draw','b':'draw'}}[row['winner']]
            assert row['terminal_results']==expected
            for side in ('a','b'):
                reward=0 if row['winner']=='draw' else 1 if row['winner']==side else -1
                assert reward=={'win':1,'loss':-1,'draw':0}[row['terminal_results'][side]]
                terminal_checks+=1
        else:assert row['winner'] is None
assert partition_keys==ledger['battle_partitions']
smoke=ROOT/'runs/reinforce-smoke'
for name,digest in json.loads((smoke/'artifact-hashes.json').read_text()).items():assert sha256(smoke/name)==digest
assert not set(partition_keys)&json.loads((smoke/'ledger.json').read_text())['battle_partitions'].keys()
scores={n:selection_score(rows) for n,rows in selection_rows.items()}
assert max(scores,key=lambda n:(*scores[n],-n))==report['selection']['chosen']==6
write('integrity.json',{'ok':True,'new_battles':0,'saved_checkpoint_updates':0,'audit':report['audit'],
    'historical_source_matches_current':True,'historical_source_path':'runs/reinforce-main/source-snapshot',
    'artifact_hash_entries':len(json.loads((original/'artifact-hashes.json').read_text())),
    'checkpoint_hashes':checkpoints,'freeze_sha256':sha256(original/'freeze.json'),
    'configuration_sha256':freeze['spec_sha256'],'specification_sha256':freeze['document_sha256'],
    'terminal_perspective_checks':terminal_checks,'phase_identities':len(partition_keys),'selection_scores':scores,
    'smoke_overlap':0,'seconds':time.monotonic()-started,'cpu_seconds':time.process_time()-cpu})
print(json.dumps(json.loads((output/'integrity.json').read_text()),indent=2))
