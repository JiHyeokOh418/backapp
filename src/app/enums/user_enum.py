from enum import Enum

class UserRole(str, Enum):
    PATIENT = "patient"
    DOCTOR = "doctor"

class UserSocialProvider(str, Enum):
    KAKAO = "kakao"
    NAVER = "naver"
    GOOGLE = "google"

class UserGender(str, Enum):
    MALE = "male"
    FEMALE = "female"
