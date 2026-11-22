from enum import Enum


# 진료 요청 방식 (주변 병원 / 의사 지정)
class RequestMode(str, Enum):
    NEARBY = "nearby"
    DIRECT = "direct"


# 진료 요청 종류
class RequestType(str, Enum):
    CONSULT = "consult"
    TREATMENT = "treatment"


# 진료 요청 상태
class CareRequestStatus(str, Enum):
    REQUESTED = "requested"
    CONTACTING = "contacting"
    CONNECTED = "connected"
    BOOKED = "booked"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    CRISIS = "crisis"


# 병원 연락 상태
class ContactStatus(str, Enum):
    SENT = "sent"
    AVAILABLE = "available"
    DECLINED = "declined"
    NO_RESPONSE = "no_response"
