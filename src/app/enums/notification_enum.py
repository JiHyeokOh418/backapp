from enum import Enum

class NotificationType(str, Enum):
    SCHEDULE = "schedule"
    NOTICE = "notice"
    SYSTEM = "system"
    REQUEST = "request"
    APPOINTMENT = "appointment"
    CHAT = "chat"
    CRISIS = "crisis"
