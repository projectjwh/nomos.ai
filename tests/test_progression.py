"""Tests for progression gate evaluation."""

from uuid import uuid4

import pytest

from phd_platform.assessment.progression import ProgressionGate
from phd_platform.core.enums import Discipline, GateStatus, Level, Verdict
from phd_platform.core.models import DefenseResult, ModuleScore, Student
from phd_platform.curriculum.loader import CurriculumLoader


@pytest.fixture
def gate(curriculum_loader: CurriculumLoader) -> ProgressionGate:
    return ProgressionGate(curriculum_loader)


class TestProgressionGate:
    def test_foundation_gate_not_met(self, gate):
        student = Student(name="New Student", enrolled_disciplines=[Discipline.ECONOMICS])
        # No scores at all
        status = gate.evaluate_gate(student, Discipline.ECONOMICS, Level.FOUNDATION)
        assert status == GateStatus.IN_PROGRESS

    def test_foundation_gate_passed(self, gate, student_with_scores):
        status = gate.evaluate_gate(
            student_with_scores, Discipline.ECONOMICS, Level.FOUNDATION
        )
        assert status == GateStatus.PASSED

    def test_foundation_gate_partial_scores(self, gate):
        student = Student(name="Partial", enrolled_disciplines=[Discipline.ECONOMICS])
        progress = student.get_progress(Discipline.ECONOMICS)
        # Only 4 of 8 foundation modules scored
        for i in range(1, 5):
            progress.module_scores[f"ECON-F-{i:03d}"] = ModuleScore(
                module_id=f"ECON-F-{i:03d}", score=0.95
            )
        status = gate.evaluate_gate(student, Discipline.ECONOMICS, Level.FOUNDATION)
        assert status == GateStatus.IN_PROGRESS  # Missing modules

    def test_undergrad_gate_mastery_met_no_defense(self, gate, curriculum_loader):
        student = Student(name="Strong UG", enrolled_disciplines=[Discipline.ECONOMICS])
        progress = student.get_progress(Discipline.ECONOMICS)
        progress.current_level = Level.UNDERGRADUATE
        # Score all undergrad modules at 95%+
        for mod in curriculum_loader.get_modules_for_level(Discipline.ECONOMICS, Level.UNDERGRADUATE):
            progress.module_scores[mod.id] = ModuleScore(module_id=mod.id, score=0.96)
        status = gate.evaluate_gate(student, Discipline.ECONOMICS, Level.UNDERGRADUATE)
        assert status == GateStatus.READY_FOR_ASSESSMENT  # Mastery met, needs defense

    def test_undergrad_gate_with_passing_defense(self, gate, curriculum_loader):
        student = Student(name="Defended UG", enrolled_disciplines=[Discipline.ECONOMICS])
        progress = student.get_progress(Discipline.ECONOMICS)
        progress.current_level = Level.UNDERGRADUATE
        for mod in curriculum_loader.get_modules_for_level(Discipline.ECONOMICS, Level.UNDERGRADUATE):
            progress.module_scores[mod.id] = ModuleScore(module_id=mod.id, score=0.96)
        # Add passing defense
        progress.defenses.append(DefenseResult(
            capstone_id=uuid4(),
            level=Level.UNDERGRADUATE,
            reviewer_verdicts={"AER": Verdict.ACCEPT, "JPE": Verdict.ACCEPT},
            overall_pass=True,
        ))
        status = gate.evaluate_gate(student, Discipline.ECONOMICS, Level.UNDERGRADUATE)
        assert status == GateStatus.PASSED

    def test_doctoral_gate_needs_majority_accept(self, gate, curriculum_loader):
        student = Student(name="PhD Student", enrolled_disciplines=[Discipline.ECONOMICS])
        progress = student.get_progress(Discipline.ECONOMICS)
        progress.current_level = Level.DOCTORAL
        for mod in curriculum_loader.get_modules_for_level(Discipline.ECONOMICS, Level.DOCTORAL):
            progress.module_scores[mod.id] = ModuleScore(module_id=mod.id, score=0.96)
        # Defense with 2 Accept, 3 Minor Revision — should NOT pass doctoral
        # (doctoral needs 3/5 Accept specifically)
        progress.defenses.append(DefenseResult(
            capstone_id=uuid4(),
            level=Level.DOCTORAL,
            reviewer_verdicts={
                "AER": Verdict.ACCEPT,
                "QJE": Verdict.ACCEPT,
                "Econometrica": Verdict.MINOR_REVISION,
                "JPE": Verdict.MINOR_REVISION,
                "ReStud": Verdict.MINOR_REVISION,
            },
            overall_pass=False,
        ))
        status = gate.evaluate_gate(student, Discipline.ECONOMICS, Level.DOCTORAL)
        assert status == GateStatus.READY_FOR_ASSESSMENT  # Defense didn't pass

    def test_blocking_modules(self, gate, curriculum_loader):
        student = Student(name="Blocked", enrolled_disciplines=[Discipline.ECONOMICS])
        progress = student.get_progress(Discipline.ECONOMICS)
        # Score some but not all foundation modules
        progress.module_scores["ECON-F-001"] = ModuleScore(module_id="ECON-F-001", score=0.95)
        progress.module_scores["ECON-F-002"] = ModuleScore(module_id="ECON-F-002", score=0.70)
        blocking = gate.get_blocking_modules(student, Discipline.ECONOMICS, Level.FOUNDATION)
        assert "ECON-F-002" in blocking  # Below 90% threshold
        assert "ECON-F-001" not in blocking
        # Unscored modules should also be blocking
        assert "ECON-F-003" in blocking

    def test_can_attempt_defense_false(self, gate):
        student = Student(name="Not Ready", enrolled_disciplines=[Discipline.ECONOMICS])
        assert not gate.can_attempt_defense(student, Discipline.ECONOMICS, Level.UNDERGRADUATE)

    def test_can_attempt_defense_true(self, gate, curriculum_loader):
        student = Student(name="Ready", enrolled_disciplines=[Discipline.ECONOMICS])
        progress = student.get_progress(Discipline.ECONOMICS)
        for mod in curriculum_loader.get_modules_for_level(Discipline.ECONOMICS, Level.UNDERGRADUATE):
            progress.module_scores[mod.id] = ModuleScore(module_id=mod.id, score=0.96)
        assert gate.can_attempt_defense(student, Discipline.ECONOMICS, Level.UNDERGRADUATE)
