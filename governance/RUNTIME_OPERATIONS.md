# Orchestration Runtime Operations

Repository JSON artifacts, not conversational memory, are authoritative. Start by reading `AGENTS.md`, `governance/state/project_state.json`, `governance/memory/project_ledger.json`, the assigned task manifest, and the matching role charter.

## Role entrypoints

- Project Orchestrator: `Act as Project Orchestrator. Read AGENTS.md and governance/state/project_state.json. Operate only through valid manifests.`
- Any worker: `Execute <task-id> as <role>. Read AGENTS.md, agents/<role>.md, project state, project ledger, and the task manifest. Stop on any authority, hash, data, or safety mismatch.`
- Reviewers: `Review <task-id> independently as <review-role>. Do not modify implementation or frozen methodology. Produce a hashed result verdict.`

## CLI

Run `python -m mt5_scalping_agent.orchestration --help`. No LIVE command exists. `advance-phase` validates every frozen completion condition and cannot authorize LIVE.

## Recovery

Inspect the persisted task, process table, Git worktree, and last result. Without process evidence, transition stale `RUNNING` to `UNVERIFIED_INTERRUPTED`; never infer success. Dirty or failed worktrees are preserved.

## Evidence-aware tests

A missing ignored/local evidence artifact is `REQUIRED_EXTERNAL_EVIDENCE_MISSING`, distinct from `REGRESSION_FAILURE`. This classification does not turn the test green or weaken its assertion. The registry modules depend on ignored `reports/chronological_validation` evidence that is not materialized in a clean linked worktree.
## Frozen design review

For research-design tasks, `FROZEN_PENDING_REVIEW` means the author has completed and hash-frozen the design, but the task remains open and implementation locked. A COMPLETE author result does not imply gate approval. The onward path is independent `VALIDATING` then `REVIEWING`; rejection and blocking fail closed.
