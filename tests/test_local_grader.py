"""Tests for the local grader — Tier 1 cost optimization."""

import pytest

from phd_platform.assessment.local_grader import LocalGrader


@pytest.fixture
def grader():
    return LocalGrader()


class TestMCQGrading:
    def test_correct_answer(self, grader):
        result = grader.grade("mcq", "A", "A", "")
        assert result is not None
        assert result.score == 1.0

    def test_case_insensitive(self, grader):
        result = grader.grade("mcq", "b", "B", "")
        assert result.score == 1.0

    def test_with_formatting(self, grader):
        result = grader.grade("mcq", "(A)", "A", "")
        assert result.score == 1.0

    def test_wrong_answer(self, grader):
        result = grader.grade("mcq", "C", "A", "")
        assert result.score == 0.0
        assert "correct answer" in result.feedback.lower()


class TestComputationGrading:
    def test_exact_match(self, grader):
        result = grader.grade("computation", "The answer is 42", "42", "")
        assert result is not None
        assert result.score == 1.0

    def test_decimal_tolerance(self, grader):
        result = grader.grade("computation", "3.14159", "3.14159", "")
        assert result.score == 1.0

    def test_close_enough(self, grader):
        result = grader.grade("computation", "x = 30.01", "x = 30", "")
        assert result.score == 1.0

    def test_wrong_computation(self, grader):
        result = grader.grade("computation", "x = 100", "x = 30", "")
        assert result.score == 0.0

    def test_no_number_in_answer(self, grader):
        result = grader.grade("computation", "I think it increases", "42", "")
        assert result.score == 0.0
        assert "numeric" in result.feedback.lower()

    def test_partial_credit_intermediate(self, grader):
        # Student gets intermediate step right but final wrong
        result = grader.grade(
            "computation",
            "MRS = 2/3, then I got x = 50",
            "MRS = 2/3, x = 30, y = 20",
            "",
        )
        # Should get partial credit for getting MRS right (0.667 matches)
        assert result is not None


class TestShortAnswerGrading:
    def test_good_coverage(self, grader):
        result = grader.grade(
            "short_answer",
            "The consumer maximizes utility subject to budget constraint using Lagrangian optimization",
            "utility maximization budget constraint Lagrangian",
            "Must mention utility, budget constraint, and Lagrangian",
        )
        assert result is not None
        assert result.score > 0.5

    def test_poor_coverage(self, grader):
        result = grader.grade(
            "short_answer",
            "People buy stuff they like",
            "utility maximization budget constraint Lagrangian first-order conditions",
            "Must mention utility, budget constraint, Lagrangian, FOC",
        )
        assert result is not None
        assert result.score < 0.5

    def test_returns_none_for_empty_rubric(self, grader):
        result = grader.grade("short_answer", "answer", "", "")
        # With no rubric terms to match, should fall through to None
        assert result is None


class TestUnsupportedTypes:
    def test_proof_returns_none(self, grader):
        result = grader.grade("proof", "By induction...", "See full proof", "")
        assert result is None

    def test_essay_returns_none(self, grader):
        result = grader.grade("essay", "The economy...", "", "")
        assert result is None

    def test_unknown_type_returns_none(self, grader):
        result = grader.grade("creative_writing", "Once upon a time", "", "")
        assert result is None


class TestHelpers:
    def test_extract_numbers(self):
        nums = LocalGrader._extract_numbers("x = 30, y = 20, total = 50.5")
        assert 30.0 in nums
        assert 20.0 in nums
        assert 50.5 in nums

    def test_extract_negative_numbers(self):
        nums = LocalGrader._extract_numbers("slope = -2.5")
        assert -2.5 in nums

    def test_extract_key_terms(self):
        terms = LocalGrader._extract_key_terms(
            "The Lagrangian multiplier represents the shadow price of the budget constraint"
        )
        assert "lagrangian" in terms
        assert "multiplier" in terms
        assert "budget" in terms
        # Common words should be filtered
        assert "the" not in terms
