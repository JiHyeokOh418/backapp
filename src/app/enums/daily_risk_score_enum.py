from enum import Enum

class DailyRiskScoreTrendFlag(str, Enum):
    NONE = "none"
    RISING = "rising"
    MEDIUM_3DAYS = "medium_3days"
    INACTIVE_7DAYS = "inactive_7days"
