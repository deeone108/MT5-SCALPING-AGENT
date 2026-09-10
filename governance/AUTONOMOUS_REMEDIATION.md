# Autonomous remediation loop

The Project Orchestrator may route a rejected review to an agent only when every finding is explicitly `agent_resolvable`. Review artifacts are immutable inputs and are copied by path and SHA-256 into each remediation descriptor.

`HUMAN_GATE_REQUIRED` is mandatory for authority changes, scope changes, 2024+ access, LIVE activation, frozen-artifact mutation, review bypass, or any finding not affirmatively classified agent-resolvable. Agent remediation is always no-data and produces a new superseding artifact; it never edits a frozen artifact.

Progress is evidence-based. A repeated finding fingerprint combined with an unchanged output hash or a non-material attempt is a deadlock and escalates to the human owner. There is no fixed low retry limit. State records the complete specification lineage, material attempts, preserved reviews, and the next legal transition so interruption can resume without inference.

Every remediation output returns to independent Statistical Validator and QA review. Approval cannot be synthesized, inherited, or bypassed by the producing agent.
