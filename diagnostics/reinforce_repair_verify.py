"""Offline repair verification; originals are read-only and no games are started.

Recompute recorded updates, never fit a new policy or save an updated checkpoint.
Use -B for frozen-source replay so even bytecode stays out of historical inputs.
"""
import ast
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT/'runs/reinforce-main'
OUT = ROOT/'runs/reinforce-repair-20260909'
sys.dont_write_bytecode = True

if '--historical-audit' in sys.argv:
    sys.path.insert(0, str(RUN/'source-snapshot/src'))
    from battlemind.environment import ROOT as HISTORICAL_ROOT, source_manifest
    from battlemind.reinforce_experiment import report_experiment
    assert HISTORICAL_ROOT == RUN/'source-snapshot'
    assert source_manifest() == json.loads((RUN/'freeze.json').read_text())['source']
    start=time.monotonic();cpu=time.process_time()
    result=report_experiment(RUN, audit=True)
    assert result['audit']['ok'],result['audit']
    with (OUT/'historical-source-audit.json').open('x') as f:
        json.dump({'source_root':str(HISTORICAL_ROOT),'audit':result['audit'],
                   'seconds':time.monotonic()-start,'cpu_seconds':time.process_time()-cpu},f,indent=2)
    print('Exact frozen-source full audit passed:',result['audit'],flush=True)
    raise SystemExit(0)

from battlemind.environment import sha256
from battlemind.adaptation_experiment import artifacts
from battlemind.reinforce import load_checkpoint
from battlemind.reinforce_experiment import build_report, report_experiment

start=time.monotonic();cpu=time.process_time()
target=OUT/'corrected-report';target.mkdir(exist_ok=False)
before=json.loads((OUT/'inputs-before.json').read_text())
changed={'src/battlemind/reinforce.py','src/battlemind/reinforce_experiment.py'}
for name,digest in before['hashes'].items():
    if name not in changed:assert sha256(ROOT/name)==digest,name

# The only changed original definitions are load_checkpoint and build_report.
unchanged_definitions={}
for name,allowed in (('reinforce.py',{'load_checkpoint'}),('reinforce_experiment.py',{'build_report'})):
    old=ast.parse((RUN/'source-snapshot/src/battlemind'/name).read_text())
    new=ast.parse((ROOT/'src/battlemind'/name).read_text())
    def definitions(tree):
        return {node.name:ast.dump(node,include_attributes=False) for node in tree.body
                if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))}
    old,new=definitions(old),definitions(new)
    for key,value in old.items():
        if key not in allowed:assert new[key]==value,(name,key)
    unchanged_definitions[name]=sorted(set(old)-allowed)
assert sha256(ROOT/'src/battlemind/reinforce_training.py')==before['hashes']['src/battlemind/reinforce_training.py']
profile=json.loads((ROOT/'configs/reinforce-loader-compatibility.json').read_text())
assert profile['repaired_reinforce_sha256']==sha256(ROOT/'src/battlemind/reinforce.py')
assert profile['original_checkpoint_compatibility']==json.loads((RUN/'checkpoints/c0.json').read_text())['compatibility']

models={}
for p in [*sorted((RUN/'checkpoints').glob('*.json')),RUN/'selected.json',
          *sorted((ROOT/'runs/reinforce-smoke/checkpoints').glob('*.json')),ROOT/'runs/reinforce-smoke/selected.json']:
    models[p.relative_to(ROOT).as_posix()]=load_checkpoint(p).sha256
predictor,v5=artifacts()

print('Current-source replay: every recorded learned decision and all 12 updates...',flush=True)
current=report_experiment(RUN,audit=True)
assert current['audit']['errors']==['Experiment full source no longer matches; historical source needed for full audit'],current['audit']
assert current['audit']['replayed_decisions']==83170
with (OUT/'current-source-replay.json').open('x') as f:
    json.dump({'audit':current['audit'],'interpretation':'Semantic replay and update reconstruction passed; full-source equality intentionally fails after repair.'},f,indent=2)

print('Rebuilding the report into a fresh output, reading original run paths...',flush=True)
(target/'checkpoints').mkdir()
shutil.copyfile(RUN/'checkpoints/c0.json',target/'checkpoints/c0.json')
shutil.copyfile(RUN/'selected.json',target/'selected.json')
ledger=json.loads((RUN/'ledger.json').read_text())
# build_report writes its new comparison output under target. Absolute input paths
# point only to retained read-only cells; their records and snapshots stay intact.
for record in ledger['runs']:record['path']=str((RUN/record['path']).resolve())
config=json.loads((RUN/'specification.json').read_text())
corrected=build_report(target,ledger,config)
old_report=json.loads((RUN/'report.json').read_text())
assert corrected==old_report
assert sha256(target/'decision-differences.jsonl')==sha256(RUN/'decision-differences.jsonl')
with (target/'report.json').open('x') as f:json.dump(corrected,f,indent=2)
for _ in range(2):assert report_experiment(RUN)['report']==corrected

print('Checking the explicit original-source replay command (no hash overrides)...',flush=True)
with (OUT/'historical-source-console.txt').open('x') as f:
    subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--historical-audit'],
                   cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=300)

for name,digest in before['hashes'].items():
    if name not in changed:assert sha256(ROOT/name)==digest,name
extras=[]
for folder in ('reinforce-main','reinforce-smoke','reinforce-audit-20260909'):
    extras += [p.relative_to(ROOT).as_posix() for p in (ROOT/'runs'/folder).rglob('*')
               if p.is_file() and p.relative_to(ROOT).as_posix() not in before['hashes']]
assert not extras,extras
report={'ok':True,'new_battles':0,'new_training':False,'saved_model_updates':0,
    'retained_checkpoints_loaded':models,'v4_sha256':predictor.sha256,'v5_sha256':v5.sha256,
    'snapshot_set':'Every REINFORCE player decision in every recorded main cell: both players, all phases, chronological per-match draws (83,170).',
    'replayed_decisions':83170,'updates_reconstructed_unchanged':12,
    'unchanged_ast_definitions':unchanged_definitions,'training_module_unchanged':True,
    'current_full_source_status':'Expected mismatch; check not bypassed',
    'historical_full_source_audit':json.loads((OUT/'historical-source-audit.json').read_text()),
    'corrected_report_equals_historical_values':True,'corrected_comparison_bytes_equal':True,
    'same_snapshot_comparisons':corrected['same_snapshot'],'read_only_report_repeats':2,
    'original_files_unchanged_except_authorized_source_edits':len(before['hashes'])-len(changed),
    'new_files_in_historical_directories':extras,'compatibility_profile_sha256':sha256(ROOT/'configs/reinforce-loader-compatibility.json'),
    'new_source_sha256':{name:sha256(ROOT/name) for name in sorted(changed)},
    'wall_seconds':time.monotonic()-start,'cpu_seconds_current_process':time.process_time()-cpu}
with (OUT/'verification.json').open('x') as f:json.dump(report,f,indent=2)
print(json.dumps(report,indent=2),flush=True)
