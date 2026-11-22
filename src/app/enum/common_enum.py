from enum import Enum


# 감정 6종 (emotion_analyses, diary_analyses 공용)
class Emotion(str, Enum):
    ANGER = "anger"
    JOY = "joy"
    ANXIETY = "anxiety"
    EMBARRASSMENT = "embarrassment"
    SADNESS = "sadness"
    HURT = "hurt"


# 척도 종류 (checklist_items, assessment_results 공용)
class Instrument(str, Enum):
    PHQ9 = "phq9"
    GAD7 = "gad7"
    ISI = "isi"
    BDI2 = "bdi2"
