# Proposed acceptance-recording live verification — not executed

This is a proposed **later authorization**, following
[ACCEPTANCE-RECORDING.md](ACCEPTANCE-RECORDING.md). It is a functional recording
check, not learning or a strength experiment. The machine-readable proposal is
[`configs/acceptance-live-verification.json`](../configs/acceptance-live-verification.json).
No command to collect these games has been implemented or run in this task.

Request exactly **48 games maximum / 600 seconds aggregate wall time**, concurrency
1, loopback only. Allocate 24 original-engine games / 180s, 24 instrumented-engine
games / 240s, and 180s for setup, source verification, shutdown, replay and reporting.
Reserve both phases before collection. Use a fresh single-use directory and ledger;
no resume, retry, allocation borrowing, extra game or training update.

Each phase uses the existing four-team pool and `scheduled_match(0..23,4)`:
all six unordered pairs, both assignments and challenger sides (four games each).
Use frozen original REINFORCE c0 against RandomLegalAgent, policy seed 260911 for
both phases, unchanged per-game 300-turn/60-second caps. This pool contains Wrap,
Clamp and Hyper Beam. Engine randomness is **not** paired by the policy seeds.
Win counts are accounting only; do not infer an instrumentation performance effect.

Before collection, implement/review the small opt-in harness that uses
`recording_environment`, fresh `AcceptanceLocalPlayer` instances per battle and
`close_acceptance_players`. Check build/source/config hashes at start and end;
preserve the historical startup binding and runtime checks through a strictly
separate derived-build path, not a relaxed historical doctor. Freeze that harness,
both engine inventories, exact policy/team hashes and this specification in the
new directory. Required retained c0 is
`runs/reinforce-main/checkpoints/c0.json`, SHA-256
`f7734489bce5d74ce2dedffd8ab274a8483810a03e09b48a26ea0ebf28d44287`.
Missing inputs or failed preflight stop before requesting games.

Original phase uses the original engine and client behavior. Instrumented phase
adds the private token/evidence path, preserving both policies. Verify exact
same-snapshot policy probabilities, draws, legal IDs and commands through retained
replay; compare original/derived methods offline on the captured current requests
where their required state can be represented without inventing hidden state.
Do not demand identical battle trajectories or reconstruct a missing private state.

For live contract coverage require at least one fully linked ordinary move,
ordinary switch, forced replacement, Wrap continuation, Clamp continuation and
Gen 1 fight normalization. Record Recharge/Struggle if encountered. Also verify
both sides' independent journals, correct original-slot/current-position mapping,
sealed streams, zero altered policy inputs, retained warning audit, and exact
commit indices. Missing coverage means **partial verification**, even if all games
complete; it never authorizes extra games or a claim that the missing case passed.
Rejection/undo/duplicate/reconnect mutation coverage remains offline unless a later
explicitly frozen functional script exercises it within these same 48 slots.

Caps/timeouts/crashes/cleanup forfeits never become wins or normal terminal rewards.
Retain their raw evidence and reasons. Stop on an unexpected protocol/error warning,
nonfinite inference, recording integrity failure, policy-boundary leak, failed
cleanup or phase/aggregate budget exhaustion. An ordinary cap may continue the next
independent scheduled game only after verified cleanup; no retries. Unrequested
slots remain never-started, distinct from requested incomplete games.

Only after both clients stop may the validator read/join private streams and end
logs. Reports must separate structural integrity, accepted/committed counts,
missing/unknowns and actual executed announcements. Confirm private evidence is
absent from public memory and spectator routes using file mutation/replay checks.
Hash inputs before/after and verify all owned processes/listeners are gone.
Report actual requests, terminal outcomes, caps/failures, normalization coverage,
file sizes, phase/total seconds, CPU/RSS and audit results.

Even full live success authorizes **no training eligibility change** and cannot
recover the historical 144 excluded episodes. Any such change needs a separate
mathematical/eligibility review and versioned regression tests.
