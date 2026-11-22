from enum import Enum


# 수면 기록 입력 방식
class SleepSource(str, Enum):
    MANUAL = "manual"
    AUTO = "auto"
