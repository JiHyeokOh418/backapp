from enum import Enum

class AppointmentContactMethod(str, Enum):
    PHONE = "phone"
    CHAT = "chat"

class AppointmentStatus(str, Enum):
    BOOKED = "booked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"
    WAITING = "waiting"
    IN_PROGRESS = "in_progress"

class AppointmentKind(str, Enum):
    TREATMENT = "treatment"
    PSYCH_TEST = "psych_test"

class AppointmentVisitType(str, Enum):
    FIRST = "first"
    RETURN = "return"

class AppointmentBookingSource(str, Enum):
    PATIENT_APP = "patient_app"
    AUTO_AFTER_VISIT = "auto_after_visit"
    DOCTOR = "doctor"
