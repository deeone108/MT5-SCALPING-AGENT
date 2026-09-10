# Agent Authority Matrix

| Role | Design | Implement | Validate | Merge recommendation | Phase advance | Safety veto | LIVE approve |
|---|---|---|---|---|---|---|---|
| Project Orchestrator | Coordinate | Manifests only | Gate completeness | Yes | **Sole agent authority** | No | No |
| Research Lead | Research specs | No production execution | Cannot self-validate | No | Recommend only | No | No |
| Data Engineer | Dataset plans | Data pipelines | Data checks, not predictive claims | No | No | No | No |
| Research Implementer | No post-freeze redesign | Frozen experiments | Implementation checks | No | No | No | No |
| Statistical Validator | Inference review | Independent validation tooling | **Independent statistics** | Validation sign-off | No | Reject only; no redesign | No |
| Backtesting Engineer | Approved simulation plans | Backtests | Backtest correctness | No | No | No | No |
| Risk & Safety Reviewer | Safety controls | Safety tests/policies | **Execution safety** | Required for safety changes | No | **Yes** | No |
| QA / Code Reviewer | Review plan | Test/review tooling | **Independent code/reproducibility** | **Yes** | No | Escalate | No |
| Documentation Agent | Information architecture | Accepted documentation | Link/provenance checks | No | No | No | No |
| Human owner | Direction | Explicitly authorized | May commission review | Protected-branch control | May approve/decline | Resolves escalation | **Required** |

Merge requires author handoff, independent QA approval, all domain sign-offs, and Project Orchestrator authorization. Authors never approve their own work. Safety-related changes additionally require a non-veto result. No automatic merge to main is permitted by this design.
