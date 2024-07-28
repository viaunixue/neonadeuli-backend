import secrets
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app.core.deps import get_db    
from app.repository.user_repository import UserRepository
from app.utils.common import get_unique_nickname
from app.models.user import User

class UserService:
    
    def __init__(self, db: AsyncSession):
        self.user_repository = UserRepository(db)

    # 임시 유저 생성
    async def create_temporary_user(self) -> User:
        nickname = await get_unique_nickname(self.user_repository.db)
        token = secrets.token_urlsafe(32)
        user = await self.user_repository.create_user(name=nickname, token=token)
        return user
    
    async def get_user_by_token(self, token: str) -> User:
        return await self.user_repository.get_user_by_token(token)