from enum import Enum

class SessionChecklistSkipReason(str, Enum):
    USER_DECLINED = "user_declined"
    NOT_APPLICABLE = "not_applicable"
    UNCLEAR = "unclear"
