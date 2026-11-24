from enum import Enum

class GuardCheckGate(str, Enum):
    A = "a"
    B = "b"

class GuardCheckResult(str, Enum):
    PASS = "pass"
    SAFE_MODE = "safe_mode"
    BLOCKED = "blocked"
