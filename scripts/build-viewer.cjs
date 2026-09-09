// Build only the official MIT battle renderer, not the network/account client.
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const esbuild = require(path.join(root, '.local/pokemon-showdown/node_modules/esbuild'));
if (require(path.join(root, '.local/pokemon-showdown/node_modules/esbuild/package.json')).version !== '0.25.12') throw Error('esbuild pin differs');
const source = path.join(root, '.local/v7-client-source/play.pokemonshowdown.com/src');
const out = process.argv[2];
const names = ['battle', 'battle-dex', 'battle-dex-data', 'battle-log', 'battle-log-misc', 'battle-text-parser', 'battle-tooltips', 'battle-animations', 'battle-animations-moves', 'battle-sound', 'battle-scene-stub', 'battle-teams'];
// The official build removes imports/exports and uses browser globals. esbuild
// performs TypeScript erasure; these two rewrites reproduce that module convention.
const scripts = names.map(name => {
  const file = path.join(source, name + (name === 'battle-log-misc' ? '.js' : '.ts'));
  let code = esbuild.transformSync(fs.readFileSync(file, 'utf8'), {loader: name.endsWith('misc') ? 'js' : 'ts', target: 'es2022', legalComments: 'inline'}).code;
  code = code.replace(/^import[\s\S]*?;\n/gm, '').replace(/^export \{[\s\S]*?\};\n/gm, '');
  code = code.replace(/^export /gm, '');
  // Renderer-only local resource routing. No account/client network module loaded.
  code = code.replaceAll('https://${Config.routes.client}/', '/assets/');
  code = code.replace(/resourcePrefix = \(\(\) => \{[\s\S]*?\}\)\(\);/, 'resourcePrefix = "/assets/";');
  code = code.replace(/fxPrefix = \(\(\) => \{[\s\S]*?\}\)\(\);/, 'fxPrefix = "/assets/fx/";');
  return code;
});
// BattleEffects initializes from Dex, so dependency order matters in global mode.
const order = ['battle-dex-data','battle-dex','battle-log-misc','battle-text-parser','battle-log','battle-sound','battle-teams','battle-scene-stub','battle-animations','battle-animations-moves','battle-tooltips','battle'];
fs.writeFileSync(path.join(out,'renderer.js'), order.map(n => scripts[names.indexOf(n)] + (n === 'battle-dex' ? '\nwindow.Dex = Dex;\n' : '')).join('\n') + '\nwindow.BattleMindRenderer = {Battle, Dex, BattleSound};\n');
const {Dex} = require(path.join(root, '.local/pokemon-showdown/dist/sim/dex'));
const en = {};
for (const [file,key] of [['default','Default'],['moves','Moves'],['abilities','Abilities'],['items','Items'],['pokedex','Pokedex'],['tags','Tags']]) {
  const table = require(path.join(root, '.local/pokemon-showdown/dist/data/text',file));
  en[key] = Object.values(table)[0];
}
Object.assign(en, require(path.join(root,'.local/pokemon-showdown/dist/data/text/names')));
const gen = Dex.mod('gen1');
const data = {BattleText:{en}, BattlePokedex:Object.fromEntries(gen.species.all().filter(p=>p.num>0&&p.num<=151).map(p=>[p.id,p])), BattleMovedex:Object.fromEntries(gen.moves.all().filter(m=>m.gen<=1).map(m=>[m.id,m])), BattleItems:{}, BattleAbilities:{}, BattlePokemonSprites:{}, BattlePokemonSpritesBW:{}, BattleTeambuilderTable:{}};
// Base tables above already come from the pinned Gen 1 Dex. There is no modern
// table to override; these empty compatibility tables are renderer plumbing.
for(let i=1;i<=9;i++) data.BattleTeambuilderTable['gen'+i]={overrideMoveData:{},overrideAbilityData:{},overrideSpeciesData:{},overrideTier:{},overrideItemData:{},overrideTypeChart:{},removeType:{}};
fs.writeFileSync(path.join(out,'data.js'), Object.entries(data).map(([k,v])=>'window.'+k+'='+JSON.stringify(v)+';').join('\n'));
console.log(JSON.stringify({esbuild:'0.25.12',renderer_bytes:fs.statSync(path.join(out,'renderer.js')).size}));
