# Phase 21B Mechanism Attribution and Economic Feasibility

Parent Phase 21A run: `reproduction_20260903T224000Z_860ce89`
Parent commit: `860ce8927134566fa4e88b98681b0f79cc167664`
Parent Phase 21A specification SHA-256: `e0a7d430196313c4634c44fc26fcaf4903a0d0358f150ee9efa7244796ee1232`
Phase 21B methodology freeze UTC: `2026-09-03T23:10:00Z`

## Boundaries and event universe

Use only `[2019-01-01, 2024-01-01)`. No 2024+, MT5, strategy, PnL, execution, optimisation, ML, Phase 22, or external-research stash. Method A is primary. Reproduce exactly each target pair's Phase 21A causal standardisation, leave-one-out residual, causal percentile, 90+ entries, frozen buckets, 60-minute deduplication, timestamp alignment, session, and volatility definitions. Event identities and counts must equal parent evidence. Analyse exact +5/+10/+15/+30/+60 minute timestamps; missing timestamps are unavailable.

Pairwise records do not create events. At each frozen target event, decompose the three existing contributors. Six unordered summaries aggregate both target/contributor orientations without deduplication.

## Arithmetic and labels

Let `R0` and `Rh` be residuals, `s=sign(R0)`, and `D=abs(R0)-abs(Rh)`. Define `target_contribution=-s*(target_z_h-target_z_0)`, `common_contribution=s*(common_z_h-common_z_0)`, and `remainder=D-target_contribution-common_contribution`. Reconstruction including remainder must hold within `EPS=1e-10`. Do not clip contributions.

For `D>0`: TARGET_REVERSAL means target contribution > EPS and common <= EPS; COMMON_CATCH_UP means common > EPS and target <= EPS; BOTH_CONTRIBUTE means both > EPS; otherwise NEITHER_OR_AMBIGUOUS. For `D<=0`, use NON_CONVERGENT. Target/common direction labels use positive, negative, or flat (`abs(c)<=EPS`). For convergent events only, signed target/common/remainder fractions divide by D without clipping or renormalising; report mean, median, p25, p75.

## Inference and stability

Primary B1 estimand at 60 minutes is `P(TARGET_REVERSAL)-P(COMMON_CATCH_UP)` over all eligible frozen events. Test one-sided H0 delta<=0 against H1 delta>0 using deterministic trading-day block bootstrap, 5,000 replicates. Report N, proportions, delta, 95% CI, raw p, BH q, survival. Material dominance requires absolute delta >= .10 plus relevant FDR survival. Material change means the dominant category changes or delta changes by >=.10.

Apply BH 5% separately: B1 primary; B2 5/10/15/30 robustness; B3 path risk; B4 economic movement; B5 pairwise attribution; B6 year/session/volatility stability; B7 frozen Method B robustness. Each estimand records its null and direction.

Report 2019-2023 and leave-one-year-out, frozen DST-aware sessions, frozen volatility (`LOW<.30`, `NORMAL [.30,.70)`, `HIGH [.70,.90)`, `EXTREME>=.90`), and frozen buckets (`90-95`,`95-99`,`99-100`). Concentration uses year/month/day/top5/top10; prospective requires top10 <=10%.

## Paths and economics

Use exact M5 residual paths to +60. Report initial and horizon residuals; elapsed time to 75/50/25%; zero cross; maximum widening and its time; and no 50% convergence. Pre-50% widening uses the path before first convergence, or all 60 minutes if none. Report median/p75/p90/p95/p99 and proportions above 10/25/50/100%. Manageable requires median<=.25, p90<=1, and P(>1)<=.10.

Measure target native favourable/adverse excursions, ordering, and times in pips for each horizon in the residual-reducing target direction. This is descriptive, not PnL.

Use canonical `config/cross_pair_cost_models.json`. Report favourable movement divided by BASE/STRESS round-trip friction and exceedance at 1/2/4/6/8x. Target economics pass only if median STRESS multiple>=2, P(>=1)>=.60, P(>=2)>=.50, P(>=4)>=.25. Two-leg combined friction is cost A plus cost B with no sizing assumption.

## Method B and relationships

Frozen Method B is rolling OLS with alpha of target z on other three z values, prior 5,760 M5 rows, current excluded, no imputation, residual actual-predicted. Repeat key attribution. Qualitative agreement means no material change.

For coefficients, `relative_beta_drift=abs(beta_period-beta_reference)/max(abs(beta_reference),.10)`. Stability requires median drift<=.25, p90<=.50, sign reversals<=10%, and every annual residual volatility within .5x-2x full reference.

## Completion and classification

Required artifacts: mechanism_by_horizon, target_movement, common_movement, joint_mechanism, contribution_fractions, path_geometry, adverse_widening, target_mfe_mae, pairwise_decomposition, one_leg_economics, two_leg_economics, year_analysis, leave_one_year_out, session_analysis, volatility_analysis, extremeness_analysis, concentration, bootstrap, fdr, method_b, relationship_stability. Missing any yields PHASE_21B_INCOMPLETE.

Classify in order: NO_ACTIONABLE_MECHANISM when no material target/common dominance and evidence is predominantly both/ambiguous/non-convergent; MECHANISM_UNSTABLE when aggregate dominance exists but year, leave-one-out, or relationship stability fails; TARGET_REVERSAL_PHENOMENON for stable FDR-surviving material target dominance; COMMON_CATCH_UP_PHENOMENON symmetrically; MIXED_CONVERGENCE_PHENOMENON when BOTH is modal among convergent events or both are material without ten-point dominance.

Override with internal PROSPECTIVE_RELATIVE_VALUE_HYPOTHESIS_JUSTIFIED only when coherent mechanism, inference, year/LOO stability, concentration, widening, STRESS economics, pairwise agreement, Method B, relationship stability, and completeness all pass. Externally return HUMAN_GATE_REQUIRED_PROSPECTIVE_HYPOTHESIS and do not access untouched data. Do not continue beyond Phase 21B.
