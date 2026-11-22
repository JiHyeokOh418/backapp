from enum import Enum


# 관리 메모 분류
class MemoCategory(str, Enum):
    CLINIC = "clinic"
    COUNSEL = "counsel"


# 진료실 종류
class RoomType(str, Enum):
    CONSULT = "consult"
    EXAM = "exam"
