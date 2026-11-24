from fastapi import Depends, HTTPException, status
from app.repository.user_repository import UserRepository, get_user_repository
from app.models.user_model import User
from app.enums.user_enum import UserSocialProvider
from app.schema.user_schema import UserCreateDTO, UserClaimDTO, UserResponseDTO, UserUpdateDTO


# 예외처리, 서비스가 드러나도록 이름을 선정해서 제작
# 트랜잭션 관리
class UserService:

    def __init__(self, repo: UserRepository):
        self.repo = repo


    # 회원 조회(id)
    async def get_user_by_id(self, id: int) -> UserResponseDTO:
        found_user = await self.repo.find_user_by_id(id)

        if not found_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="회원이 존재하지 않습니다."
            )

        return UserResponseDTO.model_validate(found_user)


    # 회원 조회(social_provider, social_id) - 없으면 None
    async def get_user_by_social(self, social_provider: UserSocialProvider, social_id: str) -> User | None:
        return await self.repo.find_user_by_social(social_provider, social_id)


    # 소셜 회원가입
    async def join(self, user: UserCreateDTO) -> UserClaimDTO:
        return await self.repo.create_user(user)


    # 회원 정보 수정
    async def update_user(self, id: int, user: UserUpdateDTO) -> UserResponseDTO:
        # dto -> dict
        # exclude_unset=True: 요청에 보내지 않은 컬럼은 제외
        update_data = user.model_dump(exclude_unset=True)
        updated_user = await self.repo.update_user(id, update_data)

        if not updated_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="회원이 존재하지 않습니다."
            )

        return UserResponseDTO.model_validate(updated_user)


    # 회원 탈퇴
    async def withdraw(self, id: int) -> None:
        is_withdrawn = await self.repo.withdraw_user(id)

        if not is_withdrawn:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="회원이 존재하지 않습니다."
            )



# 레포지토리 주입 팩토리 함수
def get_user_service(repo: UserRepository = Depends(get_user_repository)):
    return UserService(repo)
