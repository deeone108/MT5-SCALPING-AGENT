# Reusable Codex Skill Architecture

Skills are versioned governance workflows, not authority grants. Each skill package contains a SKILL.md, JSON input/output schemas, templates, deterministic validation script, tests, and version/hash metadata. Invoking a skill never expands the caller's role or data access.

| Skill | Owner role | Required independent consumer | Core output |
|---|---|---|---|
| experiment-freeze | Research Lead | Statistical Validator and QA | committed spec, SHA-256, candidate registry |
| dataset-validation | Data Engineer | QA or Statistical Validator | coverage/quality report and dataset roots |
| leakage-audit | Statistical Validator | QA | causal-access and partition-isolation verdict |
| holdout-unlock | Project Orchestrator | Research Implementer | signed unlock manifest tied to survivor/spec hashes |
| experiment-completion | Statistical Validator | Project Orchestrator | result classification and complete provenance |
| regression-validation | QA | Project Orchestrator | scoped/full test evidence and review verdict |
| phase-closure | Project Orchestrator | Documentation Agent | final state manifest and handoff index |

Skills must be idempotent where practical, fail closed on missing hashes or permissions, emit machine-readable results, and never read a locked partition merely to validate that it is locked. The future implementation location is .codex/skills/<skill-name>/; this design phase intentionally defines contracts without installing or activating automation.
