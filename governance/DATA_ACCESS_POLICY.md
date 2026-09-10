# Data Access Policy

## Classification

Data partitions are PUBLIC_METADATA, DEVELOPMENT, CONFIRMATION_LOCKED, HOLDOUT_EMBARGOED, or LIVE_SENSITIVE. Each dataset manifest records provider, license/access basis, interval, schema, unit hashes, root hash, and classification.

Agents receive least-privilege access. A task manifest names allowed dataset roots and temporal partitions. Unnamed partitions are forbidden.

## Embargo controls

Confirmation and holdout remain inaccessible until a Project Orchestrator transition manifest identifies the frozen survivor hash, specification hash, dataset root, permitted partition, responsible agent, and approval time. Directory knowledge or filesystem availability is not authorization.

Research Implementer must not enumerate, preview, count, sample, hash, or otherwise inspect locked outcomes. Data Engineer may maintain encrypted or access-separated partitions but cannot disclose them early. Statistical Validator audits access logs and provenance.

## Integrity

Never mix providers or dataset roots silently. No interpolation, repair, exclusion, deduplication, or timezone conversion occurs without a pre-registered rule and evidence. Boundary leaks are recorded. Derived artifacts carry their source roots and transformation hashes.

Credentials, account numbers, tokens, and personally identifying broker data are excluded from reports and commits.
