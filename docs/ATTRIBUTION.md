# Original work and reuse

- [Pokémon Showdown](https://github.com/smogon/pokemon-showdown) supplies all game rules, validation, legal requests, resolution, and outcomes. It is reused under MIT; its license remains in `.local/pokemon-showdown/LICENSE`. BattleMind is a player, not a new simulator.
- [`poke-env`](https://github.com/hsahovic/poke-env) supplies team packing, network/client orchestration, and request/battle parsing. It is reused under MIT; its installed distribution retains its license. The selected version is in `configs/versions.json`.
- The maximum-listed-base-power idea appears in the official [`poke-env` quickstart](https://poke-env.readthedocs.io/en/stable/examples/quickstart.html). BattleMind implements it through its own sanitized policy interface and calls it **MaxBasePowerAgent**, with deterministic ties and explicit fallbacks. It is not a novel strategy, a damage estimator, or an imported strong agent.
- RandomLegalAgent uses Python's standard library RNG with a separate seed per policy/game. It is a standard random legal-action baseline.
- The four `ou-v1-*` / `ou-v2-*` team fixtures were assembled for this project from familiar Gen 1 OU species and moves, then validated by the selected engine. The original two files were preserved. They were not copied from a named competitor's team export. No originality, optimized-team, or metagame-coverage claim is made; their species and moves are common game knowledge.
- Gen1HeuristicAgent is a project-specific handwritten utility design using familiar power/accuracy/STAB/type concepts and explicit status/healing/switch rules. Its arbitrary constants are documented in `HEURISTIC.md`; no strong-agent code, learned weights or exact damage calculator were imported. Public move/species/type data comes from `poke-env` and is checked against Showdown. The recovery-failure guard follows the pinned official engine's Gen 1 move source.
- BattleMind's implementation work consists of the immutable observation schema, public-only projection, stable request mapping, heuristic and baseline boundary, separate journals, official committed-input alignment, conservative label/execution evidence, balanced schedule, bounded local runner/lifecycle, audit metadata, error accounting, and behavioral tests. The student should understand and be able to explain these contributions; generated code alone is not a claim of personal research novelty.

No external datasets, replay corpora, model checkpoints, or strong-agent code have been incorporated. Future Metamon or other integrations must record their exact version, license, sizes, and assumptions before use. Pokémon names and game content belong to their respective rights holders.

V3 adds project-written audited dataset joins, battle-level splits, constant and conditional frequency estimation, mixture utility scoring, frozen-artifact audits and controlled benchmarks. Beta/Laplace smoothing, shrinkage toward a global frequency, Brier score, log loss, calibration bins, Wilson intervals and bootstrap resampling are standard statistical methods, not claimed as novel algorithms. Counts are estimated from the project's local M2 games; no classifier or externally trained model was imported. Handwritten rules and empirical estimates are explicitly distinguished in `PREDICTION.md`.

V4 implements standard L2 logistic regression and Newton optimization using the
already-pinned NumPy. The algorithm follows established likelihood/gradient/Hessian
methods, explained in [CMU's logistic regression notes](https://stat.cmu.edu/~cshalizi/dm/20/lectures/07/lecture-07.html)
and [regularization lectures](https://www.cs.cmu.edu/~mgormley/courses/10601-s25/slides/lecture10-reg.pdf).
No external implementation was copied and no optimizer novelty is claimed. The
project work is the observer-only feature design, train-only preprocessing,
audited data plumbing, safe frozen bundle, fair baseline fitting, common-scoring
integration, budget enforcement and empirical comparison. The classifier learns
from this project's recorded local choices. Fixed threshold opponents reuse V2's
utilities; they are simple project-written variants, not imported strong agents.

V5 implements a small antithetic random-direction finite-difference update using
NumPy's seeded generator and bounded parameter projection. This belongs to standard
black-box policy optimization; [Salimans et al. (2017)](https://arxiv.org/abs/1703.03864)
provides broader evolutionary-strategy context. BattleMind's two-round, four-parameter
Rademacher-direction method is not a reproduction of that paper's large experiments
or a novel optimizer, and no code/model was copied from it. It is not gradient-based
reinforcement learning. The project-specific work is defining an interpretable score
vector with an exactly equivalent control, preserving frozen prediction and information
boundaries, recording actual outcome-driven arithmetic updates, scheduling immutable
archived opponents, reserving separate selection/final budgets, validating safe
checkpoints and reconstructing the experiment from audited evidence. All V5 opponents
and checkpoints come from the project's own local runs and existing policies.

V6 uses standard residual adjustment, shrinkage, clipping and group-level bootstrap
ideas; it does not claim a novel model or import adaptation code. BattleMind's work
is the observer-only public evidence extractor, explicit proxy exclusions, immutable
memory summaries, opaque routing outside features, frozen common V4/V5 scorer,
same-snapshot shadow comparison, chronological reconstruction and persistent phase
budgets. No human profiles or external behavior data are used. The partial V6
development result is retained with its budget stop; final benefit is unverified.

The V6 acceptance repair changes bookkeeping and reports, not the adaptation
algorithm. It separates stopped phase clocks from reporting and planned/reserved
capacity from dispatched requests. The authorized replacement exposed a cap caused
by the frozen heuristic's handling of a frozen active Pokémon; it was not retuned
or rerun. Preserving that failure and distinguishing partial evidence from completed
acceptance are part of the project's reproducibility work, not claims of strength.
