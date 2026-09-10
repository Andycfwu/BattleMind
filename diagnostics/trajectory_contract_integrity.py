"""Read-only input inventory for the retained trajectory audit. No game APIs."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'runs/trajectory-contract-audit-20260910'
TREES = ('src', 'configs', 'scripts', 'tests', 'docs', 'diagnostics', 'models',
         'runs/reinforce-main', 'runs/actor-step-acceptance',
         'runs/reinforce-audit-20260909', 'runs/reinforce-repair-20260909',
         'runs/actor-step-verification', 'runs/v5-acceptance')
DEPENDENCIES = ('.venv/Lib/site-packages/poke_env/player/player.py',
    '.venv/Lib/site-packages/poke_env/player/battle_order.py',
    '.venv/Lib/site-packages/poke_env/ps_client/ps_client.py',
    '.local/pokemon-showdown/sim/side.ts', '.local/pokemon-showdown/sim/battle.ts',
    '.local/pokemon-showdown/sim/pokemon.ts',
    '.local/pokemon-showdown/data/mods/gen1/scripts.ts',
    '.local/pokemon-showdown/data/mods/gen1/conditions.ts',
    '.local/pokemon-showdown/server/room-battle.ts',
    '.local/pokemon-showdown/server/chat-commands/core.ts')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inventory():
    paths = [ROOT/p for p in DEPENDENCIES]
    paths += [p for p in ROOT.iterdir() if p.is_file()]
    paths += [p for tree in TREES for p in (ROOT/tree).rglob('*') if p.is_file()
              and '__pycache__' not in p.parts and p.suffix != '.pyc']
    return {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(set(paths))}


if __name__ == '__main__':
    start = time.monotonic()
    mode = sys.argv[1]
    if mode == 'before':
        OUT.mkdir(exist_ok=False)
        hashes = inventory()
        result = {'hashes': hashes, 'seconds': time.monotonic()-start,
                  'git_status': subprocess.check_output(['git', 'status', '--short'], cwd=ROOT, text=True)}
        name = 'inputs-before.json'
    elif mode == 'after':
        before = json.loads((OUT/'inputs-before.json').read_text())['hashes']
        after = inventory()
        changed = [p for p, h in before.items() if after.get(p) != h]
        added = sorted(after.keys()-before.keys())
        assert not changed, changed
        assert all(p.startswith(('diagnostics/', 'tests/', 'docs/TRAJECTORY-CONTRACT')) for p in added), added
        result = {'ok': True, 'unchanged_inputs': len(before), 'added': added,
                  'hashes': after, 'seconds': time.monotonic()-start}
        name = 'inputs-after.json'
    else:
        raise ValueError('Use before or after; never modifies an input')
    with (OUT/name).open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    print({k:v for k,v in result.items() if k != 'hashes'})
