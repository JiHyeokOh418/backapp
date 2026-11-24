from enum import Enum

class CareRequestMode(str, Enum):
    NEARBY = "nearby"
    DIRECT = "direct"

class CareRequestType(str, Enum):
    CONSULT = "consult"
    TREATMENT = "treatment"

class CareRequestStatus(str, Enum):
    REQUESTED = "requested"
    CONTACTING = "contacting"
    CONNECTED = "connected"
    BOOKED = "booked"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    CRISIS = "crisis"
