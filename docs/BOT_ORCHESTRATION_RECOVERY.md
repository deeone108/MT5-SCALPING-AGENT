# BOT orchestration recovery

## Purpose
Restore reliable bounded handoffs between implementation, CI, remediation, independent review and orchestration. This does not create execution authority.

## State machine
1. READY: task manifest exists and dependencies are satisfied.
2. DISPATCHED: one accountable implementation role is named.
3. CI_PENDING: a material commit exists and CI is required.
4. REVIEW_PENDING: CI evidence is available; independent QA/Safety/Statistical review is requested as applicable.
5. REMEDIATION_READY: every rejected finding is explicitly classified AGENT_RESOLVABLE.
6. HUMAN_GATE_REQUIRED: any authority/scope/data/frozen-methodology/execution/LIVE change, reviewer override, weakened safety control, or unresolved classification.
7. ACCEPTED: required independent gates pass.
8. CLOSED: orchestrator records the accepted transition.

## Recovery rules
- A dispatch is not progress. Progress requires a new material commit, durable result artifact, or independent review artifact.
- If a dispatched task has no material repository change or agent acknowledgement, the orchestrator may re-dispatch the same bounded task. It must not infer completion.
- Repeated finding fingerprint plus unchanged output hash is a deadlock and escalates to HUMAN_GATE_REQUIRED.
- Every implementation/remediation attempt returns to independent review. The producing agent cannot approve its own work.
- Missing task/result manifests are blocking governance defects, not optional documentation.
- CI success is necessary where specified but never substitutes for independent review.

## Safety invariants
- Research/evaluation authority only unless a later explicit human gate changes it.
- No broker order submission.
- LIVE remains disabled.
- DEMO authority is not introduced by orchestration.
- No protected/embargoed data access is granted.
- No automatic merge to protected/integration branches.
- Safety, QA and statistical gates cannot be inherited or synthesized.

## Heartbeats
For safety-relevant reviews, record a timestamped heartbeat on issue #4. A heartbeat records evidence reviewed, current authority, blockers and next legal transition. It is not an approval.

## Current recovery
PR #5 remains blocked. The asymmetric MT5 tick-value monetary-risk finding must be remediated by an implementation role, followed by CI and independent safety re-review. Existing BOT-06 P1 findings also remain unresolved until separately remediated and reviewed.
