from enum import Enum


# 아이템 분류
class ItemCategory(str, Enum):
    OUTFIT = "outfit"
    ACCESSORY = "accessory"
    FURNITURE = "furniture"
    BACKGROUND = "background"


# 아이템 보유 방식 (유일 / 중복)
class OwnershipType(str, Enum):
    UNIQUE = "unique"
    STACKABLE = "stackable"


# 미션 종류
class MissionType(str, Enum):
    DAILY_GOAL = "daily_goal"
    ALL_CLEAR_BONUS = "all_clear_bonus"
    ETC = "etc"


# 포인트 내역 종류
class PointHistoryType(str, Enum):
    EARN = "earn"
    SPEND = "spend"
    CANCEL = "cancel"
