"""One-way, public-only spectator projection. Never used by a battle policy."""

import json
import math
from pathlib import Path
import re

from poke_env.data import GenData

from .environment import sha256
from .labels import read_jsonl

VERSION = 'v7-public-replay-1'
PUBLIC = frozenset(('gen gametype tier teamsize start turn switch drag move cant faint '
    '-damage -heal -status -curestatus -boost -unboost -setboost -clearboost '
    '-clearallboost -activate -start -end -sidestart -sideend -weather -fieldstart '
    '-fieldend -crit -supereffective -resisted -immune -miss -fail -hitcount -singleturn '
    '-singlemove -notarget -ohko -mustrecharge -prepare -anim -nothing -cureteam '
    '-sethp -swapboost -copyboost -clearpositiveboost -clearnegativeboost').split())
TERMINAL = {'completed','truncated','timeout','crash','cancelled','not_started'}


def public_line(line: str) -> str | None:
    """Accept only spectator mechanics; no HTML/chat/requests/choices/end-log input.

    Called only on a separate unauthenticated spectator socket. It cannot turn a
    player-channel log into a safe spectator log (channel provenance matters).
    """
    if not isinstance(line, str) or '\n' in line or '\r' in line or len(line) > 4000:
        raise ValueError('Malformed spectator line')
    parts = line.split('|')
    kind = parts[1] if len(parts) > 1 else ''
    if kind in {'request','split','showteam','inputlog'}:
        raise ValueError('Private protocol on spectator connection')
    if kind == 'player':
        return f'|player|{parts[2]}|Side {parts[2][1:]}|unknown' if parts[2] in {'p1','p2'} else None
    if kind not in PUBLIC:
        return None  # Includes raw win/tie: terminal accounting must authorize these.
    if (kind=='gen' and parts[2]!='1') or (kind=='gametype' and parts[2]!='singles'):
        raise ValueError('Viewer supports Gen 1 singles only')
    hp_indices = {'switch':4,'drag':4,'-damage':3,'-heal':3}
    if kind in hp_indices:
        hp=parts[hp_indices[kind]]
        if not re.fullmatch(r'(?:0 fnt|(?:100|[1-9]?[0-9])/100(?: (?:par|slp|frz|brn|psn|tox))?)',hp):
            raise ValueError('Spectator HP must retain the public 100 scale; private exact HP rejected')
    return line


def terminal_lines(row: dict) -> list[str]:
    if row['status'] != 'completed':
        return []  # A cleanup forfeit is never a replay victory.
    if row['winner'] == 'draw':
        return ['|tie|']
    role = row['player_roles'][row['winner']]
    return [f'|win|Side {role[1:]}']


def validate_replay(data: dict) -> None:
    if set(data) != {'schema_version','id','title','origin','status','outcome','detail','lines','explanations','provenance','limitations'}:
        raise ValueError('Unexpected public replay fields')
    if data['schema_version'] != VERSION or not re.fullmatch(r'[a-z0-9-]{1,80}', data['id']):
        raise ValueError('Unsupported replay schema/identity')
    if data['status'] not in TERMINAL | {'running'} or len(data['lines']) > 30000:
        raise ValueError('Unsupported replay state/size')
    for line in data['lines']:
        if line.startswith(('|win|','|tie|')):
            if data['status'] != 'completed':
                raise ValueError('Incomplete replay cannot contain a victory')
        elif public_line(line) != line:
            raise ValueError('Nonpublic/un-normalized replay protocol')
    if data['status'] != 'completed' and data['outcome'] is not None:
        raise ValueError('Incomplete replay cannot have an ordinary outcome')
    if data['status'] == 'running' and data['explanations']:
        raise ValueError('Explanations are post-encounter only')
    explanation_keys={'viewed_player','turn','decision_id','snapshot_sha256','chosen_action','scores','probability',
        'shadow_probabilities','shadow_choices','initial_choice','initial_scores','memory_digest','meaning'}
    for ex in data['explanations']:
        if set(ex)!=explanation_keys or ex['viewed_player'] not in {'a','b'}:
            raise ValueError('Unexpected explanation fields; no private snapshot in viewer')
        if ex['probability'] is not None and (not math.isfinite(ex['probability']) or not 0<=ex['probability']<=1):
            raise ValueError('Invalid explanation probability')


def historical_replay(path: Path, match: int, replay_id: str, title: str) -> dict:
    """Align two public projections, selecting only opposing-observer event fields.

    Public histories live in a recorder directory but are not engine end logs.
    No exact own HP, private request, team file or private end log is read here.
    """
    row = next(r for r in read_jsonl(path/'battles.jsonl') if r['match'] == match)
    history_path = path/f'privileged/{match:03d}-histories.json'
    histories = json.loads(history_path.read_text())
    if len(histories['a']) != len(histories['b']):
        raise ValueError('Public perspective lengths differ; do not guess alignment')
    lines = ['|gen|1','|gametype|singles','|tier|[Gen 1] OU','|player|p1|Side 1|unknown',
             '|player|p2|Side 2|unknown','|teamsize|p1|6','|teamsize|p2|6','|start']
    active, identities = {}, {}
    turn = 0
    for a,b in zip(histories['a'], histories['b']):
        if (a['turn'], a['kind']) != (b['turn'], b['kind']):
            raise ValueError('Public event chronology differs')
        kind = a['kind']
        if a['turn'] != turn:
            turn = a['turn']; lines.append(f'|turn|{turn}')
        opposing = [(e, side) for e,side in ((a,'b'),(b,'a')) if (e['actor'] or '').startswith('opponent:')]
        if not opposing:
            # Only field-wide events may lack an identifiable opposing observer.
            if kind in {'-clearallboost','-weather','-fieldstart','-fieldend'} and a == b:
                lines.append('|'+kind+('|'+'|'.join(a['values']) if a['values'] else ''))
            continue
        if len(opposing) != 1:
            raise ValueError('Ambiguous observer projection')
        e, side = opposing[0]
        role = row['player_roles'][side]
        ident = f'{role}a: {side.upper()}{e["actor"].split(":")[1]}'
        values = e['values']
        if kind in {'switch','drag'}:
            species = GenData.from_gen(1).pokedex[values[0]]['name']
            identities[ident] = species; active[role] = ident
            line = f'|{kind}|{ident}|{species}|{values[1]}'
        elif kind == 'move':
            move = GenData.from_gen(1).moves.get(values[0], {})
            target = ident if move.get('target') == 'self' else active.get('p2' if role=='p1' else 'p1', ident)
            line = f'|move|{ident}|{move.get("name",values[0])}|{target}'
        else:
            # This historical allowlist lost effect annotations; preserve that limitation.
            if kind in {'-start','-end','-activate','-sidestart','-sideend'} and values:
                effect = GenData.from_gen(1).moves.get(values[0])
                values = [('move: '+effect['name']) if effect else values[0]]
            line = '|'+kind+'|'+ident+('|'+'|'.join(values) if values else '')
        cleaned = public_line(line)
        if cleaned: lines.append(cleaned)
    lines += terminal_lines(row)
    data = {'schema_version':VERSION,'id':replay_id,'title':title,'origin':'historical public projection',
        'status':row['status'],'outcome':row['winner'] if row['status']=='completed' else None,
        'detail':row.get('detail'),'lines':lines,'explanations':[],
        'provenance':{'run_manifest_sha256':sha256(path/'run.json'),'match':match,
                      'public_histories_sha256':sha256(history_path),'battle_records_sha256':sha256(path/'battles.jsonl')},
        'limitations':['Historical public projection is incomplete: trailing effect annotations and some minor messages were not retained.',
                      'HP is taken from the opposing observer public scale, never own exact HP.',
                      'Move announcement does not prove selection, hit or successful execution.']}
    validate_replay(data)
    return data


def explanation(row: dict) -> dict:
    """Post-encounter opt-in, viewed-player score output, with no snapshot/private foe."""
    ev = row.get('prediction_evaluation', {})
    return {'viewed_player':row['player'],'turn':row['observation']['turn'],
        'decision_id':row['decision_id'],'snapshot_sha256':row['snapshot_sha256'],
        'chosen_action':row['chosen_action'],'scores':row['action_scores'],
        'probability':ev.get('prediction',{}).get('probability'),
        'shadow_probabilities':ev.get('shadow_probabilities'), 'shadow_choices':ev.get('shadow_choices'),
        'initial_choice':ev.get('initial_choice'),'initial_scores':ev.get('initial_scores'),
        'memory_digest':ev.get('memory_sha256'),
        'meaning':'Recorded own-policy intention/approximate scores after encounter; not thoughts or exact damage.'}
