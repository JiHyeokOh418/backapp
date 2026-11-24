from enum import Enum

class RiskEventLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class RiskEventSource(str, Enum):
    RULE = "rule"
    CLASSIFIER = "classifier"
    GUARD = "guard"

class RiskEventStatus(str, Enum):
    OPEN = "open"
    REVIEWED = "reviewed"
    ON_HOLD = "on_hold"
    ESCALATED = "escalated"

class RiskEventOrigin(str, Enum):
    CHAT = "chat"
    ASSESSMENT = "assessment"
    TREND = "trend"
    INACTIVE = "inactive"
