from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, status
from app.repository.mypage_repository import MypageRepository, get_mypage_repository
from app.schema.mypage_schema import (
    LinkedDoctorResponseDTO,
    MyProfileResponseDTO,
    MyProfileUpdateDTO,
    MypageProfileCardDTO,
    MypageSummaryResponseDTO,
    UserSettingResponseDTO,
    UserSettingUpdateDTO,
)

KST = timezone(timedelta(hours=9)) # UTC+9


# 마이페이지 비즈니스 로직, 예외 처리, 트랜잭션 관리
class MypageService:

    def __init__(self, repo: MypageRepository):
        self.repo = repo


    # 회원이 없으면 404
    async def _get_user_or_404(self, user_id: int):
        user = await self.repo.find_user(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="회원이 존재하지 않습니다."
            )
        return user


    # 설정 행이 없으면 기본값으로 응답한다. (모델 기본값과 동일하게 유지)
    async def _get_setting_dto(self, user_id: int) -> UserSettingResponseDTO:
        setting = await self.repo.find_setting(user_id)
        if not setting:
            return UserSettingResponseDTO(hide_stats=False, share_with_doctor=True)
        return UserSettingResponseDTO.model_validate(setting)


    # 마이페이지 메인 요약
    async def get_summary(self, user_id: int) -> MypageSummaryResponseDTO:
        user = await self._get_user_or_404(user_id)
        today = datetime.now(KST).date()
        # 가입일부터 오늘까지 (가입 당일 = 1일째)
        days_together = (today - user.created_at.astimezone(KST).date()).days + 1

        return MypageSummaryResponseDTO(
            profile=MypageProfileCardDTO(
                nickname=user.nickname,
                today=today,
                days_together=days_together
            ),
            setting=await self._get_setting_dto(user_id)
        )


    # 내 정보 조회 (기본 정보 + 연결된 진료 + 공유 설정)
    async def get_profile(self, user_id: int) -> MyProfileResponseDTO:
        user = await self._get_user_or_404(user_id)
        relations = await self.repo.find_linked_doctors(user_id)

        linked_doctors = [
            LinkedDoctorResponseDTO(
                doctor_id=doctor.id,
                name=doctor.name,
                nickname=doctor.nickname,
                started_at=relation.started_at
            )
            for relation, doctor in relations
        ]

        return MyProfileResponseDTO(
            id=user.id,
            email=user.email,
            nickname=user.nickname,
            name=user.name,
            gender=user.gender,
            birth_date=user.birth_date,
            linked_doctors=linked_doctors,
            setting=await self._get_setting_dto(user_id)
        )


    # 내 정보 수정 (닉네임, 이름, 생년월일, 성별)
    async def update_profile(self, user_id: int, dto: MyProfileUpdateDTO) -> MyProfileResponseDTO:
        # exclude_unset=True: 요청에 보내지 않은 컬럼은 제외
        updated = await self.repo.update_user(user_id, dto.model_dump(exclude_unset=True))
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="회원이 존재하지 않습니다."
            )
        return await self.get_profile(user_id)


    # 설정 조회
    async def get_setting(self, user_id: int) -> UserSettingResponseDTO:
        await self._get_user_or_404(user_id)
        return await self._get_setting_dto(user_id)


    # 설정 수정 (숫자·기록 현황 숨기기, 의사 공유)
    async def update_setting(self, user_id: int, dto: UserSettingUpdateDTO) -> UserSettingResponseDTO:
        await self._get_user_or_404(user_id)
        setting = await self.repo.upsert_setting(user_id, dto.model_dump(exclude_unset=True, exclude_none=True))
        return UserSettingResponseDTO.model_validate(setting)



def get_mypage_service(repo: MypageRepository = Depends(get_mypage_repository)) -> MypageService:
    return MypageService(repo)
