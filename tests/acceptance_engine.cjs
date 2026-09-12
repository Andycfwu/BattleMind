// Unit-level calls on plain stubs. No Battle/Player constructors or turn resolution.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const cp = require('node:child_process');
for (const name of ['spawn', 'spawnSync', 'fork', 'exec', 'execSync', 'execFile', 'execFileSync']) {
  cp[name] = () => { throw new Error('Process launch forbidden in offline engine checks'); };
}
require('node:net').Server.prototype.listen = () => { throw new Error('Server launch forbidden'); };
const [original, derived, output] = process.argv.slice(2).map(p => path.resolve(p));
fs.mkdirSync(output);
const manifest = JSON.parse(fs.readFileSync(path.join(derived, 'acceptance-build.json')));
const session = '1'.repeat(32);
const hash = text => require('node:crypto').createHash('sha256').update(text).digest('hex');
function events(file) {
  let prev = '0'.repeat(64), index = 0;
  const records = fs.readFileSync(file, 'utf8').trimEnd().split('\n').map(line => {
    const e = JSON.parse(line); assert.equal(e.seq, ++index); assert.equal(e.prev, prev);
    assert.equal(e.hash, hash(prev + '\n' + e.body)); prev = e.hash;
    const body = JSON.parse(e.body); assert.equal(body.build, manifest.build_id); return body;
  });
  assert.equal(records[0].kind, 'open'); assert.equal(records.at(-1).kind, 'close');
  return records;
}
process.env.BATTLEMIND_ACCEPTANCE_DIR = output;
process.env.BATTLEMIND_ACCEPTANCE_SESSION = session;
process.env.BATTLEMIND_ACCEPTANCE_BUILD = manifest.build_id;
const BME = require(path.join(derived, 'dist/lib/battlemind-acceptance.js'));
function modules(root) {
  return {Side: require(path.join(root, 'dist/sim/side.js')).Side.prototype,
    Battle: require(path.join(root, 'dist/sim/battle.js')).Battle.prototype,
    Stream: require(path.join(root, 'dist/sim/battle-stream.js')).BattleStream.prototype,
    Room: require(path.join(root, 'dist/server/room-battle.js')).RoomBattle.prototype};
}
const old = modules(original), fresh = modules(derived);
let mathRandomCalls = 0;
Math.random = () => { mathRandomCalls++; throw new Error('RNG call forbidden'); };
function view(actions) {
  return actions.map(a => ({kind: a.choice, move: a.moveid ?? null, slot: a.moveSlot ?? null,
    targetLoc: a.targetLoc ?? null, target: a.target?.position ?? null}));
}
let fixtureNumber = 0;
function scenario(api, scenario, recording) {
  const id = ++fixtureNumber;
  const roomid = `battle-gen1ou-unit-${id}`;
  const outputs = [], queue = [], sends = [];
  let rngCalls = 0, turnLoopStubCalls = 0, returnValue;
  const request = {active: [{moves: [{id: 'psychic', move: 'Psychic', target: 'normal'},
    {id: 'recover', move: 'Recover', target: 'self'}]}], side: {id: 'p1', pokemon: []}};
  const battle = {gen: 1, gameType: 'singles', activePerHalf: 1, format: {mod: 'gen1'},
    inputLog: [], log: [], sentLogPos: 0, strictChoices: false,
    dex: {moves: {get: id => ({id, name: id, target: 'normal'})}},
    actions: {targetTypeChoices: () => false}, random: () => { rngCalls++; return 1; },
    send: (...args) => sends.push(args), allChoicesDone: () => false,
    updateSpeed() {}, clearRequest() {}, turnLoop() { turnLoopStubCalls++; },
    queue: {list: [], clear() {this.list = [];}, sort() {}, addChoice: actions => queue.push(view(actions))}};
  const side = {id: 'p1', battle, requestState: scenario === 'forced' ? 'switch' : 'move',
    activeRequest: request, lastSelectedMove: 'psychic', lastSelectedMoveSlot: 0,
    slotConditions: [{}], getChoiceIndex: () => 0, isChoiceDone() {return this.choice.actions.length === 1;},
    getChoice: api.Side.getChoice, commitChoices: api.Side.commitChoices,
    emitChoiceError: api.Side.emitChoiceError, updateRequestForPokemon: () => false,
    send: (...args) => sends.push(args)};
  const mon = {name: 'Fixture', position: 0, status: '', volatiles: {}, maybeLocked: false,
    side, getMoveRequestData: () => request.active[0], getMoves: () => request.active[0].moves,
    getLockedMove: () => null, getSemiLockedMove: () => null,
    getMoveSlot: index => ({id: request.active[0].moves[index]?.id || 'psychic'})};
  if (['wrap', 'clamp', 'recharge'].includes(scenario)) {
    mon.getSemiLockedMove = () => scenario; mon.maybeLocked = true;
  }
  if (scenario === 'fight') {mon.volatiles.partiallytrapped = {}; mon.maybeLocked = true;}
  if (scenario === 'struggle') mon.getMoves = () => [];
  side.active = [mon]; side.pokemon = [mon, {name: 'Bench', position: 1, fainted: false}];
  side.clearChoice = () => {side.choice = {actions: [], cantUndo: false, forcedSwitchesLeft: 1, switchIns: new Set()};};
  side.clearChoice();
  side.choose = input => {
    side.clearChoice();
    return scenario === 'forced' ? api.Side.chooseSwitch.call(side, '2') :
      api.Side.chooseMove.call(side, scenario === 'rejected' ? '9' : input.split(' ')[1]);
  };
  battle.getSide = () => side; battle.sides = [side];
  battle.choose = (id, input) => {returnValue = api.Battle.choose.call(battle, id, input); return returnValue;};
  battle.undoChoice = id => api.Battle.undoChoice.call(battle, id);
  const stream = {battle};
  const raw = JSON.stringify({...request, rqid: 7});
  const player = {slot: 'p1', request: {rqid: 7, request: raw, isWait: false}, sendRoom: text => outputs.push(text)};
  const room = {room: {roomid}, playerTable: {user: player},
    players: [player, {request: {isWait: false}}], frozen: false,
    stream: {write: text => {
      for (const line of text.split('\n')) {
        const index = line.indexOf(' '), type = line.slice(1, index), message = line.slice(index + 1);
        api.Stream._writeLine.call(stream, type, message);
      }
      return Promise.resolve();
    }}};
  api.Side.emitRequest.call(side, request);
  if (recording) BME.roomRequest(room, 'p1', raw);
  const action = scenario === 'forced' ? 'switch 2' : scenario === 'alias' ? 'move 2' : 'move 1';
  const token = `bm1-${session}-${'3'.repeat(32)}-1`;
  api.Room.choose.call(room, {id: 'user', popup: text => outputs.push(text)}, `${action}|7|${token}`);
  if (['replacement', 'cancel', 'stale'].includes(scenario)) {
    const user = {id: 'user', popup: text => outputs.push(text)};
    const second = token.slice(0, -1) + '2';
    if (scenario === 'cancel') api.Room.undo.call(room, user, `|7|${second}`);
    else api.Room.choose.call(room, user, `move 2|${scenario === 'stale' ? 6 : 7}|${second}`);
  }
  const acceptedView = view(side.choice.actions);
  if (returnValue && scenario !== 'cancel') {
    // Execute only the real commit bookkeeping; the turn loop is a counter stub.
    battle.allChoicesDone = () => true;
    api.Battle.commitChoices.call(battle);
  }
  if (recording) { BME.engineEnd(stream); BME.roomEnd(room); }
  if (recording && process.env.BATTLEMIND_ACCEPTANCE_DIR === output) {
    const roomEvents = events(path.join(output, roomid + '.room.jsonl'));
    const simEvents = events(path.join(output, roomid + '.sim.jsonl'));
    assert.equal(roomEvents.filter(e => e.kind === 'received').length,
      ['replacement', 'cancel', 'stale'].includes(scenario) ? 2 : 1);
    const accepted = simEvents.filter(e => e.kind === 'accepted');
    const committed = simEvents.filter(e => e.kind === 'committed');
    assert.equal(accepted.length, scenario === 'rejected' ? 0 : scenario === 'replacement' ? 2 : 1);
    assert.equal(committed.length, ['rejected', 'cancel'].includes(scenario) ? 0 : 1);
    for (const e of committed) {
      assert.equal(battle.inputLog[e.input_index], `>p1 ${e.choice}`);
      assert.deepEqual(e.actions, accepted.find(a => a.attempt === e.attempt).actions);
    }
    if (scenario === 'replacement') assert.equal(simEvents.filter(e => e.kind === 'replaced').length, 1);
    if (scenario === 'cancel') assert.equal(simEvents.filter(e => e.kind === 'cancelled').length, 1);
    if (scenario === 'stale') assert.equal(roomEvents.filter(e => e.kind === 'room_rejected').length, 1);
    if (['wrap','clamp','fight','recharge','struggle'].includes(scenario)) {
      assert.equal(accepted[0].choice, 'move ' + scenario);
      assert.equal(simEvents.filter(e => e.kind === 'normalization').length, 1);
    }
    if (scenario === 'forced') assert.equal(accepted[0].actions[0].switch_position, 2);
  }
  const publicSends = sends.map(args => args.map(value => value && typeof value === 'object' ?
    {name: value.name, position: value.position} : value));
  return {returnValue, acceptedView, afterCommit: view(side.choice.actions), inputLog: battle.inputLog,
    lastSelectedMove: side.lastSelectedMove, lastSelectedMoveSlot: side.lastSelectedMoveSlot,
    queue, sends: publicSends, outputs, rngCalls, turnLoopStubCalls};
}
const results = [];
for (const name of ['ordinary', 'alias', 'wrap', 'clamp', 'fight', 'recharge', 'struggle', 'forced', 'rejected',
  'replacement', 'cancel', 'stale']) {
  const control = scenario(old, name, false), observed = scenario(fresh, name, true);
  assert.deepEqual(observed, control, name);
  results.push({name, equal: true, returnValue: observed.returnValue, accepted: observed.acceptedView,
    committed: observed.inputLog, rngCalls: observed.rngCalls});
}
// Disabled tracing and a failed private write must leave engine method behavior unchanged.
const control = scenario(old, 'ordinary', false);
process.env.BATTLEMIND_ACCEPTANCE_DIR = path.join(output, 'does-not-exist');
assert.deepEqual(scenario(fresh, 'ordinary', true), control);
delete process.env.BATTLEMIND_ACCEPTANCE_DIR;
assert.deepEqual(scenario(fresh, 'ordinary', false), control);
assert.equal(mathRandomCalls, 0);
fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify({schema: 'acceptance-engine-unit-1',
  fixture_provenance: 'Pinned production methods on plain stubs; no Battle constructors, turn simulation, games or network.',
  cases: results, recording_failure_preserves_behavior: true, disabled_preserves_behavior: true,
  mathRandomCalls, games: 0, build: manifest.build_id}, null, 2));
console.log(`${results.length} paired method cases + failed/disabled recording passed; zero games/RNG calls`);
