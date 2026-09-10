# Reproducible QA test environment

The repository's authoritative dependency declaration is `pyproject.toml`.
It requires Python `>=3.10,<3.13`, documents Python 3.12 as the intended
version, and provides pytest through the `dev` optional dependency:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Reviewers must invoke pytest through the selected interpreter rather than
relying on a shell-level `pytest` command. This proves which environment ran
the suite and avoids accidentally selecting an interpreter without the dev
extra.

For an isolated linked worktree that does not contain its own `.venv`, the
already-provisioned primary-worktree environment may be reused without
installing dependencies or writing into the review worktree:

```powershell
Set-Location -LiteralPath 'C:\Users\derek\Desktop\Vcodeee-ph22b-remediation-001'
& 'C:\Users\derek\Desktop\Vcodeee\.venv\Scripts\python.exe' -m pytest `
  tests/orchestration/test_phase22b_remediation.py `
  tests/orchestration/test_runtime.py `
  tests/orchestration/test_integrated_state.py `
  tests/governance/test_agent_orchestration_design.py -q
```

Before accepting the evidence, QA records the interpreter and pytest version:

```powershell
& 'C:\Users\derek\Desktop\Vcodeee\.venv\Scripts\python.exe' -c `
  "import sys, pytest; print(sys.executable); print(sys.version); print(pytest.__version__)"
```

This procedure does not open market data. It does not authorize dependency
installation, research execution, backtesting, PnL calculation, or access to
any locked partition. A missing compatible environment is an environment
failure and must not be reported as a passing QA review.
