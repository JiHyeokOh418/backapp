from enum import Enum

class CareActionLogActionType(str, Enum):
    WATER = "water"
    SUNLIGHT = "sunlight"
    PAT = "pat"
    LULLABY = "lullaby"
    SNACK = "snack"
    WASH = "wash"
