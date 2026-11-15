# Iteration loop

The repeatable cycle for testing one hypothesis at a time against the current champion. One command runs the offline gate; the rest is discipline.

## Cycle (offline part takes ~2 minutes)

1. **Pick ONE hypothesis** from `docs/backlog.md` (or write a new one). Define it before looking at data: what changes, which segment it should help, what result would kill it.
2. **Register the arm** in `engine/policies/registry.py` with a descriptive name, existing arms untouched.
3. **Offline gate** — one command:

   ```powershell
   .venv/Scripts/python.exe scripts/iterate.py --champion <current-champion> --challengers <arm> `
       --since 2026-11-14T15:00:00 --until 2026-11-14T15:23:00
   ```

   It replays the window point-in-time (catalogue, recent buys, PIT carts), checks per-arm artifacts, and prints a decision table with paired user-clustered bootstrap intervals. Verdicts:

   - `CANDIDATE` — paired purchase-NDCG CI excludes 0 above the champion **and** n >= 30 reranked purchases **and** zero invalid lists **and** latency p95 far below the 3 s deadline. Justifies a bounded live trial.
   - `INSUFFICIENT EVIDENCE` — CI includes 0 or tiny-n. Keep collecting; do not promote.
   - `NO-GO` — CI excludes 0 below the champion.
   - `EXECUTION FAIL` — invalid lists or latency over deadline. Fix before any quality comparison.
   - `DIAGNOSTIC ONLY` — the arm has no rerank hooks (cf-*, lgbm-*, money-*, skibidy-*). Gate it with `scripts/evaluate_recent.py` (`online_trial_eligible`) or the organic/live evaluators instead, and watch support/latency here.
   - Read `artifact_warnings`: an arm with an empty/stale artifact silently degenerates to its base policy (e.g. a `recent_covis.json` built *after* the replay window is unusable in it — rebuild it as-of before `--since` with `scripts/refresh_signals.py`).

4. **Live trial, bounded**: expose the arm at 10-20% via `scripts/run_live.py` shards for a FIXED, predeclared window (60-90 min). Champion stays in the same window as control.
5. **Measure** on the fixed window: `scripts/analyze_windows.py` + `scripts/compare_leaderboard.py`, and `scripts/check_emitters.py` to confirm a single writer. Decide at the predeclared end; do not peek repeatedly.
6. **Record**: one paragraph in `docs/` (hypothesis, window, n, metric, decision, artifact paths under `logs/iteration_*.json`). Promote, kill, or park.

## Rules

- One change per cycle; champion and challenger never change in the same window.
- The replay verdict is a diagnostic on observed labels — it does not estimate the simulator's expected conversion.
- No automatic promotion: `promotion_gate` stays review-only by design.
- Windows must be mature (`--until <= now - 2min`) and single-writer before any comparison counts.
