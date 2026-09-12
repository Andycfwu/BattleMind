'use strict';
// Resolution only: no server, accounts, choices, or sockets are created here.
const fs = require('node:fs');
const path = require('node:path');
const {createRequire} = require('node:module');
const root = fs.realpathSync(process.cwd());
const entry = path.resolve(process.argv[2]);
if (path.dirname(entry) !== root || path.basename(entry) !== 'pokemon-showdown') {
  throw new Error('Inspect from the real server cwd and pokemon-showdown entry');
}
if (!fs.statSync(entry).isFile()) throw new Error('Missing server entry');
const seen = new Set();
const edges = [];
const failures = [];
const relative = p => path.relative(root, p).split(path.sep).join('/');
function packageFile(resolved, expected) {
  let directory = path.dirname(fs.realpathSync(resolved));
  while (directory.startsWith(root + path.sep)) {
    const candidate = path.join(directory, 'package.json');
    if (fs.existsSync(candidate) && JSON.parse(fs.readFileSync(candidate, 'utf8')).name === expected) return candidate;
    directory = path.dirname(directory);
  }
  throw new Error('Resolved package escapes the derived tree or lacks metadata: ' + expected);
}
function walk(file, from) {
  if (seen.has(file)) return;
  seen.add(file);
  const pkg = JSON.parse(fs.readFileSync(file, 'utf8'));
  const req = createRequire(from);
  for (const name of [...new Set([...Object.keys(pkg.dependencies || {}), ...Object.keys(pkg.optionalDependencies || {})])].sort()) {
    const optional = Object.hasOwn(pkg.optionalDependencies || {}, name);
    const row = {from: relative(from), package: name, optional};
    try {
      const resolved = req.resolve(name);
      row.resolved = relative(fs.realpathSync(resolved));
      const child = packageFile(resolved, name);
      row.version = JSON.parse(fs.readFileSync(child, 'utf8')).version;
      edges.push(row);
      walk(child, resolved);
    } catch (error) {
      row.error = String(error.message);
      edges.push(row);
      if (!optional) failures.push(row);
    }
  }
}
walk(path.join(root, 'package.json'), entry);
// Loading this module must not start a server. The real startup is a separately
// budgeted probe; this catches sockjs's transitive requires before that probe.
let sockjsLoad = false;
try { createRequire(entry)('sockjs'); sockjsLoad = true; }
catch (error) { failures.push({module_load: 'sockjs', error: String(error.message)}); }
console.log(JSON.stringify({schema: 'bm-acceptance-resolution-1', cwd: root, entry,
  edges, required_failures: failures, sockjs_loaded: sockjsLoad, server_started: false}));
if (failures.length) process.exitCode = 1;
