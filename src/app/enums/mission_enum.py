from enum import Enum

class MissionType(str, Enum):
    DAILY_GOAL = "daily_goal"
    ALL_CLEAR_BONUS = "all_clear_bonus"
    ETC = "etc"

class MissionCategory(str, Enum):
    BODY = "body"
    HABIT = "habit"
    MIND = "mind"
