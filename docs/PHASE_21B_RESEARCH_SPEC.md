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


## FINAL PRE-ANALYSIS INFERENCE ADDENDUM

PHASE 21B HUMAN GATE RESOLUTION — FINAL INFERENCE ADDENDUM

The lead architect is resolving the remaining Phase 21B classification-
affecting methodology BEFORE any Phase 21B research data is accessed.

Existing Phase 21B specification commit:

e95871b469079eefbeca6307e5de58cb285b0dd1

Existing specification SHA-256:

b39874a48c07009fdb0598273d8bed20356f9beb340f0b9a98e4cb3b4151cac3

No Phase 21B research results have been observed.

Therefore the following definitions are prospectively frozen now.

==================================================
0. UPDATE AND REFINGERPRINT THE SPECIFICATION
==================================================

Append a section to:

docs/PHASE_21B_RESEARCH_SPEC.md

titled:

FINAL PRE-ANALYSIS INFERENCE ADDENDUM

Record every definition below.

Then:

1. recompute SHA-256 for the complete specification
2. commit with:

"Freeze Phase 21B inference and classification rules"

3. record:
   - previous spec commit
   - new spec commit
   - previous SHA-256
   - new SHA-256
4. require clean working tree
5. only then access Phase 21B research data

No methodology may change after the run begins.

==================================================
1. B3 PATH-RISK FAMILY
==================================================

Primary B3 estimand:

median_widening_ratio

where:

widening_ratio =
    max_pre_50pct_convergence_widening
    / abs(initial_residual)

Primary null:

H0:
population median widening_ratio > 0.25

Alternative:

H1:
population median widening_ratio <= 0.25

This is a ONE-SIDED screening test for manageable median widening.

Use deterministic trading-day block bootstrap.

Also report the preregistered descriptive criteria:

p90 widening_ratio <= 1.00

and

P(widening_ratio > 1.00) <= 0.10

These two are pass/fail screening criteria, not separate hypothesis tests.

B3 FDR family contains the four pair-level primary median-widening tests.

For any aggregate result, report it descriptively and separately.

==================================================
2. B4 ECONOMIC-MOVEMENT FAMILY
==================================================

Primary B4 estimand:

median_stress_multiple

for favourable native target-leg movement at 60 minutes.

stress_multiple =
    favourable_native_movement
    / frozen_round_trip_STRESS_cost

Primary null:

H0:
population median stress_multiple < 2.0

Alternative:

H1:
population median stress_multiple >= 2.0

Use one-sided trading-day block bootstrap.

B4 FDR family contains the four pair-level 60-minute tests.

The already frozen descriptive economic criteria remain mandatory:

median stress_multiple >= 2.0

P(stress_multiple >= 1.0) >= 0.60

P(stress_multiple >= 2.0) >= 0.50

P(stress_multiple >= 4.0) >= 0.25

For economic materiality to PASS, the pair must:

1. survive B4 FDR
AND
2. satisfy all four descriptive economic criteria

Do not test each descriptive criterion separately.

==================================================
3. B5 PAIRWISE-ATTRIBUTION FAMILY
==================================================

Pairwise analysis remains decomposition of the existing Phase 21A
target-event population.

For each ordered target/contributor relation define:

pairwise_delta =
    P(target_contribution > contributor_contribution)
    -
    P(contributor_contribution > target_contribution)

using only convergent events where the two contributions can be compared.

Ties within EPS are excluded from the numerator comparison but remain
reported.

Primary null for target-dominance direction:

H0:
pairwise_delta <= 0

Alternative:

H1:
pairwise_delta > 0

For common-catch-up direction use the symmetric test:

H0:
pairwise_delta >= 0

Alternative:

H1:
pairwise_delta < 0

Do NOT run both directional alternatives and pick whichever wins.

Choose the direction prospectively from the aggregate B1 mechanism:

- if B1 indicates TARGET reversal dominance, test target-dominance direction
- if B1 indicates COMMON catch-up dominance, test contributor/common-dominance direction
- if B1 indicates no material dominance, B5 is descriptive only and no pairwise-dominance inferential claim is permitted

B5 FDR family includes all ordered target/contributor relations tested under the one selected direction.

==================================================
4. B6 REGIME-STABILITY FAMILY
==================================================

B6 is NOT a superiority test.

It is a stability test of the already selected aggregate mechanism.

Let:

delta_primary =
    aggregate target-minus-common mechanism proportion difference

For each subgroup g:

delta_g =
    subgroup target-minus-common mechanism proportion difference

Define:

stability_deviation_g =
    abs(delta_g - delta_primary)

Primary B6 null:

H0:
stability_deviation_g >= 0.10

Alternative:

H1:
stability_deviation_g < 0.10

Use one-sided trading-day block bootstrap.

Apply this to:

- each calendar year
- each leave-one-year-out estimate
- each non-empty session
- each non-empty volatility regime

B6 FDR family contains all subgroup stability tests.

A subgroup is considered materially stable only if:

1. FDR q < 0.05
AND
2. dominant mechanism category does not change

The overall mechanism-stability screen passes only if:

- at least 4 of 5 calendar years pass
- all 5 leave-one-year-out estimates pass
- at least 75% of non-empty session groups pass
- at least 75% of non-empty volatility groups pass

==================================================
5. B7 METHOD-B ROBUSTNESS FAMILY
==================================================

Use the frozen Method B residual definition.

Let:

delta_A =
    Method A target-minus-common mechanism difference

delta_B =
    Method B target-minus-common mechanism difference

Define:

method_difference =
    abs(delta_B - delta_A)

Primary null:

H0:
method_difference >= 0.10

Alternative:

H1:
method_difference < 0.10

Use one-sided trading-day block bootstrap.

B7 FDR family contains the four pair-level tests at 60 minutes.

Method B qualitative agreement requires BOTH:

1. pair-level method_difference < 0.10 with FDR q < 0.05
2. Method B dominant mechanism category matches Method A

Overall Method B robustness passes if at least 3 of 4 pairs pass and none shows the opposite materially dominant mechanism.

==================================================
6. NUMERICAL DEFINITION OF "PREDOMINANT"
==================================================

Delete the vague word "predominantly" from the classification logic.

Use these exact rules.

For all eligible events at 60 minutes define proportions:

p_target
p_common
p_both
p_ambiguous
p_nonconvergent

A SINGLE mechanism is "modal" only if it has the largest proportion.

It is "materially modal" only if:

its proportion exceeds the second-largest category by >= 0.10.

For mixed/other structure define:

p_mixed_other =
    p_both + p_ambiguous + p_nonconvergent

Mixed/other evidence is considered predominant if:

p_mixed_other >= 0.60

This threshold is now frozen.

==================================================
7. PAIRWISE CONTRADICTION RULE
==================================================

"Pairwise evidence does not contradict the mechanism" is now defined numerically.

For TARGET_REVERSAL aggregate mechanism:

pairwise evidence PASSES if:

- at least 4 of the 6 unordered pair summaries have target-oriented sign consistent with target reversal
- none of the six shows a materially opposite effect of >= 0.10 in the common-catch-up direction after FDR

For COMMON_CATCH_UP aggregate mechanism:

symmetric rule.

For MIXED_CONVERGENCE:

pairwise evidence PASSES if:

- no single pairwise relation shows a materially opposite dominant mechanism >= 0.10 that survives B5 FDR
- at least 4 of 6 unordered pair summaries are qualitatively mixed or weak rather than strongly one-sided

For NO_ACTIONABLE_MECHANISM:

pairwise evidence is descriptive only.

==================================================
8. REVISED CLASSIFICATION HIERARCHY
==================================================

Replace the earlier ordering with this mutually exclusive decision tree.

Apply in this exact order.

------------------------------------------
STEP 1 — VALIDITY
------------------------------------------

If any required Phase 21B component is missing:

PHASE_21B_INCOMPLETE

STOP.

------------------------------------------
STEP 2 — PROSPECTIVE ESCALATION
------------------------------------------

If ALL prospective criteria are satisfied:

PROSPECTIVE_RELATIVE_VALUE_HYPOTHESIS_JUSTIFIED

Then return externally:

HUMAN_GATE_REQUIRED_PROSPECTIVE_HYPOTHESIS

Do not access holdout data.

------------------------------------------
STEP 3 — TARGET REVERSAL
------------------------------------------

Assign:

TARGET_REVERSAL_PHENOMENON

if ALL:

- p_target - p_common >= 0.10
- B1 target-dominance survives FDR
- target is materially modal OR p_target is at least 0.10 above p_common
- B6 stability screen passes

Economic feasibility is NOT required for this phenomenon classification.

------------------------------------------
STEP 4 — COMMON CATCH-UP
------------------------------------------

Assign:

COMMON_CATCH_UP_PHENOMENON

if ALL symmetric conditions hold:

- p_common - p_target >= 0.10
- B1 common-dominance survives FDR
- common is materially modal OR p_common is at least 0.10 above p_target
- B6 stability screen passes

------------------------------------------
STEP 5 — MIXED CONVERGENCE
------------------------------------------

Assign:

MIXED_CONVERGENCE_PHENOMENON

if convergence remains robust from Phase 21A AND either:

A.
p_both is the modal mechanism category

OR

B.
abs(p_target - p_common) < 0.10
AND
p_target + p_common + p_both >= 0.40

OR

C.
p_mixed_other >= 0.60
AND
p_both >= max(p_target, p_common)

This explicitly makes MIXED reachable.

------------------------------------------
STEP 6 — MECHANISM UNSTABLE
------------------------------------------

Assign:

MECHANISM_UNSTABLE

if:

a 10-percentage-point target/common dominance exists in aggregate

BUT

B6 stability fails

OR

relationship-stability screening fails.

------------------------------------------
STEP 7 — NO ACTIONABLE MECHANISM
------------------------------------------

Assign:

NO_ACTIONABLE_MECHANISM

if none of the above classifications apply.

This includes cases where:

- target/common difference is < 0.10
- BOTH is not sufficiently dominant for MIXED
- ambiguous/non-convergent mass is high
- mechanism inference fails FDR
- attribution is too diffuse

==================================================
9. PROSPECTIVE ESCALATION CRITERIA
==================================================

PROSPECTIVE_RELATIVE_VALUE_HYPOTHESIS_JUSTIFIED requires ALL:

1. phenomenon classification is one of:
   TARGET_REVERSAL_PHENOMENON
   COMMON_CATCH_UP_PHENOMENON
   MIXED_CONVERGENCE_PHENOMENON

2. relevant B1 inference survives FDR where directional dominance is claimed

3. B6 stability screen passes

4. concentration:
   top-10 absolute-event contribution <= 10%

5. B3 path risk passes:
   - median widening_ratio <= 0.25
   - p90 <= 1.00
   - P(widening_ratio > 1.00) <= 0.10
   - B3 primary inference survives FDR

6. B4 economic materiality passes for the relevant implementation interpretation

7. B5 pairwise contradiction rule passes

8. B7 Method B robustness passes

9. relationship-stability screen passes

10. no required component is incomplete

Failure of any one criterion prevents prospective escalation.

Retain the lower phenomenon classification instead.

==================================================
10. TWO-LEG ECONOMIC RULE
==================================================

If the mechanism is COMMON_CATCH_UP or MIXED and the plausible implementation would require two legs:

use combined STRESS friction:

stress_cost_A + stress_cost_B

Apply the same economic materiality thresholds:

median stress_multiple >= 2.0

P(>=1x) >= 0.60

P(>=2x) >= 0.50

P(>=4x) >= 0.25

For TARGET_REVERSAL, the primary economic screen is one-leg target cost.

Two-leg economics may still be reported descriptively.

==================================================
11. RELATIONSHIP-STABILITY PASS RULE
==================================================

Retain the previously frozen beta-drift criteria:

median absolute relative beta drift <= 0.25

p90 absolute relative beta drift <= 0.50

sign reversal in <=10% valid rolling estimates

annual residual volatility within 0.5x to 2.0x full-period reference

Overall relationship-stability PASSES only if:

- all four target-pair Method A relationship diagnostics pass
AND
- at least 3 of 4 Method B relationship diagnostics pass

No averaging away a failed target pair.

==================================================
12. NO FURTHER METHODOLOGY INVENTION
==================================================

These rules are intended to close the remaining classification ambiguity.

If a normal coding issue occurs:
fix it and continue.

If a genuinely new methodology ambiguity appears that can alter the research conclusion:
stop with HUMAN_GATE_REQUIRED.

Do not manufacture gates for implementation details.

==================================================
13. EXECUTE PHASE 21B
==================================================

After committing and fingerprinting this addendum:

implement and run the complete previously authorised Phase 21B analysis.

Use only:

[2019-01-01, 2024-01-01)

No 2024+.

No MT5.

No strategy.

No PnL.

No execution.

No optimisation.

Keep external stash isolated.

==================================================
14. FINAL RESPONSE
==================================================

Return only when validly complete as one of:

NO_ACTIONABLE_MECHANISM

MECHANISM_UNSTABLE

TARGET_REVERSAL_PHENOMENON

COMMON_CATCH_UP_PHENOMENON

MIXED_CONVERGENCE_PHENOMENON

or:

HUMAN_GATE_REQUIRED_PROSPECTIVE_HYPOTHESIS

If a genuine unresolved methodology issue remains, return:

HUMAN_GATE_REQUIRED

Include complete run provenance, tests, FDR results, stability results,
path risk, economics, pairwise evidence, Method B, relationship stability
and artifact validation.

Proceed by freezing this addendum first.
## PRE-ANALYSIS CONSERVATIVE OPERATIONALISATION

Following explicit instruction to continue, the remaining combination rules are frozen conservatively before data access:

- Aggregate B1 proportions and delta are pooled across all eligible target events. A directional aggregate B1 claim survives only when all four pair-level B1 tests survive BH FDR in that same direction. The pooled value is descriptive and is not added as a fifth B1 test.
- Method A has no estimated beta: its frozen common component is the equal-weight mean of three contributors. Its relationship coefficients therefore remain exactly one third, coefficient drift and sign reversal are zero by construction, and its relationship screen is determined by the already-required annual residual-volatility ratios.
- B4 remains the frozen four target-leg tests. Two-leg economics are descriptive because no two-leg inferential family was frozen. Consequently a COMMON_CATCH_UP or MIXED result cannot satisfy prospective B4 escalation; it retains its appropriate phenomenon classification. No additional test is invented.