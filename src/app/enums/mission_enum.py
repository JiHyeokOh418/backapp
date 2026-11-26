from enum import Enum

class MissionType(str, Enum):
    DAILY_GOAL = "daily_goal"
    ALL_CLEAR_BONUS = "all_clear_bonus"
    ETC = "etc"

class MissionCategory(str, Enum):
    BODY = "body"
    HABIT = "habit"
    MIND = "mind"

# 자동 완료 목표 - id가 아니라 이름으로 찾음.(tests/seed_base_data.py 의 이름과 같아야 한다) 
# (마음이와 대화하기, 마음 기록, 한 줄 일기 쓰기)
AUTO_MISSION = {"chat": "마음이와 대화하기", "emotion":"마음 기록", "diary": "한 줄 일기 쓰기"}
AUTO_MISSION_NAMES = set(AUTO_MISSION.values())
