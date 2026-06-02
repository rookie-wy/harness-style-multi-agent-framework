"""数据访问层"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from .models import User, Conversation, Note, Reminder
from ..auth.security import get_password_hash, verify_password


class UserRepository:
    @staticmethod
    async def create(db: AsyncSession, username: str, password: str, email: str = None) -> User:
        user = User(
            username=username,
            email=email,
            hashed_password=get_password_hash(password)
        )
        db.add(user)
        await db.flush()
        return user

    @staticmethod
    async def get_by_username(db: AsyncSession, username: str) -> Optional[User]:
        result = await db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def authenticate(db: AsyncSession, username: str, password: str) -> Optional[User]:
        user = await UserRepository.get_by_username(db, username)
        if not user or not verify_password(password, user.hashed_password):
            return None
        return user


class ConversationRepository:
    @staticmethod
    async def save(
            db: AsyncSession, user_id: int, session_id: str,
            user_input: str, assistant_reply: str, routed_skills: List[str]
    ) -> Conversation:
        conv = Conversation(
            user_id=user_id,
            session_id=session_id,
            user_input=user_input,
            assistant_reply=assistant_reply,
            routed_skills=",".join(routed_skills) if routed_skills else ""
        )
        db.add(conv)
        await db.flush()
        return conv

    @staticmethod
    async def get_user_history(
            db: AsyncSession, user_id: int, limit: int = 50
    ) -> List[Conversation]:
        result = await db.execute(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


class NoteRepository:
    @staticmethod
    async def create(db: AsyncSession, user_id: int, content: str, category: str = "general") -> Note:
        note = Note(user_id=user_id, content=content, category=category)
        db.add(note)
        await db.flush()
        return note


class ReminderRepository:
    @staticmethod
    async def create(db: AsyncSession, user_id: int, content: str, trigger_at) -> Reminder:
        from datetime import datetime, timedelta
        if isinstance(trigger_at, int):
            trigger_at = datetime.utcnow() + timedelta(minutes=trigger_at)
        reminder = Reminder(user_id=user_id, content=content, trigger_at=trigger_at)
        db.add(reminder)
        await db.flush()
        return reminder