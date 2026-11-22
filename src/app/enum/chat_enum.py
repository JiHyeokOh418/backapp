from enum import Enum


# 채팅 세션 상태
class SessionStatus(str, Enum):
    SCHEDULED = "scheduled"
    ACTIVE = "active"
    ENDED = "ended"
    ABANDONED = "abandoned"
    MISSED = "missed"
    CANCELLED = "cancelled"


# 세션 종료 사유
class SessionEndReason(str, Enum):
    USER = "user"
    COMPLETED = "completed"
    TIMEOUT = "timeout"
    SAFETY = "safety"


# 세션 요약 생성 상태
class SummaryStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"
    SKIPPED = "skipped"


# 세션 종류
class SessionType(str, Enum):
    COUNSELLING = "counselling"
    INTAKE = "intake"


# 메시지 작성 주체
class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


# 메시지 시스템 기록 상태
class SystemRecordStatus(str, Enum):
    OK = "ok"
    PARTIAL = "partial"
    FAILED = "failed"


# 메시지 입력 방식
class InputType(str, Enum):
    TEXT = "text"
    VOICE = "voice"


# LLM 호출 목적
class LlmPurpose(str, Enum):
    REPLY = "reply"
    SUMMARY = "summary"


# LLM 응답 파싱 상태
class ParseStatus(str, Enum):
    OK = "ok"
    RETRIED_OK = "retried_ok"
    FAILED = "failed"


# 안전 필터 위치 (입력 / 출력)
class GuardGate(str, Enum):
    IN = "in"
    OUT = "out"


# 안전 필터 결과
class GuardResult(str, Enum):
    PASS = "pass"
    SAFE_MODE = "safe_mode"
    BLOCKED = "blocked"
