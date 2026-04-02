"""Tests for the persistence layer — using in-memory SQLite."""

from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from phd_platform.core.enums import Discipline, Level
from phd_platform.core.models import ModuleScore
from phd_platform.persistence.database import init_db
from phd_platform.persistence.repository import StudentRepository
from phd_platform.persistence.tables import Base


@pytest.fixture
async def db_session():
    """Create an in-memory SQLite database and yield a session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def repo(db_session: AsyncSession) -> StudentRepository:
    return StudentRepository(db_session)


class TestStudentCRUD:
    @pytest.mark.asyncio
    async def test_create_student(self, repo: StudentRepository):
        student = await repo.create_student(
            name="Alice",
            email="alice@example.com",
            interests=["causal inference", "ML"],
            strengths=["econometrics"],
        )
        assert student.name == "Alice"
        assert student.email == "alice@example.com"
        assert "causal inference" in student.interests
        assert student.id is not None

    @pytest.mark.asyncio
    async def test_get_student_round_trip(self, repo: StudentRepository):
        created = await repo.create_student(
            name="Bob",
            email="bob@test.com",
            interests=["NLP", "transformers"],
        )
        loaded = await repo.get_student(str(created.id))
        assert loaded is not None
        assert loaded.name == "Bob"
        assert loaded.email == "bob@test.com"
        assert loaded.interests == ["NLP", "transformers"]

    @pytest.mark.asyncio
    async def test_get_nonexistent_student(self, repo: StudentRepository):
        result = await repo.get_student("nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_students(self, repo: StudentRepository):
        await repo.create_student(name="Alice")
        await repo.create_student(name="Bob")
        students = await repo.list_students()
        assert len(students) == 2
        names = {s["name"] for s in students}
        assert names == {"Alice", "Bob"}


class TestEnrollment:
    @pytest.mark.asyncio
    async def test_enroll_and_load(self, repo: StudentRepository):
        student = await repo.create_student(name="Charlie")
        await repo.enroll(str(student.id), Discipline.ECONOMICS)
        loaded = await repo.get_student(str(student.id))
        assert loaded is not None
        assert Discipline.ECONOMICS in loaded.enrolled_disciplines
        progress = loaded.get_progress(Discipline.ECONOMICS)
        assert progress.current_level == Level.FOUNDATION

    @pytest.mark.asyncio
    async def test_update_level(self, repo: StudentRepository):
        student = await repo.create_student(name="Dana")
        await repo.enroll(str(student.id), Discipline.AI_ML)
        await repo.update_level(str(student.id), Discipline.AI_ML, Level.UNDERGRADUATE)
        loaded = await repo.get_student(str(student.id))
        assert loaded is not None
        progress = loaded.get_progress(Discipline.AI_ML)
        assert progress.current_level == Level.UNDERGRADUATE


class TestModuleScores:
    @pytest.mark.asyncio
    async def test_save_and_load_score(self, repo: StudentRepository):
        student = await repo.create_student(name="Eve")
        score = ModuleScore(
            module_id="ECON-F-001",
            score=0.92,
            attempts=1,
            weakness_areas=["algebra"],
            completed_at=datetime.now(),
        )
        await repo.save_module_score(str(student.id), Discipline.ECONOMICS, score)
        scores = await repo.get_module_scores(str(student.id), Discipline.ECONOMICS)
        assert "ECON-F-001" in scores
        assert scores["ECON-F-001"].score == pytest.approx(0.92)
        assert scores["ECON-F-001"].weakness_areas == ["algebra"]

    @pytest.mark.asyncio
    async def test_update_existing_score(self, repo: StudentRepository):
        student = await repo.create_student(name="Frank")
        score_v1 = ModuleScore(module_id="CS-F-001", score=0.60, attempts=1)
        await repo.save_module_score(str(student.id), Discipline.COMPUTER_SCIENCE, score_v1)
        score_v2 = ModuleScore(module_id="CS-F-001", score=0.88, attempts=2)
        await repo.save_module_score(str(student.id), Discipline.COMPUTER_SCIENCE, score_v2)
        scores = await repo.get_module_scores(str(student.id), Discipline.COMPUTER_SCIENCE)
        assert scores["CS-F-001"].score == pytest.approx(0.88)
        assert scores["CS-F-001"].attempts == 2

    @pytest.mark.asyncio
    async def test_scores_loaded_with_student(self, repo: StudentRepository):
        student = await repo.create_student(name="Grace")
        await repo.enroll(str(student.id), Discipline.DATA_SCIENCE)
        score = ModuleScore(module_id="DS-F-001", score=0.95)
        await repo.save_module_score(str(student.id), Discipline.DATA_SCIENCE, score)
        loaded = await repo.get_student(str(student.id))
        assert loaded is not None
        progress = loaded.get_progress(Discipline.DATA_SCIENCE)
        assert "DS-F-001" in progress.module_scores
        assert progress.module_scores["DS-F-001"].score == pytest.approx(0.95)


class TestTutoringSessions:
    @pytest.mark.asyncio
    async def test_save_and_load_session(self, repo: StudentRepository):
        student = await repo.create_student(name="Hank")
        history = [
            {"role": "user", "content": "Explain the chain rule"},
            {"role": "assistant", "content": "The chain rule states..."},
        ]
        await repo.save_tutoring_session(str(student.id), "ECON-F-002", history)
        loaded = await repo.load_tutoring_session(str(student.id), "ECON-F-002")
        assert loaded is not None
        assert len(loaded) == 2
        assert loaded[0]["role"] == "user"
        assert "chain rule" in loaded[0]["content"]

    @pytest.mark.asyncio
    async def test_update_session(self, repo: StudentRepository):
        student = await repo.create_student(name="Iris")
        await repo.save_tutoring_session(str(student.id), "AI-F-001", [{"role": "user", "content": "hi"}])
        extended = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "user", "content": "teach me attention"},
        ]
        await repo.save_tutoring_session(str(student.id), "AI-F-001", extended)
        loaded = await repo.load_tutoring_session(str(student.id), "AI-F-001")
        assert loaded is not None
        assert len(loaded) == 3

    @pytest.mark.asyncio
    async def test_load_nonexistent_session(self, repo: StudentRepository):
        student = await repo.create_student(name="Jack")
        result = await repo.load_tutoring_session(str(student.id), "NOPE-001")
        assert result is None


class TestCapstoneAndDefense:
    @pytest.mark.asyncio
    async def test_save_capstone(self, repo: StudentRepository):
        student = await repo.create_student(name="Kate")
        capstone_id = await repo.save_capstone(
            student_id=str(student.id),
            discipline=Discipline.ECONOMICS,
            level=Level.UNDERGRADUATE,
            title="Impact of Remote Work on Housing Prices",
            abstract="This paper examines...",
            paper_text="Full paper content here...",
        )
        assert capstone_id is not None
        loaded = await repo.get_capstone(capstone_id)
        assert loaded is not None
        assert loaded["title"] == "Impact of Remote Work on Housing Prices"
        assert loaded["level"] == "undergraduate"

    @pytest.mark.asyncio
    async def test_save_defense_result(self, repo: StudentRepository):
        student = await repo.create_student(name="Leo")
        capstone_id = await repo.save_capstone(
            str(student.id), Discipline.AI_ML, Level.MASTERS, "Deep Hedging"
        )
        defense_id = await repo.save_defense_result(
            capstone_id=capstone_id,
            level=Level.MASTERS,
            reviewer_verdicts={"NeurIPS": "Accept", "ICML": "Minor Revision", "ICLR": "Accept"},
            feedback={"NeurIPS": "Strong work", "ICML": "Needs ablations", "ICLR": "Novel approach"},
            overall_pass=True,
            transcript=[{"phase": "qa", "content": "..."}],
        )
        results = await repo.get_defense_results(capstone_id)
        assert len(results) == 1
        assert results[0]["overall_pass"] is True
        assert results[0]["reviewer_verdicts"]["NeurIPS"] == "Accept"

    @pytest.mark.asyncio
    async def test_placement_result(self, repo: StudentRepository):
        student = await repo.create_student(name="Mona")
        await repo.save_placement_result(
            student_id=str(student.id),
            discipline=Discipline.FINANCIAL_ENGINEERING,
            starting_level=Level.UNDERGRADUATE,
            gap_modules=["FE-F-003"],
            diagnostic_scores={"FE-F-001": 0.95, "FE-F-002": 0.88, "FE-F-003": 0.60},
        )
        # Verify no error (we don't have a get_placement_result yet, but the save works)


class TestQuestionBank:
    @pytest.mark.asyncio
    async def test_add_and_get_questions(self, repo: StudentRepository):
        questions = [
            {"question": "What is 2+2?", "type": "computation", "difficulty": 1,
             "objective_index": 0, "correct_answer": "4", "rubric": "Must be 4"},
            {"question": "Prove 1+1=2", "type": "proof", "difficulty": 5,
             "objective_index": 1, "correct_answer": "By Peano axioms...", "rubric": "Full proof"},
        ]
        added = await repo.add_questions("ECON-F-001", questions)
        assert added == 2

        loaded = await repo.get_questions("ECON-F-001", limit=10)
        assert len(loaded) == 2
        texts = {q["question"] for q in loaded}
        assert "What is 2+2?" in texts

    @pytest.mark.asyncio
    async def test_question_count(self, repo: StudentRepository):
        questions = [{"question": f"Q{i}", "correct_answer": f"A{i}"} for i in range(3)]
        await repo.add_questions("DS-F-001", questions)
        count = await repo.question_count("DS-F-001")
        assert count == 3

    @pytest.mark.asyncio
    async def test_empty_question_bank(self, repo: StudentRepository):
        loaded = await repo.get_questions("NONEXISTENT-001")
        assert loaded == []
        count = await repo.question_count("NONEXISTENT-001")
        assert count == 0

    @pytest.mark.asyncio
    async def test_questions_random_order(self, repo: StudentRepository):
        questions = [{"question": f"Q{i}", "correct_answer": f"A{i}"} for i in range(20)]
        await repo.add_questions("CS-F-001", questions)
        # Get 5 questions — should be a random subset
        batch = await repo.get_questions("CS-F-001", limit=5)
        assert len(batch) == 5
