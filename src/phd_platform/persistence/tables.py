"""SQLAlchemy table definitions for the PhD Platform."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now()


class StudentRow(Base):
    __tablename__ = "students"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), default="")
    interests: Mapped[str] = mapped_column(Text, default="[]")  # JSON array
    strengths: Mapped[str] = mapped_column(Text, default="[]")  # JSON array
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    enrollments: Mapped[list[EnrollmentRow]] = relationship(back_populates="student", cascade="all, delete-orphan")
    module_scores: Mapped[list[ModuleScoreRow]] = relationship(back_populates="student", cascade="all, delete-orphan")
    tutoring_sessions: Mapped[list[TutoringSessionRow]] = relationship(back_populates="student", cascade="all, delete-orphan")
    capstones: Mapped[list[CapstoneRow]] = relationship(back_populates="student", cascade="all, delete-orphan")


class EnrollmentRow(Base):
    __tablename__ = "enrollments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[str] = mapped_column(String(36), ForeignKey("students.id"), nullable=False)
    discipline: Mapped[str] = mapped_column(String(50), nullable=False)
    current_level: Mapped[str] = mapped_column(String(20), default="foundation")
    enrolled_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    student: Mapped[StudentRow] = relationship(back_populates="enrollments")


class ModuleScoreRow(Base):
    __tablename__ = "module_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[str] = mapped_column(String(36), ForeignKey("students.id"), nullable=False)
    discipline: Mapped[str] = mapped_column(String(50), nullable=False)
    module_id: Mapped[str] = mapped_column(String(20), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    weakness_areas: Mapped[str] = mapped_column(Text, default="[]")  # JSON array
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    student: Mapped[StudentRow] = relationship(back_populates="module_scores")


class TutoringSessionRow(Base):
    __tablename__ = "tutoring_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[str] = mapped_column(String(36), ForeignKey("students.id"), nullable=False)
    module_id: Mapped[str] = mapped_column(String(20), nullable=False)
    conversation_history: Mapped[str] = mapped_column(Text, default="[]")  # JSON array
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    last_activity: Mapped[datetime] = mapped_column(DateTime, default=_now)

    student: Mapped[StudentRow] = relationship(back_populates="tutoring_sessions")


class CapstoneRow(Base):
    __tablename__ = "capstones"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    student_id: Mapped[str] = mapped_column(String(36), ForeignKey("students.id"), nullable=False)
    discipline: Mapped[str] = mapped_column(String(50), nullable=False)
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    abstract: Mapped[str] = mapped_column(Text, default="")
    paper_text: Mapped[str] = mapped_column(Text, default="")
    revision_number: Mapped[int] = mapped_column(Integer, default=0)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    student: Mapped[StudentRow] = relationship(back_populates="capstones")
    defenses: Mapped[list[DefenseResultRow]] = relationship(back_populates="capstone", cascade="all, delete-orphan")


class DefenseResultRow(Base):
    __tablename__ = "defense_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    capstone_id: Mapped[str] = mapped_column(String(36), ForeignKey("capstones.id"), nullable=False)
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    reviewer_verdicts: Mapped[str] = mapped_column(Text, default="{}")  # JSON dict
    feedback: Mapped[str] = mapped_column(Text, default="{}")  # JSON dict
    overall_pass: Mapped[bool] = mapped_column(Boolean, default=False)
    transcript: Mapped[str] = mapped_column(Text, default="[]")  # JSON array
    conducted_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    capstone: Mapped[CapstoneRow] = relationship(back_populates="defenses")


class QuestionBankRow(Base):
    """Pre-generated question bank — avoids LLM calls for diagnostics/assessments."""
    __tablename__ = "question_bank"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    module_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[str] = mapped_column(String(20), default="short_answer")
    difficulty: Mapped[int] = mapped_column(Integer, default=3)
    objective_index: Mapped[int] = mapped_column(Integer, default=0)
    correct_answer: Mapped[str] = mapped_column(Text, default="")
    rubric: Mapped[str] = mapped_column(Text, default="")
    partial_credit: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    # Cost optimization columns
    times_served: Mapped[int] = mapped_column(Integer, default=0)
    avg_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_served_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cooldown_hours: Mapped[int] = mapped_column(Integer, default=24)
    retired: Mapped[bool] = mapped_column(Boolean, default=False)


class LectureRow(Base):
    """Structured lecture content with embedded checkpoints."""
    __tablename__ = "lectures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    module_id: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    author_agent_id: Mapped[str] = mapped_column(String(50), default="")
    level_tier: Mapped[str] = mapped_column(String(20), default="foundation")  # foundation/undergraduate/masters/doctoral
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=30)
    # Structured content stored as JSON array of blocks
    # Each block: {"type": "exposition"|"checkpoint"|"worked_example"|"try_it"|"reflection",
    #              "content": "...", "question_id": null|int, ...}
    content_blocks: Mapped[str] = mapped_column(Text, default="[]")
    prerequisites_summary: Mapped[str] = mapped_column(Text, default="")
    learning_objectives: Mapped[str] = mapped_column(Text, default="[]")  # JSON array
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class LectureProgressRow(Base):
    """Tracks how far a student has progressed through a lecture."""
    __tablename__ = "lecture_progress"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[str] = mapped_column(String(36), ForeignKey("students.id"), nullable=False)
    module_id: Mapped[str] = mapped_column(String(20), nullable=False)
    blocks_completed: Mapped[int] = mapped_column(Integer, default=0)
    blocks_total: Mapped[int] = mapped_column(Integer, default=0)
    checkpoint_scores: Mapped[str] = mapped_column(Text, default="[]")  # JSON array of {block_idx, score}
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    last_activity: Mapped[datetime] = mapped_column(DateTime, default=_now)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)


class IntegrityEventRow(Base):
    __tablename__ = "integrity_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[str] = mapped_column(String(36), ForeignKey("students.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    session_type: Mapped[str] = mapped_column(String(20), default="")
    module_id: Mapped[str] = mapped_column(String(20), default="")
    elapsed_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    flag_reason: Mapped[str] = mapped_column(Text, default="")
    event_metadata: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class ConceptEngagementRow(Base):
    __tablename__ = "concept_engagement"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[str] = mapped_column(String(36), ForeignKey("students.id"), nullable=False)
    module_id: Mapped[str] = mapped_column(String(20), nullable=False)
    concept: Mapped[str] = mapped_column(String(200), nullable=False)
    engagement_depth: Mapped[int] = mapped_column(Integer, default=1)
    evidence: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class LLMUsageRow(Base):
    __tablename__ = "llm_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    tier: Mapped[int] = mapped_column(Integer, default=2)
    provider: Mapped[str] = mapped_column(String(20), default="")
    model: Mapped[str] = mapped_column(String(50), default="")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    purpose: Mapped[str] = mapped_column(String(30), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class UserRow(Base):
    """Web authentication — bridges to existing StudentRow."""
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    student_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("students.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PlacementResultRow(Base):
    __tablename__ = "placement_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[str] = mapped_column(String(36), ForeignKey("students.id"), nullable=False)
    discipline: Mapped[str] = mapped_column(String(50), nullable=False)
    starting_level: Mapped[str] = mapped_column(String(20), nullable=False)
    gap_modules: Mapped[str] = mapped_column(Text, default="[]")  # JSON array
    diagnostic_scores: Mapped[str] = mapped_column(Text, default="{}")  # JSON dict
    assessed_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
