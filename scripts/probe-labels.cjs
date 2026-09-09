// Bounded official-engine tests. These are not evaluation battle results.
const {Battle} = require(require('path').join(process.cwd(), 'dist/sim/index.js'));
const assert = require('assert/strict');
const evs = {hp:252, atk:252, def:252, spa:252, spd:252, spe:252};
const mon = (species,moves) => ({species,moves,evs});
const b = new Battle({formatid:'gen1ou', seed:[1,2,3,4],
  p1:{name:'A',team:[mon('Exeggutor',['Explosion']),mon('Tauros',['Body Slam'])]},
  p2:{name:'B',team:[mon('Chansey',['Growl']),mon('Tauros',['Body Slam'])]}});
const actions = () => b.inputLog.filter(s => /^>p[12] /.test(s));
b.choose('p1','move 1');
assert.equal(actions().length, 0, 'The first submission is not committed');
b.choose('p2','move 1');
assert.deepEqual(actions().slice(0,2), ['>p1 move explosion','>p2 move growl']);
assert(!b.log.some(s => s.startsWith('|move|p2a:')), 'Fainted second Pokemon never announces its intended move');
assert(b.p1.activeRequest.forceSwitch[0]);
assert(b.p2.activeRequest.forceSwitch[0]);
b.choose('p1','switch 2');
assert.equal(actions().length, 2, 'Forced choices also wait until every required side commits');
b.choose('p2','switch 2');
assert.deepEqual(actions().slice(2), ['>p1 switch 2','>p2 switch 2']);
console.log(JSON.stringify({passed:true, committed_actions:actions(), growl_announced:false}));
b.destroy();
