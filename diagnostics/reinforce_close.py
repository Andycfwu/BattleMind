"""Close this standalone audit by verifying retained bytes, without changing them."""
import json
from pathlib import Path
import subprocess
import time
import psutil
from battlemind.environment import ROOT, sha256, source_manifest
from battlemind.adaptation_experiment import artifacts

start=time.monotonic();cpu=time.process_time()
out=ROOT/'runs/reinforce-audit-20260909'
before=json.loads((out/'inputs-before.json').read_text())
assert subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()==before['git_head']
for name,digest in before['tracked'].items():assert sha256(ROOT/name)==digest,name
for name,digest in before['historical_control_files'].items():assert sha256(ROOT/name)==digest,name
manifest_counts={}
for folder in ('reinforce-main','reinforce-smoke'):
    path=ROOT/'runs'/folder
    manifest=json.loads((path/'artifact-hashes.json').read_text())
    for name,digest in manifest.items():assert sha256(path/name)==digest,name
    manifest_counts[folder]=len(manifest)
assert source_manifest()==json.loads((ROOT/'runs/reinforce-main/freeze.json').read_text())['source']
predictor,v5=artifacts()
v7=ROOT/'runs/v7-release-bundle'
old=json.loads((ROOT/'runs/reinforce-verification/closure.json').read_text())
assert sha256(v7/'manifest.json')==old['v7_bundle_verification']['manifest_sha256']
for name,digest in json.loads((v7/'manifest.json').read_text())['files'].items():assert sha256(v7/name)==digest
assert sha256(ROOT/'runs/v7-release-bundle.zip')==old['v7_zip_sha256']
listeners=[{'address':c.laddr.ip,'port':c.laddr.port,'pid':c.pid} for c in psutil.net_connections(kind='tcp')
           if c.status=='LISTEN' and c.laddr.port in (8000,8765)]
servers=[]
for p in psutil.process_iter(['pid','name','cmdline']):
    try:
        if (p.info['name'] or '').lower() in ('node.exe','node') and any('pokemon-showdown' in a.lower() for a in (p.info['cmdline'] or [])):
            servers.append(p.info['pid'])
    except (psutil.NoSuchProcess,psutil.AccessDenied):pass
assert not listeners and not servers
unit=(ROOT/'.local/reinforce-audit-unit-tests.log').read_text()
assert '179 passed, 14 deselected' in unit
subprocess.run(['git','diff','--check'],check=True)
# Retain console evidence in the new ignored audit directory, not old runs.
for source,target in (
    ('.local/reinforce-audit-unit-tests.log','unit-tests.txt'),
    ('.local/reinforce-diagnostic-integrity.log','integrity-console.txt'),
    ('.local/reinforce-diagnostic-synthetic.log','synthetic-console.txt'),
    ('.local/reinforce-diagnostic-analysis.log','analysis-console.txt'),
    ('.local/reinforce-diagnostic-details.log','details-console.txt')):
    with (out/target).open('xb') as f:f.write((ROOT/source).read_bytes())
files=[p for p in out.rglob('*') if p.is_file()]
report={'ok':True,'new_games':0,'production_edits':0,'historical_files_changed':0,
    'original_tracked_files_verified':len(before['tracked']),'historical_manifest_entries':manifest_counts,
    'main_source_matches_freeze':True,'git_head':before['git_head'],'v4_sha256':predictor.sha256,'v5_sha256':v5.sha256,
    'v7_manifest_and_zip_unchanged':True,'listeners':listeners,'showdown_processes':servers,
    'diagnostic_files_before_closure':len(files),'diagnostic_bytes_before_closure':sum(p.stat().st_size for p in files),
    'unit_result':unit.strip().splitlines()[-1],
    'new_source_files':subprocess.check_output(['git','status','--short'],text=True).strip().splitlines(),
    'wall_seconds':time.monotonic()-start,'cpu_seconds':time.process_time()-cpu,
    'inspected_official_source_hashes':{name:sha256(ROOT/'.local/pokemon-showdown'/name) for name in
        ('sim/side.ts','data/mods/gen1/conditions.ts','data/moves.ts','data/mods/gen5/moves.ts')}}
with (out/'closure.json').open('x',encoding='utf-8') as f:json.dump(report,f,indent=2,allow_nan=False)
hashes={str(p.relative_to(ROOT)).replace('\\','/'):sha256(p) for p in out.rglob('*') if p.is_file()}
for p in [*ROOT.glob('diagnostics/*.py'),ROOT/'diagnostics/REINFORCE-AUDIT-PLAN.md',ROOT/'docs/REINFORCE-AUDIT.md']:
    hashes[p.relative_to(ROOT).as_posix()]=sha256(p)
with (out/'audit-hashes.json').open('x',encoding='utf-8') as f:json.dump(hashes,f,indent=2)
print(json.dumps(report,indent=2))
