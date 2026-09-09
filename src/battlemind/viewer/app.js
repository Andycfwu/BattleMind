const $id = id => document.getElementById(id);
BattleSound.muted = true;
BattleSound.effectVolume = 0;
BattleSound.bgmVolume = 0;
Dex.gen = 1;
Dex.loadedSpriteData = {xy: 1, bw: 1};
const priorPrefs = Dex.prefs.bind(Dex);
Dex.prefs = name => name === 'language' ? 'en' : name === 'nogif' ? true : priorPrefs(name);
let battle = null, current = null, token = '', seenIds = '', fetching = false;
let explain = false, loading = false, loadGeneration = 0;
const playbackControls = ['play', 'pause', 'back', 'next', 'reset', 'go', 'speed', 'seek', 'explain'];
window.viewerDiagnostics = {remoteRequests: [], errors: []};
window.addEventListener('error', e => fail(e.message));
window.addEventListener('securitypolicyviolation', e => {
  viewerDiagnostics.remoteRequests.push(e.blockedURI);
  $id('network-status').dataset.blocked = String(viewerDiagnostics.remoteRequests.length);
  fail('Blocked unexpected resource: ' + e.blockedURI);
});

function fail(error) {
  $id('error').textContent = String(error);
  viewerDiagnostics.errors.push(String(error));
}

async function get(url) {
  const response = await fetch(url);
  if (!response.ok) throw Error(await response.text());
  return response.json();
}

function speed() {
  if (!battle || loading) return;
  const mode = $id('speed').value;
  battle.messageFadeTime = {hyperfast: 40, fast: 50, normal: 300, slow: 500}[mode];
  battle.messageShownTime = mode === 'slow' ? 1000 : 1;
  battle.scene.updateAcceleration();
}

function renderInfo() {
  if (!current || loading) return;
  $id('state').textContent = current.status === 'truncated' ? 'CAPPED — no winner' : current.status.toUpperCase();
  $id('mode').textContent = current.origin.startsWith('live') ?
    'Delayed playback · simulation may already be finished' : 'Recorded playback';
  $id('turn').textContent = 'Turn ' + Math.max(0, battle?.turn || 0);
  $id('detail').textContent = current.detail || (current.status === 'completed' ?
    'Completed game. The recorded result belongs only to this game.' : '');
  if (/^memory-[0-3]$/.test(current.id)) {
    const encounter = Number(current.id.slice(-1)) + 1;
    $id('detail').textContent = `Recorded encounter ${encounter}/4. Reset before encounter 1; ` +
      (encounter === 1 ? 'cold start, no earlier evidence.' :
        `memory uses only the preceding ${encounter - 1} completed encounter(s).`) +
      ' Navigating playback does not update memory. Open the recorded explanation for probabilities and memory digest.';
  }
  $id('limitation').textContent = current.limitations.join(' ');
  $id('public-log').textContent = current.lines.join('\n');
  $id('explain').disabled = current.status === 'running';
  if (explain) $id('explanation').textContent = current.explanations.length ?
    JSON.stringify(current.explanations, null, 2) : 'No recorded score explanation is packaged for this encounter.';
}

async function load(id) {
  const generation = ++loadGeneration;
  loading = true;
  playbackControls.forEach(key => $id(key).disabled = true);
  $id('state').textContent = 'Loading public replay';
  const next = await get('/api/replay/' + id);
  if (generation !== loadGeneration) return;
  // Invalidate pending animation callbacks before destroying the prior scene.
  if (battle) { battle.pause(); battle.destroy(); }
  current = next;
  explain = false;
  $id('explanation').textContent = 'Hidden until requested.';
  battle = new Battle({id: 'battle-gen1ou-1', log: current.lines, $frame: $('.battle'),
    $logFrame: $('.official-log'), isReplay: true, paused: true, autoresize: false});
  battle.ignoreNicks = true;
  battle.setMute(true);
  loading = false;
  playbackControls.forEach(key => $id(key).disabled = false);
  speed();
  battle.subscribe(state => {
    renderInfo();
    if (state === 'error') fail('Official renderer reported an unsupported replay event.');
  });
  renderInfo();
}

async function refresh() {
  if (fetching) return;
  fetching = true;
  try {
    const state = await get('/api/state');
    token = state.token;
    const ids = state.replays.map(r => r.id).join(',');
    if (ids !== seenIds) {
      const old = $id('recording').value;
      $id('recording').replaceChildren(...state.replays.map(r =>
        new Option(r.title.replace('— memory starts empty', '— sequence starts empty'), r.id)));
      seenIds = ids;
      const last = state.replays.at(-1);
      const selected = last.origin.startsWith('live') ? last.id : (old || 'normal');
      $id('recording').value = selected;
      await load(selected);
    }
    for (const id of ['agent-a', 'agent-b']) {
      if ($id(id).options.length) continue;
      $id(id).replaceChildren(...state.policies.map(p => new Option(p, p)));
      $id(id).value = id === 'agent-a' ? 'learned-score' : 'max-base-power';
    }
    const ledger = state.ledger;
    $id('budget').textContent = ledger.requested + '/' + ledger.maximum_games +
      ' games requested · ' + ledger.run_seconds.toFixed(2) + '/300 seconds · ' + ledger.state;
    $id('launch').disabled = ledger.state !== 'idle' || ledger.requested >= ledger.maximum_games || ledger.run_seconds + 75 > 300;
    if (!loading && current?.origin.startsWith('live')) {
      const id = current.id;
      const next = await get('/api/replay/' + id);
      if (!loading && current.id === id) {
        for (const line of next.lines.slice(current.lines.length)) battle.add(line);
        current = next;
        renderInfo();
      }
    }
  } catch (error) { fail(error); }
  finally { fetching = false; }
}

$id('recording').onchange = () => load($id('recording').value).catch(fail);
$id('play').onclick = () => battle.play();
$id('pause').onclick = () => battle.pause();
$id('back').onclick = () => battle.seekBy(-1);
$id('next').onclick = () => battle.seekBy(1);
$id('reset').onclick = () => { battle.reset(); battle.pause(); renderInfo(); };
$id('go').onclick = () => battle.seekTurn(Math.max(0, Math.min(1000, Number($id('seek').value))));
$id('speed').onchange = speed;
$id('explain').onclick = () => { explain = true; renderInfo(); };
$id('launch').onclick = async () => {
  try {
    const response = await fetch('/api/demo', {method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-BattleMind-Token': token},
      body: JSON.stringify({agent_a: $id('agent-a').value, agent_b: $id('agent-b').value})});
    if (!response.ok) throw Error(await response.text());
    await refresh();
  } catch (error) { fail(error); }
};
document.addEventListener('click', e => { if (e.target.closest('a')) e.preventDefault(); });
refresh();
setInterval(refresh, 750);
