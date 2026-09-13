# Autonomous remediation loop

The Project Orchestrator may route a rejected review to an agent only when every finding is explicitly `agent_resolvable`. Review artifacts are immutable inputs and are copied by path and SHA-256 into each remediation descriptor.

`HUMAN_GATE_REQUIRED` is mandatory for authority changes, scope changes, 2024+ access, LIVE activation, frozen-artifact mutation, review bypass, or any finding not affirmatively classified agent-resolvable. Agent remediation is always no-data and produces a new superseding artifact; it never edits a frozen artifact.

Progress is evidence-based. A repeated finding fingerprint combined with an unchanged output hash or a non-material attempt is a deadlock and escalates to the human owner. There is no fixed low retry limit. State records the complete specification lineage, material attempts, preserved reviews, and the next legal transition so interruption can resume without inference.

Every remediation output returns to independent Statistical Validator and QA review. Approval cannot be synthesized, inherited, or bypassed by the producing agent.

## Human-owner autonomous chaining policy (2026-09-13)

For work affirmatively classified `AGENT_RESOLVABLE`, the Orchestrator continues the complete bounded remediation, independent-review, acceptance, and durable-launch chain without requiring a human relay between checkpoints. Each subtask still produces a committed, recoverable checkpoint. Review independence and all existing gates remain mandatory.

Codex does not continuously monitor long-running computation. After a detached worker has a persisted identity, PID, state, heartbeat, and durable logs, Codex stops; a later session resumes from repository state.

`HUMAN_GATE_REQUIRED` is reserved for new protected-data authority, material scientific-scope or frozen-methodology changes, strategy/PnL/execution/LIVE authority, reviewer overrides, or weakened safety controls. Platform availability and routine engineering defects are not human gates.