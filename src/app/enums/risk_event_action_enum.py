from enum import Enum

class RiskEventActionActorType(str, Enum):
    AI = "ai"
    SYSTEM = "system"
    DOCTOR = "doctor"

class RiskEventActionAction(str, Enum):
    SAFETY_QUESTION = "safety_question"
    NOTIFY_DOCTOR = "notify_doctor"
    REVIEW = "review"
    HOLD = "hold"
    ESCALATE = "escalate"
    NOTE = "note"
