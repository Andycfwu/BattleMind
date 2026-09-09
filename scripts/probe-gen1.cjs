// TEST ONLY: bounded engine scenarios, never substituted for battle-run metrics.
const {Battle} = require(require('path').join(process.cwd(), 'dist/sim/index.js'));
const assert = require('assert/strict');
const evs = {hp: 252, atk: 252, def: 252, spa: 252, spd: 252, spe: 252};
const mon = (species, moves) => ({species, moves, evs});
function battle(a, b, seed = 1) {
  return new Battle({formatid: 'gen1ou', seed: [seed, 2, 3, 4],
    p1: {name: 'ProbeA', team: [a, mon('Tauros', ['Body Slam'])]},
    p2: {name: 'ProbeB', team: [b, mon('Tauros', ['Body Slam'])]}});
}
function request(b, side) {
  const r = JSON.parse(JSON.stringify(b[side].activeRequest));
  r.rqid = 1; // Server adds this sequence number; direct engine has no transport rqid.
  return r;
}
function find(a, b, side, wanted) {
  for (let seed = 1; seed <= 32; seed++) {
    const game = battle(a, b, seed);
    game.makeChoices('move 1', 'move 1');
    const r = request(game, side);
    if (wanted(r)) { game.destroy(); return r; }
    game.destroy();
  }
  throw Error('No matching scenario within 32 fixed seeds');
}
const result = {};
result.recharge = find(mon('Tauros', ['Hyper Beam']), mon('Snorlax', ['Amnesia']), 'p1',
  r => r.active?.[0].moves[0].id === 'recharge');
result.sleep = find(mon('Exeggutor', ['Sleep Powder']), mon('Chansey', ['Growl']), 'p2',
  r => r.active?.[0].moves[0].id === 'fight');
result.partial_trap = find(mon('Dragonite', ['Wrap']), mon('Snorlax', ['Amnesia']), 'p2',
  r => r.active?.[0].moves[0].id === 'fight');
result.forced_switch = find(mon('Exeggutor', ['Explosion']), mon('Chansey', ['Growl']), 'p1',
  r => r.forceSwitch?.[0]);
const game = battle(mon('Magikarp', ['Splash']), mon('Magikarp', ['Splash']));
for (let turn = 0; turn < 65; turn++) {
  const r = request(game, 'p1');
  if (r.active[0].moves[0].id === 'struggle') { result.struggle = r; break; }
  game.makeChoices('move 1', 'move 1');
}
game.destroy();
assert(result.struggle, 'Exhausting real PP should request Struggle');
assert(!result.partial_trap.active[0].trapped, 'Gen 1 partial trapping allows switching');
console.log(JSON.stringify(result));
