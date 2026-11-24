from enum import Enum

class PointHistoryType(str, Enum):
    EARN = "earn"
    SPEND = "spend"
    CANCEL = "cancel"
