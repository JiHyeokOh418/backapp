from enum import Enum

class AssessmentResultSource(str, Enum):
    AI_INTAKE = "ai_intake"
    SELF = "self"
    CLINIC = "clinic"
