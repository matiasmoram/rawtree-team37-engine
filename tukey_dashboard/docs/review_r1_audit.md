# Review r1: numeric and logical coherence audit (team_37 Tukey dashboard)

Scope: build_dataset.py, render.py (data and texts as of 15/11 ~03:45 CET), views.py, dashboard_data.json, tidy CSVs, dist/index.html.
render.py was being edited while this audit ran, so it is cited by function name. Scripts: scratchpad `audit/a1..a4_*.py`.
Points already raised elsewhere are not repeated here: H1 "podi" wording, 98 vs 99 %, 40 vs 20 %, V3 loss-sign wording, V5 "1.801 k", V4 0,3 clamp, pre-registration timestamp.

## Verified correct (no action)
- Implied oracle: within each of 14 hours, every team gives the same oracle (spread ≤ 0,0001). The API `rank` is exactly the conversion order (0 mismatches in the last 4 h).
- Formulas: m̂ = (c − (1−s)b)/s, q, score = s·q, lost = (1−s)(0,5q+10), per_pp = 0,01(0,5q+10) and D1 (5,18 / 22,87) are all correct. D2 = 0,5·Δq and D6 = 0,25·Δq are correct.
- Power: MDE = 2,80·√(4σ²/n)·100 is correct for a 50/50 split with total n (Var of the difference = σ²/(n/2)·2), σ² on the 0–1 scale and Δ/100. n* = 31,36σ²/(Δ/100)² is consistent with it.
- Garwood interval: matches χ² (k=2: 0,242–7,225; k=10: 4,795–18,39; k=300: 267,0–335,9). The max cell count is 483, so exp(−λ) never underflows.
- Median polish: converged. Row and column residual medians are 0,0000 after 10, 50 and 200 iterations. Effects are stable to 0,001 (overall 0,604; slot effects +1,29/+0,32/−0,32/−0,44).
- Tukey hinges: depth is correct (n=14 gives v[3] and v[10]; n=17 gives v[4] and v[12]). Fences are at 1,5·H.
- Cross-view agreement holds for: 86 % median (V2 box = D1 = verdict), 22,9 (verdict = ledger D1), 54–68 hinges (V3 = ledger D2), 43 % slot 1 (verdict = V4), ×2,2, 0,19/0,56 (verdict = V5), and 48/56.

## BLOCKER
1. **The page has a concurrent A/B of fz-v9a vs fz-v10-nocorr but compares them unpaired.** (render.py `build_period`: `alts`/`med`, `gaps`, `d2`, `d6`; `texts` v3_sub "no és un A/B")
   - Evidence: both versions were served in the same 12 windows of 15 min (dg 00:15–03:15), at about 67/33 (19.538 vs 9.002 requests).
     - Paired Δconv: mean +0,132, median +0,139. Δq median +4,9. Pooled 2,216 vs 2,092.
     - z ≈ 1,9 with var_e; a paired t on the window differences gives t = 1,97 (k = 12).
   - What the page uses instead: unpaired medians over different window sets (57,8 vs 57,1, so Δ = 0,02).
     - That gives V5 "→ 1,8 M peticions", ledger D2 low end 0,4 and D6 low end 0,2.
   - Correct values: n* at Δ 0,13 is 31,36·0,002616/0,0013² ≈ 49 k requests (≈ 4,5 h). The stakes are D2 ≈ 2,4 and D6 ≈ 1,2.
   - The verdict ("not distinguishable in 2 h") still holds, since MDE 0,19 > 0,13. But the numbers are wrong ×6 in Δ and ×37 in n*. The practice data also favours fz-v9a, which strengthens D2.
   - Fix: for version pairs that share windows, compute the request-weighted within-window Δ. Use it for `d2`, `d6` and `gaps`. Change V3 sub to "nocorr vs fz-v9a: A/B concurrent 67/33, 12 finestres, Δ +0,13 (t≈2)". Keep "no és A/B" only for cf-rot, lgbm and ev-v2.
2. **A perfect D3 outcome shows as refuted.** (render.py `ledger_rows`, D3 outcome)
   - `(FN.get("bb_share") or 100) < 1` turns a 0,0 % re-buy share (the ban working perfectly) into 100, so the cell shows "✗ refutat".
   - Fix: `FN.get("bb_share") is not None and FN["bb_share"] < 1`.
3. **The final re-run is fragile, and the Final mode is gated on DB data.**
   - Gating (render.py `main`, build_dataset.py:301-316): `has_final` needs `D["final"]`, which exists only when the final DB `relation_slot` is non-empty.
     - If the DB extract fails, the toggle stays disabled and no ledger outcome is filled, even though the API final windows exist.
   - Crash paths in `build_period`/`texts`:
     - `sel_t = hours_us[-1]`: IndexError when there is no team_37 hourly row.
     - `rank_m = next(...)`: StopIteration if team_37 has on-time < 20 % in the last hour.
     - `N['worst_rank'] - N['best_rank']`: TypeError if the API `rank` is empty.
     - The verdict f-string uses `N['explore_cost']`: KeyError when slot-10 data is missing.
     - `ref_cold_ratio = st.median([])`: StatisticsError.
     - `order[0]`: IndexError when `keep` is empty.
     - build_dataset.py:73,161-162: KeyError on a missing baseline/reference row (partial final window).
   - Fix:
     - Build the final block from the API alone.
     - Make the DB-derived parts (V4, D3) optional and show "pendent".
     - Guard each lookup and print "–".
     - Smoke-test by running the pipeline on a 2-window synthetic final.

## MAJOR
4. **D1 outcome tests a weaker statistic than the one pre-registered.** (`ledger_rows`)
   - The prediction is "on-time ≥ 98 % a cada finestra" (15 min). The check is `FN["box_team_37"]["min"]`, the minimum of HOURLY on-time from field_hourly.
   - Fix: `min(r["on_time"] for r in W_final)`, exposed as `N["w_min"]`.
5. **D4 and D6 have no outcome logic, so after the final they stay "… pendent" forever.** (`ledger_rows`)
   - D6 is measurable from the API versions: the max version share per final window, or over the period.
   - D4 → "no mesurable" (spec §2.3 V6).
6. **H1 and V1 disagree on the model rank.** (`texts` h1 vs `build_period` rank_m)
   - H1 says "mateix model servit (#4 de 32 en qualitat)", which is the 01:00 hour.
   - V1 plots the 02:00 hour, where team_37 is #5 of 33 (`rank_m`=5, `n_plotted`=33). The jury will count 4 dots above us.
   - The hours also mix versions: 02:00 = fz-v9a 7.171 + nocorr 3.629; 01:00 = 2.936 + 1.410.
   - Fix: quote both ranks ("#4 de 32 a 01h, #5 de 33 a 02h"), or plot the worst hour.
7. **The identity residual is partly tautological, and m̂ uses on-time where served share is available.** (build_dataset.py `windows15` L100-103; `texts` v2_sub)
   - 12 of the 48 "dins ±0,05" windows have served share ≥ 99 %, where the residual is 0 by construction. On informative windows the count is 36/44 (82 %).
   - All 8 failures are positive (+0,06…+0,145): fallback requests convert above the window baseline. So m̂ overstates m by (1−s)(b′−b)/s for low-s teams (rivals and team_37 alike).
   - Served share ≠ on-time by up to 11,6 pp (ds 21:45: 38,8 vs 31,0), yet m̂ and q use on-time.
   - Fix: print "36 de 44 finestres informatives". Use served_share for team_37 m̂. Say that the whisker is not a CI.
8. **"CONFIRMATORI" is put on practice evidence.** (`page_body`: V2 and V4 sections; ledger D3)
   - These views show the same data that generated the hypotheses. Nothing is confirmatory before the final.
   - Fix: practice V2, V4 and D3 → EXPLORATORI. Use CONFIRMATORI only in Final mode, on pre-registered checks.
9. **D3 contradicts V4.** (`ledger_rows` D3 vs `texts` v4_sub)
   - The ledger says re-buys are banned ("ja aplicat") and predicts < 1 % of slots. V4 shows "Ja comprat: 2,1 % dels slots" (bb_share 2,087 %, 25.353 impressions).
   - Cause: `relation_slot` pools 12:09–03:07, which includes the hours before the 15:50 ban. `bought_before` also counts 60-day history buys (extract_db.py relation_slot multiIf).
   - Fix: split the extract at the ban time and show the post-ban share. Otherwise restate the prediction.
10. **V4 "×" factors are ratios of (rate + 0,5), not of rates.** (`build_period` col1, rel_labels, res_label; `texts` v4_sub)
    - "El slot 1 multiplica per 5,6 els slots 7–10": the raw rates are 6,54 vs 0,50 per 1.000, which is ×13,1; the (r+0,5) ratio is ×7,0.
    - The panel factors "×0,27 efecte" etc. have the same issue.
    - Fix: label them as effects on the log(compres/1.000+0,5) scale, or quote raw ratios.
11. **The "top-6" group contains artefacts and has three different definitions.** (`build_period` box; build_dataset.py:108; `field_rows`)
    - It has 9 hourly on-time values of 0 (ds 11h: 6 teams; ds 12h: 3), yet those teams' conversion (0,70–0,84) is above baseline (0,64–0,74). So 0 means "not reported", not 0 %.
      - They show as 9 outliers in the V2 box, and the grey band falls to 0 in those windows.
    - The three definitions:
      - The box is the top-6 by hourly conversion, excluding team_37 (5 or 6 rivals).
      - The band is the top-6 by 15-min conversion, including team_37.
      - The V1 "top6" labels are the top 2 rivals.
    - Fix: treat on_time==0 with conv ≠ b as missing. Use one definition (top-6 rivals by API rank in that hour).

## MINOR
12. **The power σ² is estimated across hours.** (build_dataset.py `power_curve` L259-269)
    - Across hours, hour and traffic drift is included. For the fixed baseline list, across-window var/request is 0,00320 vs 0,00136 within an hour.
    - The concurrent v9a/nocorr pairs give σ² ≈ 0,0028 within windows, which is consistent with 0,00262. So the MDE stands; cite this cross-check.
    - `p = 0.022` is hard-coded; use live_conv/100.
13. **The ruler hard-codes the baseline 0,58** (`texts` ruler; `explore_cost` fallback) instead of the median over hours of 100/(o_h−b_h) (spec §2.6#2). That median is 36,6 vs 36,3: same rounding today, but the number is free-typed.
14. **`explore_cost` mixes o_med (median over hours) with b_h (the selected hour's b = 0,523).**
    - D4 says "slots 9–10", but the cost covers slot 10 only, at 30 %. Slots 9+10 (0,494+0,445 per 1.000) give ≈ 0,50; the planned 5 % gives ≈ 0,04.
    - It also mixes realised purchases with the expected metric.
    - Fix: use the median of (o_h−b_h) and compute the cost for the decision as written.
15. **The loss formula ignores the cold component.** Fallback requests also lose cold points, so `loss_mean` and the D1 stakes are lower bounds; write "≥". The footer says "fred 10 (no inclòs)" but the titles do not.
16. **Spec §2.6#6 is not implemented.** `loss_conv_mean` is 2,92, while the hourly 0,5·(q_h − score_h) gives 3,31 (equal weights), a 12 % gap against the 2 % tolerance. Add the assert or explain the gap.
17. **The `score = s·q` assert is algebraically always true** (q comes from the same c and s). Assert against the published `progress` score instead.
18. **Free-typed numbers break "every number from N".** Examples: "p95 1,8–2,9 s/h", "10–45 ms", "72 % multi-versió", "0,69 a 1,36", "1,66 %" (units: % vs "/1.000" in the same sentence; 1,66 % = 16,6/1.000), `dq_conv` fallback 0.028, `n_final` 21600.
19. **The ledger sub-text does not match the table.**
    - It says "Ordenat per punts en joc", but D3 (no stake) sits 3rd, above D6 (8,0).
    - "Barra = escenari mitjà–pitjor" is true only for D1; D2 and D6 bars are min–max across alternatives.
    - The top of the D2 range is ev-v2-nocovis (15,9), which is not a final candidate (brief §5 D2). Restrict to the candidates.
20. **"Versió principal" is mislabelled.** The API team `model_version` ≠ the most-served version: the 00h and 01h hours are tagged fz-v10-nocorr while fz-v9a served 8.473/10.660 and 2.936/4.346. Use argmax(requests) from api_versions (build_dataset.py:120, 144).
21. **Missing oracles are imputed silently.** If final progress is hidden, the q values use the practice o_med (3,338) without any flag; ds 10–12h have no oracle either. Add an `oracle_imputed` flag and show it in the subtitle.
22. **Hard-coded conclusions and versions.**
    - The H1 else-branch always says "La fiabilitat és la palanca, no el model", whatever the data (wrong if the final runs at 99 %).
    - `LIVE_VERSION` is hard-coded, and `live = order[0]` silently picks another version.
23. **The V1 whisker carries no information at the selected hour.** At s = 99,98 % the ±1,8 q whisker is meaningless, and the "±0,05 bound" fails in 8 of 44 informative windows. Hide it when s > 0,95, or show it on the worst hour.
