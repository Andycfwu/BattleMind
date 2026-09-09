"""Explicit, hash-pinned download/build of the small offline renderer closure.

First developer freeze uses --freeze. Normal setup verifies configs/viewer-assets.json.
No model, dataset, audio, full client or full sprite archive is downloaded.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
COMMIT = 'afa9d4ae645923e42fc8f587080c6bf3d13de2fc'
SRC = ROOT / '.local/v7-client-source'
DEST = ROOT / '.local/viewer-assets'
PIN = ROOT / 'configs/viewer-assets.json'


def fetch(url, path, entries, expected):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = path.read_bytes() if path.exists() else urllib.request.urlopen(
        urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=30).read()
    digest = hashlib.sha256(data).hexdigest()
    key = path.relative_to(ROOT / '.local').as_posix()
    if expected is not None and expected.get(key, {}).get('sha256') != digest:
        raise ValueError(f'Asset changed or not pinned: {key}')
    path.write_bytes(data)
    entries[key] = {'url': url, 'sha256': digest, 'bytes': len(data)}


def main():
    args = argparse.ArgumentParser()
    args.add_argument('--freeze', action='store_true')
    opt = args.parse_args()
    if opt.freeze and PIN.exists():
        raise ValueError('Refuse to overwrite an asset freeze')
    expected = None if opt.freeze else json.loads(PIN.read_text())['downloads']
    entries = {}
    source_files = ['LICENSE','README.md','.babelrc']
    names = ['battle','battle-dex','battle-dex-data','battle-log','battle-text-parser','battle-tooltips','battle-animations','battle-animations-moves','battle-sound','battle-scene-stub','battle-teams']
    source_files += ['play.pokemonshowdown.com/src/'+n+'.ts' for n in names]
    source_files += ['play.pokemonshowdown.com/src/battle-log-misc.js']
    source_files += ['play.pokemonshowdown.com/js/lib/'+n for n in ['jquery-2.2.4.min.js','html-sanitizer-minified.js']]
    source_files += ['play.pokemonshowdown.com/style/'+n for n in ['battle.css','battle-log.css']]
    base = f'https://raw.githubusercontent.com/smogon/pokemon-showdown-client/{COMMIT}/'
    for p in source_files:
        fetch(base+p, SRC/p, entries, expected)
    DEST.mkdir(parents=True, exist_ok=True)
    for name in ['jquery-2.2.4.min.js','html-sanitizer-minified.js']:
        shutil.copyfile(SRC/'play.pokemonshowdown.com/js/lib'/name, DEST/name)
    css = (SRC/'play.pokemonshowdown.com/style/battle.css').read_text()
    # Route CSS resource paths locally; deny external URLs with CSP as well.
    css = re.sub(r'https?://play\.pokemonshowdown\.com/', '/assets/', css)
    (DEST/'battle.css').write_text(css.replace('../fx/', '/assets/fx/'))
    (DEST/'battle-log.css').write_bytes((SRC/'play.pokemonshowdown.com/style/battle-log.css').read_bytes())
    subprocess.run(['node', str(ROOT/'scripts/build-viewer.cjs'), str(DEST)], check=True)
    anim = (SRC/'play.pokemonshowdown.com/src/battle-animations.ts').read_text()
    effects = set(re.findall(r"url: '([^']+)'", anim))
    effects |= {'bg-gen1.png','bg-gen1-spl.png','bg.png','weather-sunnyday.jpg','weather-raindance.jpg','bg-space.jpg'}
    for name in sorted(effects):
        if '/' in name or ':' in name: continue
        fetch(base+'play.pokemonshowdown.com/fx/'+name, DEST/'fx'/name, entries, expected)
    species = set()
    for team in (ROOT/'configs/teams').glob('*.txt'):
        for block in team.read_text().strip().split('\n\n'):
            species.add(re.sub('[^a-z0-9]', '', block.splitlines()[0].lower()))
    sprite_paths = [f'sprites/{d}/{s}.png' for s in sorted(species|{'substitute'}) for d in ('gen1','gen1-back')]
    sprite_paths += ['sprites/ani/substitute.gif','sprites/ani-back/substitute.gif','sprites/trainers/unknown.png','sprites/trainers/unknown-flipped.png','sprites/gen6bgs/bg-beach.jpg','sprites/pokemonicons-sheet.png','sprites/pokemonicons-pokeball-sheet.png']
    for p in sprite_paths:
        fetch('https://play.pokemonshowdown.com/'+p, DEST/p, entries, expected)
    notices = DEST/'licenses';notices.mkdir(exist_ok=True)
    shutil.copyfile(SRC/'LICENSE',notices/'showdown-client-AGPL.txt')
    shutil.copyfile(ROOT/'.local/pokemon-showdown/LICENSE',notices/'showdown-engine-MIT.txt')
    (notices/'README.txt').write_text('Official battle-*.ts renderer headers license the battle renderer MIT; full client LICENSE retained as context. Source headers/attributions accompany this bundle under source/. jQuery MIT and Caja sanitizer notices are in their files. Pokemon names/artwork belong to their respective owners (Nintendo/Game Freak/Creatures); BattleMind claims no artwork ownership. Only local demonstration; no upload.\n')
    # Keep corresponding source, including MIT headers and effect artist attribution.
    shutil.copytree(SRC, DEST/'source', dirs_exist_ok=True)
    record = {'schema_version':'v7-assets-1','client_commit':COMMIT,'downloads':entries,
              'download_bytes':sum(x['bytes'] for x in entries.values()),
              'files':{p.relative_to(DEST).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(DEST.rglob('*')) if p.is_file()}}
    if opt.freeze:
        PIN.write_text(json.dumps(record,indent=2)+'\n')
    elif record != json.loads(PIN.read_text()):
        raise ValueError('Built viewer assets differ from the frozen closure')
    print(json.dumps({'download_bytes':record['download_bytes'],'files':len(record['files']),'output':str(DEST)}))


if __name__ == '__main__': main()
