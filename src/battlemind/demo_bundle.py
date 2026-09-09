"""Safe local artifact closure; historical loaders and scientific code stay unchanged."""

import json
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import zipfile

from .adaptation_experiment import artifacts
from .environment import ROOT, sha256
from .labels import read_jsonl
from .memory_audit import replay_cell
from .opponent_memory import ObserverMemory
from .viewer_records import historical_replay, explanation, validate_replay

MAX_BYTES = 64 * 1024 * 1024
VERSION = 'v7-demo-bundle-1'


def write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def safe_path(root: Path, name: str) -> Path:
    p = PurePosixPath(name)
    if (not name or '\\' in name or ':' in name or p.is_absolute() or '..' in p.parts
        or p.as_posix() != name or any(x.startswith('.') and x not in {'.babelrc','.gitindex'} for x in p.parts)):
        raise ValueError('Unsafe artifact path')
    result = root.joinpath(*p.parts)
    if not result.resolve().is_relative_to(root.resolve()):
        raise ValueError('Artifact escapes root')
    return result


def check_assets(path: Path) -> dict:
    pin = json.loads((ROOT/'configs/viewer-assets.json').read_text())
    for name, expected in pin['files'].items():
        p = safe_path(path, name)
        if not p.is_file() or sha256(p) != expected:
            raise ValueError(f'Missing/changed viewer asset: {name}; run scripts/setup-viewer.py')
    return pin


def prepare(destination: Path) -> dict:
    """Only preselected retained examples. Never reads an engine end log or trains."""
    artifacts()
    asset_pin = check_assets(ROOT/'.local/viewer-assets')
    destination.mkdir(parents=True, exist_ok=False)
    for source, target in ((ROOT/'models/v4-supervised.json','predictor.json'),
                           (ROOT/'runs/v5-acceptance/selected.json','checkpoint.json')):
        shutil.copyfile(source,destination/target)
    examples = [
        ('normal','V2 heuristic vs MaxBasePower — ordinary recorded game','runs/m2-comparison-max-base-power',0),
        ('choice-change','V5 changed a scored choice — illustration, not a counterfactual win','runs/v5-acceptance/final/selected-vs-random',0),
        ('freeze-cap','V6 limitation: frozen actives, 300-turn cap; cleanup is not a win','runs/v6-acceptance-repair/final/g1/none-p4-vs-switch-active',2)]
    ids = []
    for ident,title,source,match in examples:
        replay = historical_replay(ROOT/source,match,ident,title)
        if ident == 'choice-change':
            row = next(r for r in read_jsonl(ROOT/source/'decisions.jsonl') if r['decision_id']=='m0:a:r2')
            replay['explanations'] = [explanation(row)]
        write(destination/f'replays/{ident}.json', replay); ids.append(ident)
    # A closed four-encounter prefix starting from empty individual memory.
    source = ROOT/'runs/v6-acceptance-repair/development/g0/individual-p0-vs-max-base-power'
    target = destination/'memory-trace'
    target.mkdir()
    metadata = json.loads((source/'run.json').read_text())
    minimal = {k:metadata[k] for k in ('adaptation','predictor','policy_checkpoints')}
    minimal['predictor'] = {'sha256':minimal['predictor']['sha256']}
    minimal['policy_checkpoints'] = {'a':{'sha256':minimal['policy_checkpoints']['a']['sha256']}}
    minimal['config'] = {'battles':4}
    write(target/'run.json', minimal)
    for match in range(4):
        for name in (f'observer/{match:03d}.json',f'memory/{match:03d}-before.json',
                     f'memory/{match:03d}-after.json',f'privileged/attempts/{match:03d}-a.jsonl'):
            p=target/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/name,p)
        ident=f'memory-{match}'
        replay=historical_replay(source,match,ident,f'V6 chronological encounter {match+1}/4 — memory starts empty')
        rows=read_jsonl(source/f'privileged/attempts/{match:03d}-a.jsonl')
        replay['explanations']=[explanation(rows[0])]
        replay['provenance']['memory_before_sha256']=sha256(source/f'memory/{match:03d}-before.json')
        replay['provenance']['memory_after_sha256']=sha256(source/f'memory/{match:03d}-after.json')
        write(destination/f'replays/{ident}.json',replay);ids.append(ident)
    shutil.copytree(ROOT/'.local/viewer-assets', destination/'assets')
    files={p.relative_to(destination).as_posix():sha256(p) for p in sorted(destination.rglob('*')) if p.is_file()}
    manifest={'schema_version':VERSION,'files':files,'replays':ids,
        'predictor_sha256':sha256(destination/'predictor.json'),'checkpoint_sha256':sha256(destination/'checkpoint.json'),
        'assets_pin_sha256':sha256(ROOT/'configs/viewer-assets.json'),
        'source_provenance':{'memory_run_sha256':sha256(source/'run.json'),
                             'historical_status_sha256':sha256(ROOT/'docs/MILESTONE6-REPAIR.md')},
        'runtime_requirement':'Pinned Python/Node/poke-env and source scoring compatibility; no training',
        'memory_trace':'Observer-owned snapshots/public events plus its own audit journal; offline only, never an HTTP endpoint',
        'randomness':'Frozen snapshot replay is reproducible; simulator trajectories are not controlled',
        'download_bytes':asset_pin['download_bytes']}
    write(destination/'manifest.json', manifest)
    return verify(destination)


def verify(root: Path) -> dict:
    manifest=json.loads((root/'manifest.json').read_text())
    if manifest.get('schema_version') != VERSION:
        raise ValueError('Unsupported demo bundle')
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p != root/'manifest.json'}
    pin=json.loads((ROOT/'configs/viewer-assets.json').read_text())
    allowed={'assets/'+name for name in pin['files']} | {'predictor.json','checkpoint.json','memory-trace/run.json'}
    allowed.update(f'replays/{i}.json' for i in manifest['replays'])
    for m in range(4):
        allowed.update('memory-trace/'+n for n in (f'observer/{m:03d}.json',f'memory/{m:03d}-before.json',f'memory/{m:03d}-after.json',f'privileged/attempts/{m:03d}-a.jsonl'))
    if actual != allowed:
        raise ValueError('Bundle contains files outside the minimal artifact closure')
    if actual != set(manifest['files']):
        raise ValueError('Bundle contains missing or unlisted files')
    total=0
    for name,expected in manifest['files'].items():
        path=safe_path(root,name);total+=path.stat().st_size
        if total>MAX_BYTES or sha256(path)!=expected:
            raise ValueError(f'Bundle size/hash mismatch: {name}')
    if manifest['assets_pin_sha256'] != sha256(ROOT/'configs/viewer-assets.json'):
        raise ValueError('Incompatible renderer pin')
    check_assets(root/'assets')
    bundle,checkpoint=artifacts(root/'predictor.json',root/'checkpoint.json')
    if (manifest['predictor_sha256'],manifest['checkpoint_sha256']) != (bundle.sha256,checkpoint.sha256):
        raise ValueError('Manifest/model disagreement')
    for ident in manifest['replays']:
        validate_replay(json.loads(safe_path(root,f'replays/{ident}.json').read_text()))
    replay=replay_cell(root/'memory-trace',ObserverMemory(),bundle,checkpoint)
    return {'ok':True,'schema_version':VERSION,'manifest_sha256':sha256(root/'manifest.json'),
        'bytes':total,'files':len(actual),'replays':len(manifest['replays']),
        'predictor_sha256':bundle.sha256,'checkpoint_sha256':checkpoint.sha256,
        'public_memory_encounters_replayed':len(replay['updates']),
        'observer_decisions_replayed':len(replay['decisions']),
        'changed_probability_decisions':sum(r['probabilities']['individual']!=r['probabilities']['none'] for r in replay['decisions'])}


def export_bundle(source: Path, output: Path) -> dict:
    result=verify(source)
    with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob('*')):
            if path.is_file(): archive.write(path,path.relative_to(source).as_posix())
    return {**result,'archive_sha256':sha256(output),'archive_bytes':output.stat().st_size}


def import_bundle(source: Path, output: Path) -> dict:
    if output.exists(): raise ValueError('Import destination exists; no overwrite')
    # Validate in isolation before admitting anything into the destination.
    with tempfile.TemporaryDirectory(prefix='battlemind-v7-') as temp:
        root=Path(temp)
        with zipfile.ZipFile(source) as archive:
            members=archive.infolist()
            if len(members)>500 or sum(m.file_size for m in members)>MAX_BYTES:
                raise ValueError('Oversized bundle')
            if len({m.filename for m in members})!=len(members): raise ValueError('Duplicate archive members')
            for m in members:
                path=safe_path(root,m.filename)
                if m.is_dir() or (m.external_attr>>16)&0o170000==0o120000: raise ValueError('Directories/symlinks not supported')
                path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(archive.read(m))
        result=verify(root)
        output.parent.mkdir(parents=True,exist_ok=True)
        shutil.copytree(root,output)
    return {**result,'output':str(output)}
