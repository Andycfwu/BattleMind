# Gen1HeuristicAgent v1

This is the frozen V2 reference. V3 adds a separate switch-aware policy described in [PREDICTION.md](PREDICTION.md); this policy's implementation and weights are unchanged.

The policy in `src/battlemind/heuristic.py` is a handwritten, deterministic utility rule. It accepts one frozen `DecisionSnapshot`, scores only its legal choices, and returns the first maximum in legal request order. It has no access to the runner, team files, account names, other client's request, or submitted action. RandomLegalAgent and MaxBasePowerAgent remain unchanged comparison policies.

These constants were chosen as understandable starting rules and frozen before the reported comparisons. They were not fitted to data. The resulting number is **utility**, not damage, expected HP loss, a simulator evaluation, or win probability.

## Move rules

For an ordinary damaging move, start with:

`listed base power × nominal accuracy × STAB × Gen 1 type effectiveness`

STAB is 1.5 when the user's visible species has the move's type. The type chart and species/move tables are public game knowledge from the pinned library, checked against the official engine by `doctor`. If no foe has been revealed, the type multiplier defaults to 1; it does not invent a species. Fixed integer hit counts multiply power (Double Kick has two); variable hit counts remain unmodeled.

| Rule | Utility adjustment / condition |
|---|---|
| Seismic Toss / Night Shade | `90 × nominal accuracy`, a utility constant; their Gen 1 immunity exception is checked against engine metadata |
| Super Fang | `70 × nominal accuracy`; outside the validated team pool, no broader support claim |
| Hyper Beam | Multiply by 0.7 for recharge cost; no prediction that it will KO and skip recharge |
| Explosion / Self-Destruct | Multiply by `0.25 + 0.65 × (1 − displayed HP fraction)`; penalize losing a healthy Pokémon |
| Recover / Soft-Boiled | At HP ≤55%, `45 + 170 × (1 − HP fraction)`; otherwise 0 |
| Rest | At HP ≤35%, or HP <75% with paralysis/burn/poison/toxic status, `140 × (1 − HP fraction) + 35 if curing one of those statuses`; otherwise 0 |
| Sleep move | `140 × nominal accuracy` only for a healthy foe with no revealed sleeping opponent; otherwise 0 |
| Paralysis move | `95 × nominal accuracy` only for a healthy foe; Thunder Wave gets 0 against Ground |
| Swords Dance / Amnesia / Agility | 95 at HP ≥70% when the corresponding **displayed** stage is below +2; otherwise 0 |
| Other status moves | 0; still selectable as a legal fallback |
| Engine Fight / Recharge / Struggle | 0 / 0 / 40; only if present in the request |

Recovery and Rest also avoid the engine's known Gen 1 failure when own missing HP is 255 or 511 and current HP is not a multiple of 256. This narrow check uses exact **own** request HP; it does not estimate opposing HP or reimplement healing. Sleep Clause handling is conservative: even a revealed Rest sleeper suppresses another sleep attempt, because the policy does not reconstruct who caused sleep.

## Switching

For the current Pokémon and each legal bench choice, compute a position utility:

`min(best known attack utility, 200) − 0.6 × min(revealed incoming attack utility, 300) + 40 × HP fraction − status penalty`

Incoming pressure uses only the active foe's previously announced damaging moves. If none are known, use the explicitly assumed utility 80. A known immunity stays 0. Unknown HP uses neutral fraction 0.5 for this position score. The status penalty is 70 for sleep/freeze and 15 for paralysis/burn. Bench offense uses known own moves; future PP availability is not modeled.

A voluntary switch needs position improvement **greater than 80**, and no own public switch/drag during the last two turns. Opening deployment at turn 0 does not trigger the cooldown. Its score is `best currently offered move utility + improvement − 80`; disallowed switches score −1000. This requires a substantial improvement before paying the turn cost and reduces repeated switching. The cooldown conservatively includes forced replacements and game-effect switches too.

A forced replacement ignores the threshold and cooldown and selects the highest position utility among actual legal switches. Ties always follow request order. Trapping and engine-required choices come from the adapter's request mapping; scoring cannot make a disallowed action legal.

## What the policy deliberately leaves uncertain

Raw HP numerator, denominator and precision are preserved in snapshots. Dividing public `54/100` for a utility calculation does not reconstruct exact opposing HP. Unknown moves, unrevealed team members, effective stats and Gen 1 derived counters remain unknown. Displayed boosts only gate setup; they are never converted to effective attack, defense or speed.

The heuristic does not calculate damage, speed order, critical-hit rates, accuracy-stage interactions, the Gen 1 1/256 miss behavior, status/stat reapplication, overflow, Counter, residual counters, trap duration, exact self-KO defense effects, or hidden move likelihoods. Nominal accuracy is just the public listed percentage. It ignores the wrapper's physical/special category because that table retains modern categories for some Gen 1 moves. Razor Leaf critical hits and Agility/Amnesia tactical value are therefore poorly represented. A switch evaluation also does not plan the opponent's next move.

## Explaining the contribution

`move_score()` states the move preferences, `position_score()` gives the switching approximation, and `scores()` compares actual legal actions and handles forced replacements. `choose()` returns the best semantic ID. Every heuristic decision records all candidate scores and a short reason, allowing a reviewer to explain a choice without claiming the score is physically exact.

The original work is this explicit scoring design and its integration with a tested information boundary. The engine supplies the game rules, and `poke-env` supplies networking and public data tables. The bounded comparisons in `STATUS.md` test behavior against two weak baselines; they do not validate every scoring term or establish competitive strength.
