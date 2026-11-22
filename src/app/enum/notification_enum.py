from enum import Enum


# 알림 종류
class NotificationType(str, Enum):
    SCHEDULE = "schedule"
    NOTICE = "notice"
    SYSTEM = "system"
    REQUEST = "request"
    APPOINTMENT = "appointment"
    CHAT = "chat"
    CRISIS = "crisis"
