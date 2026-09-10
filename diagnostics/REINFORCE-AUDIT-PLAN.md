# Retained REINFORCE audit plan (no collection)

This audit reads the single consumed `runs/reinforce-main` experiment and its
48-game engineering smoke. It does not start Showdown, fit any model on retained
data, alter production behavior, or write into historical artifact directories.
Outputs go to fresh `runs/reinforce-audit-20260909`; production/document input
hashes and original manifests are checked before and after. Current clean source
is commit d1f86c2; the original main source manifest matches it byte-for-byte for
its frozen source closure. Diagnosis files live outside that closure.

1. Verify all original artifact hashes and checkpoint compatibility, phase keys,
   recorded source/configuration, selection and frozen rollout identities.
2. Independently reconstruct recorded softmax, sampling, terminal targets, losses,
   gradient sums and saved parameter differences. No new historical checkpoint is
   saved. Existing private-commitment auditing is run read-only as a separate check.
3. Analyze every final player-a snapshot with c0/c3/c6/c9/c12 on identical inputs,
   plus initial-versus-V2 behavior. Report KL(c0 || cK), reverse KL, TV, entropy,
   maximum probability, greedy/common-draw differences and request/situation groups.
   Historical final games are now diagnostic data, never a future untouched test.
4. Analyze all training player-a decisions/episodes, admitted and excluded: return,
   value/advantage distributions, episode-weighted and decision-weighted summaries,
   early/middle/late contributions, signal cancellation, mask/exploration and
   class/context losses. No proposed update is selected or applied from these data.
5. Enumerate all 70 unknown-commitment exclusions and the cap. Use exact first
   mismatch, lengths, engine context, public history, outcomes and batch/team/opponent
   groupings. Never search ahead to invent alignment or replace historical targets.
6. Representative decisions are chosen by deterministic first occurrence in
   final selected-arm run order: first loss versus each V2/V5; first common-draw
   disagreement; first selected recovery, switch, status, setup and engine action.
   Include the first recovery while already above the V2 recovery threshold when
   present. Overlapping selections are allowed and recorded. Outcomes/events shown
   afterward are hindsight for review only, not policy inputs or counterfactual wins.
7. One fixed synthetic check suite, seed 460901: analytic derivatives at nonzero
   weights, correctly rewarded two-action preference, two observable contexts,
   variable masks, four-step terminal-only reward, opposite player returns and
   clipping/projection. Effective toy dimensions are 2 state × 3 action features,
   zero-padded only to exercise the actual production gradient/update functions.
   Four learning tasks use 80 batches × 32 episodes and fixed main SGD rates
   (actor30/value.1); delayed episodes have four steps, others one. Success cutoffs
   are .85 consistent action, .80 context/variable-mask/delayed-first choice.
   These tests are not Pokémon performance evidence. Record every result and stop
   if 100s wall or CPU is consumed, leaving 20s below the 120s user ceiling. No
   repeats or hyperparameter tuning to make a failed task pass. Fresh malformed
   checkpoint fixtures test loaders; originals never change.

Independent mathematical comparisons use finite differences of log-softmax and
value squared loss, rather than a second copy of the production derivative. Shared
features are fixed; actor and value coefficients are disjoint. The value baseline
is detached in the actor loss. Discount is one; actor sums within episodes and
averages episodes with the fixed /100 factor, critic averages decisions.

The final report separates confirmed defects from limitations/hypotheses and
proposes exactly one new experiment, without executing it. V6 remains incomplete;
the richer learner's historical lack of demonstrated improvement is preserved.
