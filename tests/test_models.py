"""Tests for core data models."""

import pytest

from phd_platform.core.enums import Discipline, Level, Verdict
from phd_platform.core.models import (
    DefenseResult,
    ModuleScore,
    Progress,
    Student,
)


class TestStudent:
    def test_get_progress_creates_new(self):
        student = Student(name="Test")
        progress = student.get_progress(Discipline.ECONOMICS)
        assert progress.discipline == Discipline.ECONOMICS
        assert progress.current_level == Level.FOUNDATION

    def test_get_progress_returns_existing(self):
        student = Student(name="Test")
        p1 = student.get_progress(Discipline.ECONOMICS)
        p1.current_level = Level.MASTERS
        p2 = student.get_progress(Discipline.ECONOMICS)
        assert p2.current_level == Level.MASTERS

    def test_multiple_disciplines(self):
        student = Student(name="Test")
        econ = student.get_progress(Discipline.ECONOMICS)
        cs = student.get_progress(Discipline.COMPUTER_SCIENCE)
        econ.current_level = Level.MASTERS
        assert cs.current_level == Level.FOUNDATION  # Independent


class TestProgress:
    def test_current_mastery_empty(self):
        progress = Progress(discipline=Discipline.ECONOMICS)
        assert progress.current_mastery == 0.0

    def test_current_mastery_with_scores(self):
        progress = Progress(discipline=Discipline.ECONOMICS, current_level=Level.FOUNDATION)
        progress.module_scores["ECON-F-001"] = ModuleScore(module_id="ECON-F-001", score=0.90)
        progress.module_scores["ECON-F-002"] = ModuleScore(module_id="ECON-F-002", score=0.80)
        # Both start with 'F' matching FOUNDATION's first char 'f' -> 'F'
        assert progress.current_mastery == pytest.approx(0.85)

    def test_weakness_modules(self):
        progress = Progress(discipline=Discipline.ECONOMICS)
        progress.module_scores["MOD-A"] = ModuleScore(module_id="MOD-A", score=0.90)
        progress.module_scores["MOD-B"] = ModuleScore(module_id="MOD-B", score=0.60)
        progress.module_scores["MOD-C"] = ModuleScore(module_id="MOD-C", score=0.75)
        weak = progress.weakness_modules
        assert "MOD-B" in weak
        assert "MOD-C" in weak
        assert "MOD-A" not in weak

    def test_no_weakness_modules_all_high(self):
        progress = Progress(discipline=Discipline.ECONOMICS)
        progress.module_scores["MOD-A"] = ModuleScore(module_id="MOD-A", score=0.95)
        assert len(progress.weakness_modules) == 0


class TestDefenseResult:
    def test_passing_count(self):
        from uuid import uuid4
        result = DefenseResult(
            capstone_id=uuid4(),
            level=Level.DOCTORAL,
            reviewer_verdicts={
                "AER": Verdict.ACCEPT,
                "QJE": Verdict.MINOR_REVISION,
                "Econometrica": Verdict.MAJOR_REVISION,
                "JPE": Verdict.ACCEPT,
                "ReStud": Verdict.REJECT,
            },
        )
        assert result.passing_count == 3  # Accept + Minor Revision count as passing

    def test_revision_count(self):
        from uuid import uuid4
        result = DefenseResult(
            capstone_id=uuid4(),
            level=Level.MASTERS,
            reviewer_verdicts={
                "QJE": Verdict.MAJOR_REVISION,
                "Econometrica": Verdict.MAJOR_REVISION,
                "JPE": Verdict.ACCEPT,
            },
        )
        assert result.revision_count == 2

    def test_all_accept(self):
        from uuid import uuid4
        result = DefenseResult(
            capstone_id=uuid4(),
            level=Level.UNDERGRADUATE,
            reviewer_verdicts={
                "AER": Verdict.ACCEPT,
                "JPE": Verdict.ACCEPT,
            },
        )
        assert result.passing_count == 2
        assert result.revision_count == 0
