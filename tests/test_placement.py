"""Tests for placement engine with mock AI client."""

import pytest

from phd_platform.assessment.placement import PlacementEngine
from phd_platform.core.enums import Discipline, Level
from phd_platform.core.models import Student
from phd_platform.curriculum.loader import CurriculumLoader
from tests.conftest import SAMPLE_DIAGNOSTIC_QUESTIONS, SAMPLE_EVALUATION, MockAsyncAnthropic


@pytest.fixture
def placement_engine(curriculum_loader: CurriculumLoader) -> PlacementEngine:
    client = MockAsyncAnthropic(default_response=SAMPLE_EVALUATION)
    return PlacementEngine(client, curriculum_loader)


class TestPlacementEngine:
    @pytest.mark.asyncio
    async def test_generate_diagnostic_returns_questions(self, curriculum_loader):
        client = MockAsyncAnthropic(default_response=SAMPLE_DIAGNOSTIC_QUESTIONS)
        engine = PlacementEngine(client, curriculum_loader)
        module = curriculum_loader.get_module("ECON-F-006")
        questions = await engine.generate_diagnostic(Discipline.ECONOMICS, module, 2)
        assert len(questions) == 2
        assert questions[0].question  # Not empty
        assert questions[0].correct_answer  # Not empty

    @pytest.mark.asyncio
    async def test_evaluate_response_returns_nonzero_score(self, placement_engine):
        module = placement_engine.curriculum.get_module("ECON-F-001")
        question = {"question": "What is 2+2?", "correct_answer": "4", "rubric": "Must be 4"}
        score = await placement_engine.evaluate_response(question, "4", module)
        assert score.module_id == "ECON-F-001"
        assert score.score == pytest.approx(0.78)  # From SAMPLE_EVALUATION
        assert len(score.weakness_areas) > 0

    @pytest.mark.asyncio
    async def test_evaluate_response_with_diagnostic_question(self, curriculum_loader):
        from phd_platform.core.models import DiagnosticQuestion
        client = MockAsyncAnthropic(default_response=SAMPLE_EVALUATION)
        engine = PlacementEngine(client, curriculum_loader)
        module = curriculum_loader.get_module("ECON-F-002")
        q = DiagnosticQuestion(
            question="Differentiate x^3",
            correct_answer="3x^2",
            rubric="Must apply power rule",
        )
        score = await engine.evaluate_response(q, "3x^2", module)
        assert score.score > 0.0
        assert score.completed_at is not None

    def test_determine_starting_level_all_high(self, placement_engine, sample_student):
        scores = {f"ECON-F-{i:03d}": 0.95 for i in range(1, 9)}
        level = placement_engine.determine_starting_level(
            sample_student, Discipline.ECONOMICS, scores
        )
        assert level == Level.UNDERGRADUATE  # Passed foundation, placed into undergrad

    def test_determine_starting_level_all_low(self, placement_engine, sample_student):
        scores = {f"ECON-F-{i:03d}": 0.50 for i in range(1, 9)}
        level = placement_engine.determine_starting_level(
            sample_student, Discipline.ECONOMICS, scores
        )
        assert level == Level.FOUNDATION

    def test_determine_starting_level_mixed(self, placement_engine, sample_student):
        scores = {f"ECON-F-{i:03d}": 0.85 for i in range(1, 9)}
        # Average of 0.85 < 0.90 threshold
        level = placement_engine.determine_starting_level(
            sample_student, Discipline.ECONOMICS, scores
        )
        assert level == Level.FOUNDATION

    def test_identify_gaps(self, placement_engine):
        scores = {
            "ECON-F-001": 0.95,
            "ECON-F-002": 0.60,  # Gap
            "ECON-F-003": 0.90,
            "ECON-F-004": 0.50,  # Gap
        }
        gaps = placement_engine.identify_gaps(scores)
        assert "ECON-F-002" in gaps
        assert "ECON-F-004" in gaps
        assert "ECON-F-001" not in gaps

    def test_identify_gaps_custom_threshold(self, placement_engine):
        scores = {"ECON-F-001": 0.85}
        gaps = placement_engine.identify_gaps(scores, threshold=0.90)
        assert "ECON-F-001" in gaps
