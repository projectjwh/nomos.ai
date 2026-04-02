"""Data access layer — maps between Pydantic domain models and SQLAlchemy rows."""

from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from phd_platform.core.enums import Discipline, Level, Verdict
from phd_platform.core.models import (
    CapstoneSubmission,
    DefenseResult,
    ModuleScore,
    Progress,
    Student,
)
from phd_platform.persistence.tables import (
    CapstoneRow,
    DefenseResultRow,
    EnrollmentRow,
    LectureProgressRow,
    LectureRow,
    ModuleScoreRow,
    PlacementResultRow,
    QuestionBankRow,
    StudentRow,
    TutoringSessionRow,
)


class StudentRepository:
    """Async CRUD operations for students and their progress."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ------------------------------------------------------------------
    # Student CRUD
    # ------------------------------------------------------------------
    async def create_student(
        self,
        name: str,
        email: str = "",
        interests: list[str] | None = None,
        strengths: list[str] | None = None,
    ) -> Student:
        """Create a new student and return the domain model."""
        student_id = str(uuid4())
        row = StudentRow(
            id=student_id,
            name=name,
            email=email,
            interests=json.dumps(interests or []),
            strengths=json.dumps(strengths or []),
        )
        self.session.add(row)
        await self.session.flush()
        return Student(
            id=UUID(student_id),
            name=name,
            email=email,
            interests=interests or [],
            strengths=strengths or [],
        )

    async def get_student(self, student_id: str) -> Student | None:
        """Load a student and all their progress from the database."""
        result = await self.session.execute(
            select(StudentRow).where(StudentRow.id == student_id)
        )
        row = result.scalar_one_or_none()
        if not row:
            return None

        student = Student(
            id=UUID(row.id),
            name=row.name,
            email=row.email,
            interests=json.loads(row.interests),
            strengths=json.loads(row.strengths),
            created_at=row.created_at,
        )

        # Load enrollments
        enrollments = await self.session.execute(
            select(EnrollmentRow).where(EnrollmentRow.student_id == student_id)
        )
        for enr in enrollments.scalars():
            disc = Discipline(enr.discipline)
            student.enrolled_disciplines.append(disc)
            progress = student.get_progress(disc)
            progress.current_level = Level(enr.current_level)

        # Load module scores
        scores = await self.session.execute(
            select(ModuleScoreRow).where(ModuleScoreRow.student_id == student_id)
        )
        for score_row in scores.scalars():
            disc = Discipline(score_row.discipline)
            progress = student.get_progress(disc)
            progress.module_scores[score_row.module_id] = ModuleScore(
                module_id=score_row.module_id,
                score=score_row.score,
                attempts=score_row.attempts,
                weakness_areas=json.loads(score_row.weakness_areas),
                completed_at=score_row.completed_at,
            )

        return student

    async def list_students(self) -> list[dict]:
        """List all students (summary info only)."""
        result = await self.session.execute(select(StudentRow))
        return [
            {"id": row.id, "name": row.name, "email": row.email, "created_at": row.created_at}
            for row in result.scalars()
        ]

    # ------------------------------------------------------------------
    # Enrollment
    # ------------------------------------------------------------------
    async def enroll(self, student_id: str, discipline: Discipline) -> None:
        """Enroll a student in a discipline."""
        row = EnrollmentRow(
            student_id=student_id,
            discipline=discipline.value,
            current_level=Level.FOUNDATION.value,
        )
        self.session.add(row)
        await self.session.flush()

    async def update_level(
        self, student_id: str, discipline: Discipline, level: Level
    ) -> None:
        """Update a student's current level in a discipline."""
        result = await self.session.execute(
            select(EnrollmentRow).where(
                EnrollmentRow.student_id == student_id,
                EnrollmentRow.discipline == discipline.value,
            )
        )
        row = result.scalar_one_or_none()
        if row:
            row.current_level = level.value
            await self.session.flush()

    # ------------------------------------------------------------------
    # Module Scores
    # ------------------------------------------------------------------
    async def save_module_score(
        self,
        student_id: str,
        discipline: Discipline,
        score: ModuleScore,
    ) -> None:
        """Save or update a module score."""
        # Check for existing score
        result = await self.session.execute(
            select(ModuleScoreRow).where(
                ModuleScoreRow.student_id == student_id,
                ModuleScoreRow.module_id == score.module_id,
                ModuleScoreRow.discipline == discipline.value,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.score = score.score
            existing.attempts = score.attempts
            existing.weakness_areas = json.dumps(score.weakness_areas)
            existing.completed_at = score.completed_at
        else:
            row = ModuleScoreRow(
                student_id=student_id,
                discipline=discipline.value,
                module_id=score.module_id,
                score=score.score,
                attempts=score.attempts,
                weakness_areas=json.dumps(score.weakness_areas),
                completed_at=score.completed_at,
            )
            self.session.add(row)
        await self.session.flush()

    async def get_module_scores(
        self, student_id: str, discipline: Discipline
    ) -> dict[str, ModuleScore]:
        """Get all module scores for a student in a discipline."""
        result = await self.session.execute(
            select(ModuleScoreRow).where(
                ModuleScoreRow.student_id == student_id,
                ModuleScoreRow.discipline == discipline.value,
            )
        )
        scores = {}
        for row in result.scalars():
            scores[row.module_id] = ModuleScore(
                module_id=row.module_id,
                score=row.score,
                attempts=row.attempts,
                weakness_areas=json.loads(row.weakness_areas),
                completed_at=row.completed_at,
            )
        return scores

    # ------------------------------------------------------------------
    # Tutoring Sessions
    # ------------------------------------------------------------------
    async def save_tutoring_session(
        self,
        student_id: str,
        module_id: str,
        history: list[dict],
    ) -> None:
        """Save or update a tutoring session's conversation history."""
        result = await self.session.execute(
            select(TutoringSessionRow).where(
                TutoringSessionRow.student_id == student_id,
                TutoringSessionRow.module_id == module_id,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.conversation_history = json.dumps(history)
            existing.last_activity = datetime.now()
        else:
            row = TutoringSessionRow(
                student_id=student_id,
                module_id=module_id,
                conversation_history=json.dumps(history),
            )
            self.session.add(row)
        await self.session.flush()

    async def load_tutoring_session(
        self, student_id: str, module_id: str
    ) -> list[dict] | None:
        """Load a tutoring session's conversation history."""
        result = await self.session.execute(
            select(TutoringSessionRow).where(
                TutoringSessionRow.student_id == student_id,
                TutoringSessionRow.module_id == module_id,
            )
        )
        row = result.scalar_one_or_none()
        if row:
            return json.loads(row.conversation_history)
        return None

    # ------------------------------------------------------------------
    # Capstones
    # ------------------------------------------------------------------
    async def save_capstone(
        self,
        student_id: str,
        discipline: Discipline,
        level: Level,
        title: str,
        abstract: str = "",
        paper_text: str = "",
    ) -> str:
        """Save a capstone submission. Returns the capstone ID."""
        capstone_id = str(uuid4())
        row = CapstoneRow(
            id=capstone_id,
            student_id=student_id,
            discipline=discipline.value,
            level=level.value,
            title=title,
            abstract=abstract,
            paper_text=paper_text,
        )
        self.session.add(row)
        await self.session.flush()
        return capstone_id

    async def get_capstone(self, capstone_id: str) -> dict | None:
        """Load a capstone submission."""
        result = await self.session.execute(
            select(CapstoneRow).where(CapstoneRow.id == capstone_id)
        )
        row = result.scalar_one_or_none()
        if not row:
            return None
        return {
            "id": row.id,
            "student_id": row.student_id,
            "discipline": row.discipline,
            "level": row.level,
            "title": row.title,
            "abstract": row.abstract,
            "paper_text": row.paper_text,
            "revision_number": row.revision_number,
            "submitted_at": row.submitted_at,
        }

    # ------------------------------------------------------------------
    # Defense Results
    # ------------------------------------------------------------------
    async def save_defense_result(
        self,
        capstone_id: str,
        level: Level,
        reviewer_verdicts: dict[str, str],
        feedback: dict[str, str],
        overall_pass: bool,
        transcript: list[dict] | None = None,
    ) -> str:
        """Save a defense result. Returns the defense result ID."""
        defense_id = str(uuid4())
        row = DefenseResultRow(
            id=defense_id,
            capstone_id=capstone_id,
            level=level.value,
            reviewer_verdicts=json.dumps(reviewer_verdicts),
            feedback=json.dumps(feedback),
            overall_pass=overall_pass,
            transcript=json.dumps(transcript or []),
        )
        self.session.add(row)
        await self.session.flush()
        return defense_id

    async def get_defense_results(self, capstone_id: str) -> list[dict]:
        """Get all defense results for a capstone."""
        result = await self.session.execute(
            select(DefenseResultRow).where(
                DefenseResultRow.capstone_id == capstone_id
            )
        )
        return [
            {
                "id": row.id,
                "capstone_id": row.capstone_id,
                "level": row.level,
                "reviewer_verdicts": json.loads(row.reviewer_verdicts),
                "feedback": json.loads(row.feedback),
                "overall_pass": row.overall_pass,
                "transcript": json.loads(row.transcript),
                "conducted_at": row.conducted_at,
            }
            for row in result.scalars()
        ]

    # ------------------------------------------------------------------
    # Placement Results
    # ------------------------------------------------------------------
    async def save_placement_result(
        self,
        student_id: str,
        discipline: Discipline,
        starting_level: Level,
        gap_modules: list[str],
        diagnostic_scores: dict[str, float],
    ) -> None:
        """Save a placement diagnostic result."""
        row = PlacementResultRow(
            student_id=student_id,
            discipline=discipline.value,
            starting_level=starting_level.value,
            gap_modules=json.dumps(gap_modules),
            diagnostic_scores=json.dumps(diagnostic_scores),
        )
        self.session.add(row)
        await self.session.flush()

    # ------------------------------------------------------------------
    # Question Bank
    # ------------------------------------------------------------------
    async def add_questions(
        self, module_id: str, questions: list[dict]
    ) -> int:
        """Bulk-insert pre-generated questions for a module. Returns count added."""
        count = 0
        for q in questions:
            row = QuestionBankRow(
                module_id=module_id,
                question=q.get("question", ""),
                question_type=q.get("type", "short_answer"),
                difficulty=q.get("difficulty", 3),
                objective_index=q.get("objective_index", 0),
                correct_answer=q.get("correct_answer", ""),
                rubric=q.get("rubric", ""),
                partial_credit=q.get("partial_credit_criteria", ""),
            )
            self.session.add(row)
            count += 1
        await self.session.flush()
        return count

    async def get_questions(
        self, module_id: str, limit: int = 5
    ) -> list[dict]:
        """Get pre-generated questions for a module from the local bank."""
        from sqlalchemy import func
        result = await self.session.execute(
            select(QuestionBankRow)
            .where(QuestionBankRow.module_id == module_id)
            .order_by(func.random())
            .limit(limit)
        )
        return [
            {
                "question": row.question,
                "type": row.question_type,
                "difficulty": row.difficulty,
                "objective_index": row.objective_index,
                "correct_answer": row.correct_answer,
                "rubric": row.rubric,
                "partial_credit_criteria": row.partial_credit,
            }
            for row in result.scalars()
        ]

    async def question_count(self, module_id: str) -> int:
        """Count questions available for a module."""
        from sqlalchemy import func
        result = await self.session.execute(
            select(func.count()).where(QuestionBankRow.module_id == module_id)
        )
        return result.scalar() or 0

    # ------------------------------------------------------------------
    # Lectures
    # ------------------------------------------------------------------
    async def save_lecture(
        self,
        module_id: str,
        title: str,
        content_blocks: list[dict],
        author_agent_id: str = "",
        level_tier: str = "foundation",
        estimated_minutes: int = 30,
        learning_objectives: list[str] | None = None,
        prerequisites_summary: str = "",
    ) -> None:
        """Save or update a lecture for a module."""
        result = await self.session.execute(
            select(LectureRow).where(LectureRow.module_id == module_id)
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.title = title
            existing.content_blocks = json.dumps(content_blocks)
            existing.author_agent_id = author_agent_id
            existing.level_tier = level_tier
            existing.estimated_minutes = estimated_minutes
            existing.learning_objectives = json.dumps(learning_objectives or [])
            existing.prerequisites_summary = prerequisites_summary
        else:
            row = LectureRow(
                module_id=module_id,
                title=title,
                content_blocks=json.dumps(content_blocks),
                author_agent_id=author_agent_id,
                level_tier=level_tier,
                estimated_minutes=estimated_minutes,
                learning_objectives=json.dumps(learning_objectives or []),
                prerequisites_summary=prerequisites_summary,
            )
            self.session.add(row)
        await self.session.flush()

    async def get_lecture(self, module_id: str) -> dict | None:
        """Load a lecture for a module."""
        result = await self.session.execute(
            select(LectureRow).where(LectureRow.module_id == module_id)
        )
        row = result.scalar_one_or_none()
        if not row:
            return None
        return {
            "module_id": row.module_id,
            "title": row.title,
            "author_agent_id": row.author_agent_id,
            "level_tier": row.level_tier,
            "estimated_minutes": row.estimated_minutes,
            "content_blocks": json.loads(row.content_blocks),
            "learning_objectives": json.loads(row.learning_objectives),
            "prerequisites_summary": row.prerequisites_summary,
        }

    async def save_lecture_progress(
        self,
        student_id: str,
        module_id: str,
        blocks_completed: int,
        blocks_total: int,
        checkpoint_scores: list[dict] | None = None,
        completed: bool = False,
    ) -> None:
        """Save or update a student's lecture progress."""
        result = await self.session.execute(
            select(LectureProgressRow).where(
                LectureProgressRow.student_id == student_id,
                LectureProgressRow.module_id == module_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.blocks_completed = blocks_completed
            existing.blocks_total = blocks_total
            existing.checkpoint_scores = json.dumps(checkpoint_scores or [])
            existing.completed = completed
            existing.last_activity = datetime.now()
        else:
            row = LectureProgressRow(
                student_id=student_id,
                module_id=module_id,
                blocks_completed=blocks_completed,
                blocks_total=blocks_total,
                checkpoint_scores=json.dumps(checkpoint_scores or []),
                completed=completed,
            )
            self.session.add(row)
        await self.session.flush()

    async def get_lecture_progress(
        self, student_id: str, module_id: str
    ) -> dict | None:
        """Load a student's lecture progress."""
        result = await self.session.execute(
            select(LectureProgressRow).where(
                LectureProgressRow.student_id == student_id,
                LectureProgressRow.module_id == module_id,
            )
        )
        row = result.scalar_one_or_none()
        if not row:
            return None
        return {
            "blocks_completed": row.blocks_completed,
            "blocks_total": row.blocks_total,
            "checkpoint_scores": json.loads(row.checkpoint_scores),
            "completed": row.completed,
            "started_at": row.started_at,
            "last_activity": row.last_activity,
        }
