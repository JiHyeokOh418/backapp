from enum import Enum

class ChecklistItemAnswerType(str, Enum):
    BOOLEAN = "boolean"
    NUMBER = "number"
    SCALE = "scale"
    CHOICE = "choice"
    TEXT = "text"
