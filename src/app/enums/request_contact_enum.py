from enum import Enum

class RequestContactStatus(str, Enum):
    SENT = "sent"
    AVAILABLE = "available"
    DECLINED = "declined"
    NO_RESPONSE = "no_response"
