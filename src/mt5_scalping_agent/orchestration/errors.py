class OrchestrationError(RuntimeError):
    """Fail-closed control-plane error with a stable machine code."""
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")

DATA_ACCESS_GATE_DENIED = "DATA_ACCESS_GATE_DENIED"
AUTHORITY_DENIED = "AUTHORITY_DENIED"
HUMAN_GATE_REQUIRED = "HUMAN_GATE_REQUIRED"
INVALID_TRANSITION = "INVALID_TRANSITION"
MANIFEST_INVALID = "MANIFEST_INVALID"
RESULT_REJECTED = "RESULT_REJECTED"
WORKTREE_POLICY_DENIED = "WORKTREE_POLICY_DENIED"