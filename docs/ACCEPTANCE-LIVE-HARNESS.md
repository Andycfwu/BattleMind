# Live acceptance harness review — 2026-09-10

The user authorized the single [48-game proposal](ACCEPTANCE-LIVE-VERIFICATION.md).
The earlier deliverable contained recording components and offline method tests,
but no live collector or ledger. This narrow harness supplies that missing
orchestration in `diagnostics/acceptance_live_verify.py`; historical production,
recording, model, policy and eligibility files remain unchanged.

The scientific/configuration contract remains exactly the existing proposal:
24 original + 24 instrumented, 180s/240s phase caps, 180s overhead, 600s aggregate;
four teams, original frozen c0 versus random, seed 260911, 300 turns/60s per game,
concurrency 1 and 127.0.0.1. No trials, retries, repairs after collection, or learning.
The fixed fresh output is `runs/acceptance-live-verification-20260910`; existing
output or a consumed/running phase cannot be resumed. The proposed config's old
status text remains historical; the new freeze records this user's authorization.

Both 24-game allocations are reserved in a persistent ledger before collection.
Actual requests increment immediately before each match invocation; untouched
phases remain zero requested, with distinct reserved/planned slots. A new game
requires 66s remaining (60s game + 6s cleanup). Phase completion and experiment
closure are idempotent. Phase elapsed time includes child startup, server lifecycle,
per-match replay/acceptance validation and child cleanup. Overhead includes source
freeze, preflight, post-run preservation/reporting and the measured offline checks
debited at invocation. No unused allocation is borrowed across phases.

Each phase is a separate child process using the unchanged `LocalServer` startup,
loopback config, engine logging and shutdown. The original process strips acceptance
environment variables. The derived process receives only the environment returned
by the reviewed `recording_environment`. Strict original doctor validation still
runs; the derived build uses its separate exact build verifier. Both engines must
produce identical official format/team/type/move diagnostic values. This does not
claim identical simulated trajectories.

The harness invokes the unchanged `runner.play_match`. For an instrumented match
only, a context manager temporarily binds its player and cleanup factories to the
existing opt-in recorder class and seal-after-cleanup function. It restores both
bindings in `finally`. This is confined to a dedicated process, one awaited match,
with no parallel battle, service request or training task. Policies still receive
only the original immutable `DecisionSnapshot`; their files, parameters, RNG,
sampling and command resolution are unchanged. No private data is supplied to them.

After `play_match` returns, both clients have stopped and the legacy post-match
recorder has finished. The harness replays both policies in original decision order,
including all REINFORCE probabilities/logits/values/draws and random-policy choices.
It then validates private request/attempt/acceptance/commitment chains and compares
each client's captured decision rows with that client's original journal. A complete
game requires a committed status for every sampled attempt. Legacy unknown labels
are retained and are not replaced with new acceptance statuses.

An integrity error, unexpected warning, protocol error, failed cleanup or nonfinite
inference stops before the next scheduled match. Caps retain null outcomes and may
continue only after valid cleanup/evidence checks. A structurally broken capped
recording is a blocking integrity failure. Per-phase requested/completed/missing/
never-started counts remain distinct from experiment acceptance status.

Independent post-match mutation checks use disposable copies of a newly collected
observer's records. Public-memory replay, predictor, policy and spectator projection
must be identical when unrelated private acceptance/end evidence is corrupted.
No viewer service is launched. Existing offline private-data boundary tests remain
part of preflight. Cleanup records sampled process IDs and verifies no owned process
or port-8000 listener remains. CPU/RSS are sampled at 0.1s; short-lived process peaks
may be missed. Acceptance validation time is measured separately; differences in
total phase time cannot isolate causal recording overhead with unmatched battles.

Before collection, run the new ledger/scope tests and existing offline tests only.
Record their measured process time in a fresh preflight directory and debit that
wall duration against the overhead/aggregate budget. No battle-based engineering
check is added. Freeze this file, code/config/source hashes, source snapshot, exact
checkpoint/team hashes and derived-build inventory before either phase starts.

Normalization coverage is reported from actual committed branch records. Missing
Wrap/Clamp/fight coverage remains unverified, with no extra games. Passing live
checks would support a separate eligibility-design discussion only; it neither
changes the learner's rule nor recovers any historical excluded episode.

Readiness evidence: 9 new offline harness tests passed (0.22s), then the offline
suite passed 335 tests with 14 integrations deselected (11.25s). All 12 original/
derived method cases plus disabled/failed recording passed again, without battles.
`runs/acceptance-live-preflight-20260910/checks.json` records 13.6072756s measured
process wall time plus a conservative 2s debit for the earlier harness test command:
15.6072756s total charged to overhead. The last review additions bind that passing
check record and the original input inventory into the pre-collection freeze;
they do not alter match, policy, evidence or ledger mathematics.
