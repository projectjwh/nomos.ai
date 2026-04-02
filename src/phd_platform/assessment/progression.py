"""Progression gate evaluation — determines if students can advance between levels."""

from __future__ import annotations

from phd_platform.core.enums import Discipline, GateStatus, Level, Verdict
from phd_platform.core.models import DefenseResult, Progress, Student
from phd_platform.curriculum.loader import CurriculumLoader


class ProgressionGate:
    """Evaluates whether a student meets all requirements to advance to the next level.

    Gate requirements:
    - Foundation → Undergraduate: 90% mastery across all foundation modules
    - Undergraduate → Masters: 95% mastery + capstone defense pass (2 reviewers)
    - Masters → Doctoral: 95% mastery + thesis defense pass (3 reviewers)
    - Doctoral completion: Dissertation defense pass (3/5 reviewers accept)
    """

    def __init__(self, curriculum: CurriculumLoader):
        self.curriculum = curriculum

    def evaluate_gate(
        self, student: Student, discipline: Discipline, current_level: Level
    ) -> GateStatus:
        """Check all gate conditions for advancing past current_level."""
        progress = student.get_progress(discipline)
        modules = self.curriculum.get_modules_for_level(discipline, current_level)

        # Check mastery threshold
        if not self._check_mastery(progress, modules, current_level):
            return GateStatus.IN_PROGRESS

        # Foundation only requires mastery, no defense
        if current_level == Level.FOUNDATION:
            return GateStatus.PASSED

        # Higher levels require defense pass
        if not self._check_defense(progress, current_level):
            return GateStatus.READY_FOR_ASSESSMENT

        return GateStatus.PASSED

    def _check_mastery(
        self, progress: Progress, modules: list, level: Level
    ) -> bool:
        """Verify all modules meet the mastery threshold."""
        threshold = level.mastery_threshold
        for mod in modules:
            score = progress.module_scores.get(mod.id)
            if not score or score.score < threshold:
                return False
        return True

    def _check_defense(self, progress: Progress, level: Level) -> bool:
        """Verify defense requirements are met for the level."""
        level_defenses = [d for d in progress.defenses if d.level == level]
        if not level_defenses:
            return False

        latest = max(level_defenses, key=lambda d: d.conducted_at)
        required_panel = level.defense_panel_size

        if level == Level.DOCTORAL:
            # Need majority Accept (not just Minor Revision)
            accept_count = sum(
                1 for v in latest.reviewer_verdicts.values()
                if v == Verdict.ACCEPT
            )
            return accept_count >= (required_panel // 2 + 1)

        # Undergrad/Masters: majority Accept or Minor Revision
        return latest.passing_count >= (required_panel // 2 + 1)

    def get_blocking_modules(
        self, student: Student, discipline: Discipline, level: Level
    ) -> list[str]:
        """Return module IDs that are preventing gate passage."""
        progress = student.get_progress(discipline)
        modules = self.curriculum.get_modules_for_level(discipline, level)
        threshold = level.mastery_threshold
        return [
            mod.id for mod in modules
            if mod.id not in progress.module_scores
            or progress.module_scores[mod.id].score < threshold
        ]

    def can_attempt_defense(
        self, student: Student, discipline: Discipline, level: Level
    ) -> bool:
        """Check if mastery is sufficient to attempt a defense."""
        progress = student.get_progress(discipline)
        modules = self.curriculum.get_modules_for_level(discipline, level)
        return self._check_mastery(progress, modules, level)
