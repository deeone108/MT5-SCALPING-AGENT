# MT5 Scalping Agent: Agent Governance

These instructions apply repository-wide. More specific instructions may narrow, but never relax, the constitution or safety policy.

## Governing order

1. Explicit human-owner direction
2. governance/PROJECT_CONSTITUTION.md
3. governance/SAFETY_POLICY.md and governance/DATA_ACCESS_POLICY.md
4. governance/RESEARCH_GATES.md
5. governance/AGENT_AUTHORITY_MATRIX.md
6. Assigned role charter under agents/
7. Task manifest

Conflicts fail closed and require escalation. Agents must identify their role in every task/result manifest.

## Orchestration model

The Project Orchestrator decomposes work into bounded tasks, assigns exactly one accountable role, records dependencies, and uses isolated Git worktrees. Agents may read shared committed baselines but write only in their assigned worktree. They must not modify another agent's worktree, active experiment artifacts, frozen specifications, or uncommitted user work.

Every task begins with a machine-readable task manifest and ends with a result manifest conforming to the schemas under governance/. Results cite inputs, commands, tests, artifacts, hashes, limitations, and requested transition. Handoffs are accepted explicitly; absence of objection is not acceptance.

Only the Project Orchestrator may advance a phase, and only after independent Statistical Validator, QA, and applicable Safety Reviewer gates pass. The Orchestrator cannot waive failed gates. LIVE activation additionally requires explicit human-owner approval recorded as an immutable approval artifact.

## Universal prohibitions

No agent may access locked or embargoed data, mutate a frozen experiment specification, convert a research result directly into LIVE trading, submit broker orders, enable order submission, bypass gates, weaken BACKTEST/DEMO/LIVE protections, expose credentials, or merge its own unreviewed work.

Research, validation, backtesting, and execution are separate phases. A statistically interesting result is not a strategy and a backtest is not authority to trade.

## Git isolation

Use one branch and linked worktree per task. Record base SHA, branch, worktree, expected paths, and allowed mutations. Preserve unrelated changes. Commits must be scoped and reviewable. No automatic merge to main: QA recommends; the Project Orchestrator authorizes a merge; a human owns protected-branch and LIVE decisions.
