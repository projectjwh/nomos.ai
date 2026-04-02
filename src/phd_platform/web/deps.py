"""FastAPI dependency injection — database sessions, auth, orchestrator."""

from __future__ import annotations

from typing import AsyncGenerator

from fastapi import Cookie, Depends, HTTPException, Request
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from phd_platform.config import get_settings
from phd_platform.curriculum.loader import CurriculumLoader
from phd_platform.llm.client import LLMClient, get_llm_client
from phd_platform.persistence.database import get_engine, get_session_factory
from phd_platform.persistence.repository import StudentRepository
from phd_platform.persistence.tables import UserRow

# Singletons
_curriculum: CurriculumLoader | None = None


def get_curriculum() -> CurriculumLoader:
    global _curriculum
    if _curriculum is None:
        _curriculum = CurriculumLoader()
        _curriculum.load()
    return _curriculum


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session."""
    factory = get_session_factory(get_engine())
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_repo(db: AsyncSession = Depends(get_db)) -> StudentRepository:
    """Get a repository bound to the current session."""
    return StudentRepository(db)


def get_llm() -> LLMClient:
    """Get the LLM client based on config."""
    return get_llm_client()


def get_serializer() -> URLSafeTimedSerializer:
    """Get the session cookie serializer."""
    settings = get_settings()
    return URLSafeTimedSerializer(settings.secret_key)


async def get_current_user_optional(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> UserRow | None:
    """Get the current user from session cookie, or None if not logged in."""
    settings = get_settings()
    session_token = request.cookies.get("session")
    if not session_token:
        return None

    serializer = get_serializer()
    try:
        user_id = serializer.loads(session_token, max_age=settings.session_max_age)
    except (BadSignature, SignatureExpired):
        return None

    result = await db.execute(select(UserRow).where(UserRow.id == user_id))
    return result.scalar_one_or_none()


async def get_current_user(
    user: UserRow | None = Depends(get_current_user_optional),
) -> UserRow:
    """Require an authenticated user. Raises 401 if not logged in."""
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user
