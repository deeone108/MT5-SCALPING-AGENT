# MT5 Scalping Agent: Project Mission and Roadmap

## PROJECT_MISSION

Build a broker-safe, reproducible scalping research and engineering system that can progress from observed market phenomena to independently validated strategies, deterministic risk-controlled execution, and—only after explicit human-owner approval—limited LIVE readiness.

The mission is directional, not authority. It does not authorize data access, strategy creation, PnL analysis, broker connectivity, DEMO use, or LIVE trading. Authority exists only in `governance/state/project_state.json`, task manifests, partition-unlock records, and human approval artifacts.

## CURRENT_AUTHORITY

- Phase: `PHASE_22B_PENDING_DESIGN`; stage: frozen design approved, implementation not started.
- Frozen specification: `research/phase22b_spec_v6.json`; canonical SHA-256 `343b6918acb62a68065eb16ecfc7fd05704fe8a77695d8417f7f81062475d56d`.
- Purpose: retrospective mechanism validation of `P22A_SPR_ABS_15s_60s`, not strategy construction.
- Data: only the 2019–2021 retrospective-development partition is authorized for a future, separately manifested Research Implementer task. The task must bind the specification and dataset-root hashes and use the guarded resolver.
- Locked: 2022 and 2023. Forbidden: 2024+.
- Still prohibited: strategy rules, PnL, cost/profitability analysis, optimization, ML, broker orders, DEMO and LIVE activation.
- Safety state: BACKTEST-only protections remain enforced; `live_execution_authorized = false`.

## Roadmap and definitions of done

Each stage is entered only by Project Orchestrator transition after its listed evidence and independent gates pass. A later-stage mission item never grants current-stage authority.

| Stage | Purpose | Definition of done | Mandatory gate / human decision |
|---|---|---|---|
| 22B mechanism validation | Determine whether the Phase 22A spread-state observation survives raw-pip analysis and frozen confounder controls. | Frozen implementation matches v6; leakage and resolver tests pass; authorized partitions are processed sequentially; inference, failures, rejected explanations, hashes, and limitations are independently reproduced. | 2019–2021 is authorized. Separate Orchestrator unlocks are required for 2022 and then 2023. 2024+ remains forbidden. |
| Signal-candidate formation | Translate validated phenomena into prospective, falsifiable signal hypotheses without trading semantics. | Candidate registry is frozen with causal timestamps, direction-agnostic evidence inputs, abstention behavior, partitions, multiplicity, stability, failure criteria, and a fresh confirmation plan. | Human approval of a new Research Lead task; Statistical Validator review before data access. |
| Strategy specification | Define entries, exits, stops, targets and sizing only for an approved signal candidate. | Exact rules, timing, costs, risk limits, universe, parameters, rejection criteria and untouched evaluation windows are preregistered and hashed. | Explicit human approval to begin strategy design; independent Statistics, QA and Safety review. |
| Execution-model engineering | Implement deterministic simulation semantics; no broker submission. | Next-event timing, order lifecycle, fills, spread/slippage/commission, gaps, duplicates, missing ticks, rejects and audit logs have regression tests and replay evidence. | QA approval; Safety Reviewer non-veto. Broker order APIs remain prohibited. |
| Backtesting | Evaluate the frozen strategy under frozen base/stress assumptions. | Gross/cost/net results, MAE/MFE, drawdown, exposure, concentration and year/pair/regime breakdowns reproduce from pinned inputs; every failure is retained. | Orchestrator unlock of named backtest partitions after implementation review. |
| Robustness and prospective validation | Test stability without rescue tuning. | Frozen candidate survives temporal, pair, regime, perturbation, bootstrap/multiplicity and untouched prospective gates; failed candidates close unchanged. | Separate survivor freezes and partition unlocks; new human direction for any redesigned hypothesis. |
| AI evidence integration | Allow agents to consume reviewed evidence without creating trading authority. | Versioned evidence schema is non-actionable by default; deterministic policy validates provenance, eligibility and limits; agent outputs are advisory, attributable and reproducible. | QA and Safety approval. AI cannot promote a phenomenon, alter thresholds, or emit execution intent. |
| DEMO readiness | Exercise an already approved deterministic strategy in an isolated paper/demo environment. | Kill switch, credentials isolation, limits, idempotency, reconciliation, telemetry, incident response and rollback drills pass under zero-LIVE permissions. | Explicit human-owner DEMO approval plus Orchestrator, QA and Safety gates. |
| Forward validation | Observe frozen DEMO behavior prospectively with no retuning. | Minimum duration/sample, drift, operational reliability, risk-limit and reconciliation gates pass; all interventions are logged and invalidate affected evidence where specified. | Human continuation decision; Safety may veto. |
| LIVE readiness | Demonstrate technical readiness only; readiness is not activation. | Named commit/account scope, hard limits, expiry, rollback, monitoring, incident ownership, independent audit and residual-risk acceptance are complete. | Separate explicit human-owner LIVE approval is indispensable and never inferred or inherited. |

## Deterministic and AI boundary

Deterministic code owns data authorization, timestamps, feature calculations, eligibility, model matrices, statistical tests, multiple-testing correction, costs, simulation, risk limits, state transitions, order gating, hashing, audit logs and fail-closed behavior.

AI agents may coordinate authorized tasks, summarize accepted evidence, explain uncertainty, identify missing evidence, draft prospective specifications and recommend a gated next task. They may not reinterpret weak evidence as a signal, alter frozen rules, select favorable subsets, invent thresholds after results, decide trade direction, bypass deterministic validation, create `TradeIntent`, enable execution, or infer DEMO/LIVE authority.

## Global closure rules

- Invalid provenance, leakage, unexpected access, hash mismatch or nondeterminism produces an invalid/blocked run, never a favorable scientific classification.
- A failed hypothesis is retained and closed; redesign starts a new lineage and requires new data governance.
- Research evidence is not a signal; a signal is not a strategy; a backtest is not execution authority; LIVE readiness is not LIVE authorization.
- Every phase handoff records inputs, commits, hashes, accessed partitions, failures, tests, reviewers and the exact requested transition.
