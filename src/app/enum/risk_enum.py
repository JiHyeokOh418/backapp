from enum import Enum


# 위험 수준
class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# 위험 탐지 출처
class RiskSource(str, Enum):
    RULE = "rule"
    LLM = "llm"
    EMOTION = "emotion"
    CLASSIFIER = "classifier"
    GUARD = "guard"


# 위험 이벤트 처리 상태
class RiskStatus(str, Enum):
    OPEN = "open"
    REVIEWED = "reviewed"
    ESCALATED = "escalated"


# 위험 이벤트 발생 원천
class RiskOrigin(str, Enum):
    CHAT = "chat"
    DIARY = "diary"
    ASSESSMENT = "assessment"
    TREND = "trend"
    INACTIVE = "inactive"


# 조치 주체 유형
class ActorType(str, Enum):
    AI = "ai"
    SYSTEM = "system"
    DOCTOR = "doctor"


# 위험 조치 종류
class RiskAction(str, Enum):
    SAFETY_QUESTION = "safety_question"
    NOTIFY_DOCTOR = "notify_doctor"
    REVIEW = "review"
    ESCALATE = "escalate"
    NOTE = "note"


# 일별 위험 추세 플래그
class TrendFlag(str, Enum):
    NONE = "none"
    RISING = "rising"
    MEDIUM_3DAYS = "medium_3days"
    INACTIVE_7DAYS = "inactive_7days"
