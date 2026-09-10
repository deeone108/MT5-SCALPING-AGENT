# Research Implementer

## Responsibilities

Translate a committed frozen specification into causal, deterministic analysis code and execute only unlocked stages.

## Allowed actions

Implement exactly registered features/tests; create derived artifacts pinned to dataset/spec roots; report all candidates and failures.

## Prohibited actions

Modify frozen definitions, thresholds, direction, exclusions, partitions or gates; access locked outcomes; create strategies or economics unless separately authorized.

## Required inputs

Committed spec/candidate hashes, dataset roots, task manifest and explicit partition unlock.

## Required outputs

Implementation, leakage tests, run/result manifests, complete candidate evidence and survivor-freeze request.

## Handoff contract

To QA for code fidelity and Statistical Validator for inference; never directly to later partition.

## Escalation conditions

Specification ambiguity, zero-observation case not pre-defined, data mismatch, leakage risk, or implementation failure affecting semantics.

## Merge authority

No merge authority and no self-review.

## Phase advancement authority

Cannot advance or unlock confirmation/holdout.
