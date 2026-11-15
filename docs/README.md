# docs · decision record

Start with **[DECISIONS.md](DECISIONS.md)**: one table per phase, each decision with its evidence and source.

The other files are the point-in-time records those decisions cite. They were written on Saturday 14 November
about the team's earlier systems (`engine/`, `scripts/`, `t37m4/`). That code is no longer on `main`; paths such as
`engine/...` or `scripts/...` in these files refer to the git tag `archive-all-experiments-2026-11-15`:

```bash
git checkout archive-all-experiments-2026-11-15    # full repo before the cleanup
```

| File | What it records |
|---|---|
| [research.md](research.md) | Literature and public solutions reviewed before building |
| [review_2026-11-14.md](review_2026-11-14.md) | Practice review 16:15 CET: metric definition, serving decision |
| [review_20261114.md](review_20261114.md) | Codebase and live-system review 17:10 CET: issues by severity |
| [strategy_review_2026-11-14.md](strategy_review_2026-11-14.md) | Strategies prioritised for the final (17:53 CET) |
| [model_architecture_decision.md](model_architecture_decision.md) | Decision: one purchase ranker instead of many policies |
| [lgbm_cart_v2_2026-11-14.md](lgbm_cart_v2_2026-11-14.md) | Training report of `lgbm-cart-v2` and why it was not promoted |
| [live_ranker.md](live_ranker.md) | The live-feedback LightGBM ranker (`lgbm-recent`) |
| [recent_evaluation.md](recent_evaluation.md), [policy_replay.md](policy_replay.md) | Offline evaluation on recent feedback and point-in-time replay |
| [iteration.md](iteration.md), [cycle_log.md](cycle_log.md) | The iteration procedure and the result of each cycle |
| [experiments.md](experiments.md) | Traffic ownership, bounded exploration, promotion rules |
| [cartfirst.md](cartfirst.md), [contextual.md](contextual.md), [skibidy_design.md](skibidy_design.md) | Design notes of individual policies |
| [t37m4_thompson.md](t37m4_thompson.md), [t37m4_thompson_design.md](t37m4_thompson_design.md) | The Thompson-sampling model `t37-m4` |
| [backlog.md](backlog.md) | Open work as of Saturday evening |
