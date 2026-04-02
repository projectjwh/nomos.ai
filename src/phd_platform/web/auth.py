"""Authentication — register, login, logout with session cookies."""

from __future__ import annotations

from uuid import uuid4

from hashlib import sha256
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from phd_platform.persistence.tables import StudentRow, UserRow, EnrollmentRow


async def register_user(
    db: AsyncSession,
    email: str,
    password: str,
    name: str,
    interests: str = "",
    disciplines: list[str] | None = None,
) -> UserRow:
    """Create a new user + student + enrollments."""
    import json

    # Create student record
    student_id = str(uuid4())
    student = StudentRow(
        id=student_id,
        name=name,
        email=email,
        interests=json.dumps([i.strip() for i in interests.split(",") if i.strip()]),
    )
    db.add(student)

    # Create user record
    user_id = str(uuid4())
    user = UserRow(
        id=user_id,
        email=email,
        password_hash=sha256(password.encode()).hexdigest(),
        student_id=student_id,
    )
    db.add(user)

    # Create enrollments
    for disc in (disciplines or []):
        db.add(EnrollmentRow(student_id=student_id, discipline=disc))

    await db.flush()
    return user


async def authenticate_user(
    db: AsyncSession, email: str, password: str
) -> UserRow | None:
    """Verify email + password. Returns UserRow or None."""
    result = await db.execute(select(UserRow).where(UserRow.email == email))
    user = result.scalar_one_or_none()
    if user and user.password_hash == sha256(password.encode()).hexdigest():
        return user
    return None
