from enum import Enum

class ScheduleType(str, Enum):
    COUNSELING = "counseling"
    APPOINTMENT = "appointment"
    EXAM = "exam"
    NOTICE = "notice"
    PERSONAL = "personal"
