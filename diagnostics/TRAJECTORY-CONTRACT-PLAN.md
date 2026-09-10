# Retained trajectory contract audit

No games, training, production edits, new eligibility decisions, or historical writes.
Inputs: all recorded cells in `reinforce-main` and `actor-step-acceptance`.
Reproduce every REINFORCE decision on both sides/all phases; inspect every training
learner episode, including all exclusions. Historical integration/smoke games are
outside the evidence population. Metadata is used only after policy replay.

Verify existing manifests and strict loaders, record current/pinned source hashes,
compare immutable journals to merged decisions, replay seeded draws and frozen
probabilities, and rebuild the existing private labels without changing them.
Only compare engine entries at the same ordinal position. After the first mismatch,
even a later literal match remains an unknown suffix. Separate source-supported
normalization candidates from proof of exact request/acceptance correspondence.

Summarize exclusions by experiment/arm, opponent, batch, team assignment, outcome,
length and sampled/public context. These are descriptive associations, not causal
selection-bias estimates. Do not compute replacement training rewards.

Synthetic estimator tests use finite differences/exact enumeration, with a total
120-second wall limit. No model update function or battle collector is invoked.
Freeze original file hashes before analysis; compare them and directory inventories
afterwards. New outputs belong only in `runs/trajectory-contract-audit-20260910`;
new source is isolated under diagnostics/tests, with a separate audit document.
