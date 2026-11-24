from enum import Enum

class AppointmentChangeType(str, Enum):
    RESCHEDULE = "reschedule"
    CANCEL = "cancel"
