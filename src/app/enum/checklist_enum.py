from enum import Enum


# 체크리스트 답변 형식
class AnswerType(str, Enum):
    BOOLEAN = "boolean"
    NUMBER = "number"
    SCALE = "scale"
    CHOICE = "choice"
    TEXT = "text"


# 세션 체크리스트 상태 (session_checklist, checklist_events 공용)
class ChecklistStatus(str, Enum):
    PENDING = "pending"
    DONE = "done"
    SKIPPED = "skipped"


# 체크리스트 건너뜀 사유
class SkipReason(str, Enum):
    USER_DECLINED = "user_declined"
    NOT_APPLICABLE = "not_applicable"
    UNCLEAR = "unclear"


# 척도 검사 출처
class AssessmentSource(str, Enum):
    AI_INTAKE = "ai_intake"
    SELF = "self"
    CLINIC = "clinic"
