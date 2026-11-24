from enum import Enum

class ChatSessionStatus(str, Enum):
    SCHEDULED = "scheduled"
    ACTIVE = "active"
    ENDED = "ended"
    ABANDONED = "abandoned"
    MISSED = "missed"
    CANCELLED = "cancelled"

class ChatSessionEndReason(str, Enum):
    USER = "user"
    COMPLETED = "completed"
    TIMEOUT = "timeout"
    SAFETY = "safety"

class ChatSessionSummaryStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"
    SKIPPED = "skipped"

class ChatSessionType(str, Enum):
    COUNSELING = "counseling"
    INTAKE = "intake"

class ChatExpression(str, Enum):
    DEFAULT = "default"       # 기본
    SMILE = "smile"           # 미소
    BIG_SMILE = "big_smile"   # 활짝 웃음
    SAD = "sad"