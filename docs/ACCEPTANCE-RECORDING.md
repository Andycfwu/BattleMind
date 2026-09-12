# Request-bound acceptance recording — offline implementation

2026-09-10. This follows the [trajectory contract audit](TRAJECTORY-CONTRACT-AUDIT.md)
and the [actor-step results](ACTOR-STEP-RESULTS.md). It adds opt-in recording and
an independent evidence validator. **No server, battle, training, eligibility
change or historical recovery occurred.** The 144 completed learner episodes
identified by that audit remain excluded. V6 acceptance remains incomplete.

## Why a separate engine trace is necessary

The pinned client has no explicit choice-acceptance acknowledgment. A successful
WebSocket send, absence of an error, or later turn message does not certify which
attempt the simulator accepted. The room receives `rqid`, but forwards only choice
text to the simulator. The existing end log stores canonical choices without that
request ID. Client-only instrumentation cannot supply the missing link.

Inspected sources are installed poke-env **0.16.1** and official Showdown commit
**`2f5b273925862ac242b419086c1e7a8868b51da1`**, version 0.11.11. Exact local references
below refer to the unchanged original source, not shifting derived line numbers.

| Source | Evidence / instrumentation point |
|---|---|
| `.venv/Lib/site-packages/poke_env/ps_client/ps_client.py:307–326` | `send_message` constructs the room payload and awaits `websocket.send`; no accepted-choice result. |
| `.venv/Lib/site-packages/poke_env/player/player.py:295–432` | Request dispatch and stock error/default retry paths. BattleMind's existing override suppresses retries and preserves warnings. |
| `src/battlemind/runner.py:139–215` | Ordered observer parsing, duplicate-rqid suppression, immutable snapshot, sampling, mapping, own journal, then send. These bytes are unchanged. |
| `.local/pokemon-showdown/server/chat-commands/core.ts:1122–1162` | `/choose` and `/undo` route the target string to the room. |
| `.local/pokemon-showdown/server/room-battle.ts:617–659` | Room receipt, current-rqid/wait gates, forwarded choice and undo. Returning from this method is not simulator acceptance. |
| Same file, `:785–808` | The room increments its request counter, adds `rqid`, retains exact serialized request, then sends it. No other request field is changed here. |
| `.local/pokemon-showdown/sim/battle-stream.ts:36–61,98–108` | One stream write processes its lines and only then sends updates. A private envelope is prefixed inside that same write; no extra update boundary is introduced. |
| `.local/pokemon-showdown/sim/side.ts:520–538` | Engine request emission and explicit Invalid/Unavailable choice errors. The new trace records error category, not unnecessary private error text. |
| Same file, `:675–709,915,1142–1183,1185` | Locked/semi-locked moves; Gen 1 fight; no-enabled-moves Struggle; switches; Gen 1 commitment bookkeeping; choice replacement. |
| `.local/pokemon-showdown/sim/battle.ts:2964–3029,3032–3054` | Parsing, completed-choice acceptance, all-required-choices commitment, and successful cancellation. |

The original files, their compiled output, config, lock, installed wrapper and
license notices remain intact. The before/after inventory covers their hashes.

## Versioned contract

Private streams use **`bm-acceptance-1`**, build manifests
**`bm-acceptance-build-1`**, setup metadata **`bm-acceptance-session-1`**, and reports
**`bm-acceptance-report-1`**. Existing observation, model and label schemas do not change.

Each stream is exclusive-create JSONL with sequence number, previous hash, exact
JSON body string and SHA-256 of `previous_hash + newline + body`. It requires an
opening record and a clean closing record. The hash chain detects accidental
corruption/truncation; it is not a signature or an attestation against a malicious
local writer. Session/build identity is in every event. No timestamps are used for
matching; exact request, attempt and stream sequence identities are authoritative.

| Stage | New record and meaning |
|---|---|
| Own request | Exact raw JSON and SHA-256, including engine-room `rqid`; only that client's request. A canonical hash after removing `rqid` joins the simulator's emitted request content. |
| Frozen decision | Original serialized decision, snapshot digest, ordered legal IDs, map, chosen semantic ID and original own-slot registry. REINFORCE's vector, draw, checkpoint digest and scalar sampled probability are retained. A deterministic baseline can have probability `null`; it is not fabricated. |
| Attempt | OS-generated session/connection IDs and monotonically increasing local attempt number. Wire token is `bm1-{session}-{connection}-{number}`. Attempt precedes the send; send result is recorded separately. |
| Room receipt / gate | Received attempt, submitted rqid, current rqid, own-request hash and exact command; separate forwarded or explicit room rejection event. |
| Simulator dispatch | Private envelope carries the same attempt/context into the same simulator write. It binds to the current side's locally numbered request epoch and emitted-content hash. Epochs are instrumentation counters, not engine turns. |
| Parse / acceptance | `parsed` records the actual boolean from `Side.choose`. `accepted` occurs only after that returns true and `isChoiceDone()` passes. It records canonical choice and a small normalized-action view. |
| Replacement / cancellation | Pending acceptance is tied to the actual `side.choice` object. A new choice object invalidates the previous attempt, including a failed replacement parse. Successful undo records which accepted attempt was cancelled and the cancelling attempt. |
| Commitment | The exact accepted attempt and choice object are recorded where `Battle.commitChoices` appends its input log entry, after its all-choices check. The validator requires the exact recorded input index/text in the hashed official end log. No searching ahead. |
| Execution / outcome | **Not established by these records.** Existing public-execution evidence and terminal accounting remain separate. A cap/cleanup end log cannot manufacture a reward. |

Canonical request hashing recursively sorts JSON object keys and preserves array
order. Request fields in this supported scope contain integer, string, boolean,
null and array/object data. The raw payload is also hashed byte-for-byte. Private
own stats/nicknames in that raw request are recording inputs only, never features.
The engine trace emits no team, stats, account name or simulator RNG state.

The action being optimized remains the **sampled semantic ID**, with its original
probability. Two sampled IDs may normalize to the same accepted move while keeping
different original probabilities. Acceptance evidence does not replace them with
a summed probability, prove reward eligibility, or create an opponent label.

Supported normalization evidence includes locked/semi-locked Wrap, Clamp and
Recharge, Gen 1 fight, and no-enabled-moves Struggle. The branch event, parse,
acceptance, request linkage and commitment must all agree. The normalized view
contains only kind, move ID/slot, target location and current switch position.
Forced replacements use the engine's **`instaswitch`**, ordinary switches `switch`.
Gen 1 `Side.commitChoices` can further change a queued move (including fight
bookkeeping); recorded canonical commitment is deliberately not called execution.

## Implementation and use

Only new production files were added:

- `src/battlemind/acceptance.py`: own-client recorder, strict JSON/hash chains,
  independent request-menu/CDF checks, conservative post-match status validator.
- `src/battlemind/acceptance_player.py`: opt-in `AcceptanceLocalPlayer` wraps the
  existing ordered hook and own journal, then adds an opaque token to the send.
  `close_acceptance_players` seals each own journal only after existing client
  cleanup returns; failed cleanup seals it as incomplete.
- `src/battlemind/acceptance_build.py`: exact-anchor patch/build/verification and
  `recording_environment`. This setup helper checks runtime pins, requires a fresh
  ignored `runs/.../privileged/...` directory, and returns child-process environment
  variables. It neither launches a server nor mutates the global environment.
- `configs/acceptance/battlemind-acceptance.ts`: separate private room/simulator
  writers and small observers at the source points above.

There is **no new server-to-client acknowledgment**. The explicitly opt-in client
sends `/choose move 1|7|bm1-...`. The original parser already uses only the first
two fields; the derived room reads the third for recording. Its internal
`>bmaccept {...}` envelope is never broadcast. Original clients cannot produce a
complete new contract, and original engine logs cannot be retrofitted into one.

Future collection needs an explicitly reviewed harness using this new class and
setup API; the historical `battle` runner/CLI has intentionally not been rewired.
Use fresh player instances/recorders per battle. Multiple attempts within that
battle are represented, but never automatically retried. Identical repeat requests
are retained; changing a payload under the same rqid, reordered requests, reconnects
or reused side connections fail closed. Reconnect recovery is unsupported, rather
than guessed from a turn or later command. Original own slots survive request-roster
reordering; submitted switch commands still address current request positions.

Only a post-match caller may run `validate_acceptance`, after both clients stop.
It reads sealed streams and a hashed official end record. CLI use additionally
requires `--build` and runs strict derived-build verification. Its report separates
`committed`, `accepted_not_committed`, `replaced`, `cancelled`, `cancellation_applied`,
`rejected` and `unknown`. `integrity=valid` means structurally consistent evidence,
not that every attempt is committed. Malformed/missing/conflicting streams return
`invalid_or_incomplete`; missing receipt/end/send evidence never becomes acceptance.

Private files stay outside spectator exports. Neither class passes a recorder,
raw request, normalized action, other journal or registry to a policy/value model.
The original public memory and viewer modules are unchanged. Synchronous private
I/O can add latency; writer failures do not change engine returns or RNG and leave
missing/unsealed evidence that fails validation. Windows privacy follows the local
account/directory ACL; POSIX mode 0600 is not a Windows security guarantee.

## Derived build and checks actually performed

The current separate build is `.local/pokemon-showdown-acceptance-v1-r3`:

- Build ID: `e5e81f08618e4d4ac5a13cba3b7a97cae9296d1da7fa4a9b6ea4887c922ec691`.
- Patch SHA-256: `84c4c66dfdf4a165b8e17f54c5b32a455a5715a8b7daaae02bb7a3d1c40214d3`.
- `acceptance-build.json` inventories upstream files, derived sources/compiled
  output, copied dependency bytes, lock/config, runtime versions and helper hash.
- No dependency download occurred. `node_modules` was copied, never linked. The
  MIT notices remain. Earlier v1/r2 engineering builds are retained but superseded;
  the current verifier rejects their old helper hash. They never ran games.
- The historical doctor still rejects the derived build at its commit check.
  The new path does not relax historical source or checkpoint checks.

Actual commands (PowerShell, project root; all outputs in the fresh directory):

```powershell
. .\scripts\env.ps1
.\.venv\Scripts\python.exe -B -m battlemind.acceptance_build --output .local/pokemon-showdown-acceptance-v1-r3
node tests/acceptance_engine.cjs .local/pokemon-showdown .local/pokemon-showdown-acceptance-v1-r3 runs/acceptance-recording-offline-20260910/engine-units-3
.\.venv\Scripts\python.exe -B -m pytest -q tests/test_acceptance.py tests/test_acceptance_build.py
.\.venv\Scripts\python.exe -B -m pytest -q -m 'not integration'
.\.venv\Scripts\python.exe -B diagnostics/acceptance_offline_verify.py replay
.\.venv\Scripts\python.exe -B diagnostics/acceptance_offline_verify.py integrity
.\.venv\Scripts\python.exe -B diagnostics/acceptance_offline_verify.py setup
.\.venv\Scripts\python.exe -B diagnostics/acceptance_offline_verify.py closure
git diff --check
```

Output paths are exclusive; use fresh paths for a later build/unit-method run.
The diagnostic replay/integrity helper deliberately refuses to overwrite its results.
The standalone report interface is `python -m battlemind.acceptance --help`;
it writes no input file and does not feed the existing learner.

Verification artifacts live in
[`runs/acceptance-recording-offline-20260910/`](../runs/acceptance-recording-offline-20260910/).
`engine-units-3/results.json` records **12 original/derived method comparisons**,
plus disabled and failed recording. Return values, accepted/committed state,
canonical input logs, queue inputs, public method emissions and RNG counts agree.
Actual instrumented events/hashes were checked for ordinary, alias, Wrap, Clamp,
fight, Recharge, Struggle, forced replacement, rejection, replacement, cancellation
and stale requests. Process/network launch is blocked inside that harness. Its
turn-loop method is a counter stub: **zero simulated battles and zero RNG calls**.

Python fixtures are clearly synthetic source-grounded requests, not recovered
historical requests. They cover corruption, exact CDF boundaries, many-to-one
sampling, two sides, missing evidence, reconnect rejection, client order, cleanup
sealing, build/path checks and private mutations. The mutation test reproduces
the same policy/predictor result, nonempty public-memory updates and viewer output.
**59 focused tests passed in 1.54s; 326 offline unit tests passed in 8.32s, with
14 integration tests deselected.** Final hashes are recorded in `closure.json`.
`setup-verification.json` also verifies the actual derived-build/runtime/private-path
setup API without starting its returned environment or any server process.

`verification.json` loaded **28 retained REINFORCE checkpoint files**, original V4
and selected V5 through their unchanged intended loaders. It replayed **2,493 learned
decisions** from three named retained 24-game cells (original initialization,
actor-step control batch 6, treatment batch 6). Probabilities, logits, values, draws,
choices and legacy joins reproduced exactly, including **37 still-unknown labels**
in the control cell. These are replays of 72 historical games, not new collections.
No optimizer/update reconstruction was needed: all original production source,
including the optimizer, remains byte-identical. Replay took 5.113s wall / 4.922s CPU.

`preservation.json` checked **37,270 pre-work files**, with **zero changes or missing
files**. Historical experiment/model/source hashes were not rewritten. Full-source
experiment audits still require their historical source inventories, since adding
modules changes today's inventory. This check does not waive that requirement.
Development failures are retained: early fixture-side identity/stub comparison
errors and an early misplaced client-side guard were fixed before the passing
checks. Forced engine action handling was corrected to `instaswitch` before r3.

**Still unverified:** real WebSocket framing across the new token, process-stream
transport, live request timing/cancellation, raw-request fidelity across complete
battles, full server cleanup, and instrumentation overhead. Offline method tests
cannot establish those. The [separate proposed live check](ACCEPTANCE-LIVE-VERIFICATION.md)
is not executed and provides no battle-strength or revised training-eligibility claim.
