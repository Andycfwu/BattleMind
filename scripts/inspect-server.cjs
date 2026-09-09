// Reads/validates using the official engine. Does not create a second simulator.
const fs = require('fs');
const path = require('path');
const root = process.cwd();
const {Dex, Teams, TeamValidator} = require(path.join(root, 'dist/sim/index.js'));
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const format = Dex.formats.get(input.format);
const config = require(path.join(root, 'config/config.js'));
const gen1 = Dex.mod('gen1');
const types = ['Normal','Fire','Water','Electric','Grass','Ice','Fighting','Poison','Ground','Flying','Psychic','Bug','Rock','Ghost','Dragon'];
const result = {
  type_chart: Object.fromEntries(types.map(def => [def, Object.fromEntries(types.map(atk =>
    [atk, gen1.getImmunity(atk, def) ? 2 ** gen1.getEffectiveness(atk, def) : 0]))])),
  format: {id: format.id, exists: format.exists, mod: format.mod, gameType: format.gameType},
  config: Object.fromEntries(['bindaddress', 'port', 'loginserver', 'repl', 'subprocesses', 'noguestsecurity'].map(k => [k, config[k]])),
  teams: input.teams.map(t => {
    const team = Teams.import(t.text);
    return {path: t.path, errors: team ? new TeamValidator(input.format).validateTeam(team) : ['Could not import team'],
      species_types: team ? Object.fromEntries(team.map(p => {
        const species = gen1.species.get(p.species); return [species.id, species.types];
      })) : {},
      move_rules: team ? Object.fromEntries(team.flatMap(p => p.moves).map(id => {
        const m = gen1.moves.get(id); return [m.id, {type: m.type, accuracy: m.accuracy,
          status: m.status || null, selfdestruct: m.selfdestruct || null,
          multihit: m.multihit || null, ignoreImmunity: m.ignoreImmunity ?? null}];
      })) : {},
      moves: team ? Object.fromEntries(team.flatMap(p => p.moves).map(id => {
        const move = Dex.mod('gen1').moves.get(id);
        return [move.id, move.basePower];
      })) : {}};
  })
};
console.log(JSON.stringify(result));
