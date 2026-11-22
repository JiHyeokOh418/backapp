from enum import Enum


# 사용자 역할
class UserRole(str, Enum):
    PATIENT = "patient"
    DOCTOR = "doctor"


# 소셜 로그인 제공자
class SocialProvider(str, Enum):
    KAKAO = "kakao"
    NAVER = "naver"
    GOOGLE = "google"


# 성별
class Gender(str, Enum):
    MALE = "male"
    FEMALE = "female"
