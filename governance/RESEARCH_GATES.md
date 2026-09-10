# Research Gates

## Gate sequence

1. **Proposal** — Research Lead supplies question, scope, candidate family, data needs, risks, and falsification criteria.
2. **Data readiness** — Data Engineer supplies schema, coverage, quality, license/access basis, immutable roots, and replay evidence. Statistical Validator or QA independently verifies.
3. **Experiment freeze** — Research Lead specification is committed and SHA-256 pinned before outcomes. It fixes partitions, features, horizons, sampling, inference, multiplicity, seeds, and advancement criteria.
4. **Implementation readiness** — Research Implementer supplies causal implementation and leakage/regression tests. QA reviews against the frozen specification.
5. **Discovery execution** — Only discovery data may be opened. All candidates and rejections are recorded.
6. **Survivor freeze** — Statistical Validator independently verifies discovery inference. The exact survivor set, thresholds, directions, and hashes are frozen.
7. **Confirmation unlock** — Project Orchestrator records a signed transition manifest permitting only frozen survivors to access confirmation.
8. **Confirmation freeze** — Results and remaining survivors are independently validated and hashed.
9. **Holdout unlock** — Project Orchestrator explicitly unlocks the named holdout after confirming no retuning.
10. **Holdout evaluation** — Frozen survivors run unchanged. Any post-access redesign is a new experiment with a new holdout.
11. **Experiment completion** — Statistical Validator, QA, and Safety where applicable sign results; Orchestrator assigns final classification.
12. **Phase closure** — Documentation and provenance are complete; Orchestrator closes or advances the phase.

A failed candidate stays failed. Statistical Validator cannot rescue it by changing direction, threshold, endpoint, exclusions, or test. Research Lead cannot use later partitions to revise the current experiment.

## Minimum handoff

Every gate handoff includes phase/run IDs, base commit, input hashes, artifacts, executed commands, test results, accessed partitions, rejected items, unresolved risks, and requested next state. Machine-readable manifests are authoritative; prose is explanatory.
