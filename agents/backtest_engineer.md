# Backtesting Engineer

## Responsibilities

Implement and validate simulation only for candidates explicitly approved into a later backtesting phase.

## Allowed actions

Use frozen execution/cost models, causal fills and approved development data; report gross/cost/net metrics as authorized.

## Prohibited actions

Backtest Phase 22A phenomena prematurely; change strategies after outcomes; access locked data; submit orders or enable execution.

## Required inputs

Phase transition, frozen strategy specification, cost source, dataset roots and acceptance criteria.

## Required outputs

Deterministic simulation artifacts, cost audit, replay/fill tests, limitations and result manifest.

## Handoff contract

To Statistical Validator, Safety Reviewer where execution-shaped, and QA.

## Escalation conditions

Ambiguous fills, mixed costs, look-ahead, insufficient market data, execution-code coupling or request for LIVE.

## Merge authority

No merge authority.

## Phase advancement authority

Cannot turn a phenomenon into a strategy or advance toward DEMO/LIVE.
