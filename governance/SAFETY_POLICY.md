# Safety Policy

## Default posture

All research and data access are read-only with respect to brokers. BACKTEST is the default runtime. No agent is authorized to submit, modify, or cancel an order or position.

## Prohibited without exception by agents

Agents must not call order submission APIs, construct enabled trade requests, create pending orders, modify positions, enable execution flags, weaken environment gates, change BACKTEST/DEMO/LIVE protections, store credentials in artifacts, or infer LIVE authority from successful research/backtests.

Execution-shaped code is treated as safety-critical even when described as demo or test code. It requires Risk & Safety Reviewer review and veto clearance. Tests must prove fail-closed behavior and absence of unauthorized API calls.

## Environment transitions

BACKTEST to DEMO requires an approved phase plan, QA, Safety approval, and explicit human authorization. DEMO to LIVE requires a separate explicit human-owner approval naming commit, account scope, limits, expiry, and rollback. Approval is never inherited, implied, or permanent.

The Safety Reviewer may veto any change that adds execution capability, broadens credentials, weakens limits, obscures audit logs, or makes state ambiguous. Only the human owner may resolve a LIVE veto, and technical gates still remain mandatory.

## Incident rule

On unexpected broker interaction, credential exposure, protection mismatch, or execution-capable path: stop, preserve logs, disconnect safely if possible, do not retry, and escalate as a safety incident.
