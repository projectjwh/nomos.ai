"""Tests for defense system components."""

import pytest

from phd_platform.core.enums import Discipline, Level, Verdict
from phd_platform.defense.rubric import (
    RUBRIC_DIMENSIONS,
    compute_weighted_score,
    score_to_verdict,
)


class TestRubric:
    def test_all_dimensions_defined(self):
        expected = {"methodology", "novelty", "significance", "exposition"}
        assert set(RUBRIC_DIMENSIONS.keys()) == expected

    def test_each_dimension_has_5_levels(self):
        for dim, data in RUBRIC_DIMENSIONS.items():
            assert len(data["levels"]) == 5, f"{dim} doesn't have 5 scoring levels"
            assert set(data["levels"].keys()) == {1, 2, 3, 4, 5}

    def test_weighted_score_calculation(self):
        scores = {"methodology": 4, "novelty": 5, "significance": 3, "exposition": 4}
        result = compute_weighted_score(scores, Discipline.ECONOMICS)
        assert 3.0 < result < 5.0

    def test_weighted_score_with_custom_weights(self):
        scores = {"methodology": 5, "novelty": 1, "significance": 1, "exposition": 1}
        # Heavy methodology weight should pull score up
        heavy_method = compute_weighted_score(
            scores, Discipline.ECONOMICS,
            persona_weights={"methodology": 0.90, "novelty": 0.03, "significance": 0.04, "exposition": 0.03}
        )
        # Equal weights
        equal = compute_weighted_score(
            scores, Discipline.ECONOMICS,
            persona_weights={"methodology": 0.25, "novelty": 0.25, "significance": 0.25, "exposition": 0.25}
        )
        assert heavy_method > equal

    def test_verdict_thresholds_doctoral(self):
        assert score_to_verdict(4.8, Level.DOCTORAL) == "Accept"
        assert score_to_verdict(4.2, Level.DOCTORAL) == "Minor Revision"
        assert score_to_verdict(3.7, Level.DOCTORAL) == "Major Revision"
        assert score_to_verdict(2.0, Level.DOCTORAL) == "Reject"

    def test_verdict_thresholds_undergraduate(self):
        assert score_to_verdict(4.5, Level.UNDERGRADUATE) == "Accept"
        assert score_to_verdict(3.7, Level.UNDERGRADUATE) == "Minor Revision"
        assert score_to_verdict(3.0, Level.UNDERGRADUATE) == "Major Revision"
        assert score_to_verdict(1.5, Level.UNDERGRADUATE) == "Reject"


class TestVerdict:
    def test_passing_verdicts(self):
        assert Verdict.ACCEPT.is_passing
        assert Verdict.MINOR_REVISION.is_passing
        assert not Verdict.MAJOR_REVISION.is_passing
        assert not Verdict.REJECT.is_passing

    def test_resubmission_allowed(self):
        assert Verdict.MAJOR_REVISION.allows_resubmission
        assert not Verdict.REJECT.allows_resubmission
        assert not Verdict.ACCEPT.allows_resubmission
