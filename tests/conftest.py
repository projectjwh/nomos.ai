"""Shared test fixtures — mock AI client and common helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import pytest

from phd_platform.core.enums import Discipline, Level
from phd_platform.core.models import ModuleScore, Progress, Student
from phd_platform.curriculum.loader import CurriculumLoader


# ---------------------------------------------------------------------------
# Mock Anthropic Client
# ---------------------------------------------------------------------------
@dataclass
class MockContent:
    text: str = ""


@dataclass
class MockMessage:
    content: list[MockContent] = field(default_factory=list)
    model: str = "mock"
    stop_reason: str = "end_turn"


class MockMessages:
    """Mock for client.messages that returns configurable responses."""

    def __init__(self, default_response: str = '{"score": 0.85, "feedback": "Good work", "weakness_areas": []}'):
        self._responses: list[str] = []
        self._default = default_response
        self._call_count = 0
        self.last_kwargs: dict[str, Any] = {}

    def set_responses(self, responses: list[str]) -> None:
        """Queue specific responses for successive calls."""
        self._responses = list(responses)

    async def create(self, **kwargs: Any) -> MockMessage:
        self.last_kwargs = kwargs
        self._call_count += 1
        if self._responses:
            text = self._responses.pop(0)
        else:
            text = self._default
        return MockMessage(content=[MockContent(text=text)])

    @property
    def call_count(self) -> int:
        return self._call_count


class MockAsyncAnthropic:
    """Mock AsyncAnthropic client for testing without API calls."""

    def __init__(self, default_response: str = '{"score": 0.85, "feedback": "Good work", "weakness_areas": []}'):
        self.messages = MockMessages(default_response)

    def set_responses(self, responses: list[str]) -> None:
        self.messages.set_responses(responses)


# ---------------------------------------------------------------------------
# Sample AI responses
# ---------------------------------------------------------------------------
SAMPLE_DIAGNOSTIC_QUESTIONS = """[
  {
    "question": "Given utility function U(x,y) = x^0.5 * y^0.5 and budget constraint 2x + 3y = 120, find the optimal bundle.",
    "type": "computation",
    "difficulty": 3,
    "objective_index": 0,
    "correct_answer": "x=30, y=20. Set MRS = Px/Py: (y/x) = 2/3, substitute into budget.",
    "rubric": "Full marks for correct setup of Lagrangian or MRS condition, correct algebra, correct answer.",
    "partial_credit_criteria": "Half credit for correct setup with algebra errors."
  },
  {
    "question": "Explain the difference between Marshallian and Hicksian demand. When do they coincide?",
    "type": "short_answer",
    "difficulty": 4,
    "objective_index": 1,
    "correct_answer": "Marshallian maximizes utility subject to budget. Hicksian minimizes expenditure subject to utility level. They coincide at the optimal bundle due to duality.",
    "rubric": "Must mention utility maximization vs expenditure minimization, and duality.",
    "partial_credit_criteria": "Partial credit for correct definitions without duality discussion."
  }
]"""

SAMPLE_EVALUATION = '{"score": 0.78, "feedback": "Good understanding of the Lagrangian setup but made an algebra error in step 3. The intuition about corner solutions was correct.", "weakness_areas": ["algebraic manipulation", "constrained optimization mechanics"]}'

SAMPLE_PROPOSALS = """[
  {"title": "Causal Impact of Remote Work on Housing Prices", "research_question": "How did the shift to remote work during 2020-2023 affect housing prices in secondary cities?", "methodology": "Difference-in-differences using broadband penetration as an instrument", "data_sources": "Zillow ZTRAX, ACS, FCC broadband data", "contribution": "First causal estimate of remote work effect on secondary city housing", "milestones": "Weeks 1-2: data collection, Weeks 3-4: cleaning, Weeks 5-6: estimation, Weeks 7-8: writing", "risks": "Instrument validity; confounding from fiscal stimulus"},
  {"title": "Machine Learning for Predicting Municipal Bond Defaults", "research_question": "Can ensemble methods improve on traditional credit rating models for municipal bonds?", "methodology": "Random forest + gradient boosting vs Altman Z-score", "data_sources": "EMMA MSRB data, Census fiscal data", "contribution": "Novel application of ML to muni bond credit risk", "milestones": "Weeks 1-3: data, Weeks 4-5: feature engineering, Weeks 6-7: modeling, Week 8: paper", "risks": "Small default sample; class imbalance"}
]"""

SAMPLE_VERDICT = '{"verdict": "Minor Revision", "justification": "The paper makes a solid contribution but needs stronger robustness checks.", "strengths": ["Novel dataset", "Clean identification"], "weaknesses": ["Limited robustness checks", "Discussion section thin"], "suggestions": ["Add placebo tests", "Expand literature review"]}'


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_client() -> MockAsyncAnthropic:
    return MockAsyncAnthropic()


@pytest.fixture
def curriculum_loader() -> CurriculumLoader:
    loader = CurriculumLoader()
    loader.load()
    return loader


@pytest.fixture
def sample_student() -> Student:
    return Student(
        name="Test Student",
        email="test@example.com",
        interests=["causal inference", "labor economics"],
        strengths=["econometrics", "programming"],
        enrolled_disciplines=[Discipline.ECONOMICS],
    )


@pytest.fixture
def student_with_scores() -> Student:
    """Student with some module scores for testing progression."""
    student = Student(
        name="Advanced Student",
        email="advanced@example.com",
        enrolled_disciplines=[Discipline.ECONOMICS],
    )
    progress = student.get_progress(Discipline.ECONOMICS)
    progress.current_level = Level.FOUNDATION

    # High scores on foundation modules
    for mod_id in [
        "ECON-F-001", "ECON-F-002", "ECON-F-003", "ECON-F-004",
        "ECON-F-005", "ECON-F-006", "ECON-F-007", "ECON-F-008",
    ]:
        progress.module_scores[mod_id] = ModuleScore(module_id=mod_id, score=0.95)

    return student


@pytest.fixture
def student_with_weakness() -> Student:
    """Student with a weak module for testing remediation."""
    student = Student(
        name="Struggling Student",
        enrolled_disciplines=[Discipline.ECONOMICS],
    )
    progress = student.get_progress(Discipline.ECONOMICS)
    progress.module_scores["ECON-U-008"] = ModuleScore(
        module_id="ECON-U-008", score=0.60, weakness_areas=["IV estimation", "panel data"]
    )
    progress.module_scores["ECON-U-007"] = ModuleScore(
        module_id="ECON-U-007", score=0.65, weakness_areas=["MLE asymptotics"]
    )
    return student
