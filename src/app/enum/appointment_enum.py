from enum import Enum


# 예약 연락 수단
class ContactMethod(str, Enum):
    PHONE = "phone"
    CHAT = "chat"


# 예약 상태
class AppointmentStatus(str, Enum):
    BOOKED = "booked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"
    WAITING = "waiting"
    IN_PROGRESS = "in_progress"


# 예약 종류
class AppointmentKind(str, Enum):
    TREATMENT = "treatment"
    PSYCH_TEST = "psych_test"


# 초진 / 재진
class VisitType(str, Enum):
    FIRST = "first"
    RETURN = "return"


# 예약 생성 경로
class BookingSource(str, Enum):
    PATIENT_APP = "patient_app"
    AUTO_AFTER_VISIT = "auto_after_visit"
    DOCTOR = "doctor"


# 예약 변경 종류
class ChangeType(str, Enum):
    RESCHEDULE = "reschedule"
    CANCEL = "cancel"


# 예약 변경 요청자
class RequestedBy(str, Enum):
    PATIENT = "patient"
    DOCTOR = "doctor"


# 일정 종류
class ScheduleType(str, Enum):
    COUNSELING = "counseling"
    APPOINTMENT = "appointment"
    EXAM = "exam"
    NOTICE = "notice"
    PERSONAL = "personal"
