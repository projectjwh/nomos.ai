"""Learning orchestrator — connects all modules into the adaptive learning loop.

This is the integration glue that drives the full student journey:
placement -> tutoring -> assessment -> capstone -> defense -> advancement
"""

from __future__ import annotations

from uuid import uuid4

from phd_platform.llm.client import LLMClient

from phd_platform.assessment.adaptive import AdaptiveRemediator
from phd_platform.assessment.placement import PlacementEngine
from phd_platform.assessment.progression import ProgressionGate
from phd_platform.capstone.evaluator import CapstoneEvaluator
from phd_platform.capstone.generator import CapstoneGenerator
from phd_platform.core.enums import Discipline, GateStatus, Level
from phd_platform.core.exceptions import GateNotReadyError, PrerequisiteNotMetError
from phd_platform.core.models import (
    CapstoneProposal,
    CapstoneSubmission,
    DefenseResult,
    DiagnosticQuestion,
    ModuleScore,
    PreDefenseReview,
    Student,
)
from phd_platform.curriculum.loader import CurriculumLoader
from phd_platform.defense.agents import ReviewerPanel
from phd_platform.defense.session import DefenseSession
from phd_platform.tutor.engine import TutoringEngine


class PlacementResult:
    """Result of a placement diagnostic session."""

    def __init__(
        self,
        starting_level: Level,
        module_scores: dict[str, float],
        gap_modules: list[str],
    ):
        self.starting_level = starting_level
        self.module_scores = module_scores
        self.gap_modules = gap_modules


class LearningOrchestrator:
    """Connects placement -> tutoring -> assessment -> capstone -> defense.

    This orchestrator is the primary API for driving the student learning loop.
    It coordinates all engines and manages state transitions.
    """

    def __init__(self, client: LLMClient, curriculum: CurriculumLoader):
        self.client = client
        self.curriculum = curriculum
        self.placement = PlacementEngine(client, curriculum)
        self.gate = ProgressionGate(curriculum)
        self.remediator = AdaptiveRemediator(client, curriculum)
        self.capstone_gen = CapstoneGenerator(client, curriculum)
        self.capstone_eval = CapstoneEvaluator(client)
        self.reviewer_panel = ReviewerPanel(client)
        self._tutors: dict[str, TutoringEngine] = {}

    # ------------------------------------------------------------------
    # Placement
    # ------------------------------------------------------------------
    async def run_placement(
        self, student: Student, discipline: Discipline
    ) -> PlacementResult:
        """Run adaptive placement diagnostics for a discipline.

        Generates questions for each Foundation module, evaluates responses
        (in a real session the student would answer interactively), and
        determines the starting level.
        """
        foundation_modules = self.curriculum.get_modules_for_level(
            discipline, Level.FOUNDATION
        )
        all_scores: dict[str, float] = {}

        for module in foundation_modules:
            questions = await self.placement.generate_diagnostic(
                discipline, module, num_questions=3
            )
            # In an interactive session, each question would be presented to the student.
            # The orchestrator coordinates this; the actual answer collection is handled
            # by the CLI or API layer via the answer_placement_question method.
            # For now, store the questions for the session to use.
            all_scores[module.id] = 0.0  # Will be populated by answer submissions

        starting_level = self.placement.determine_starting_level(
            student, discipline, all_scores
        )
        gaps = self.placement.identify_gaps(all_scores)

        # Update student progress
        progress = student.get_progress(discipline)
        progress.current_level = starting_level

        return PlacementResult(
            starting_level=starting_level,
            module_scores=all_scores,
            gap_modules=gaps,
        )

    async def evaluate_placement_answer(
        self,
        student: Student,
        discipline: Discipline,
        question: DiagnosticQuestion,
        answer: str,
        module_id: str,
    ) -> ModuleScore:
        """Evaluate a single placement answer and update progress."""
        module = self.curriculum.get_module(module_id)
        score = await self.placement.evaluate_response(question, answer, module)

        # Update student progress
        progress = student.get_progress(discipline)
        existing = progress.module_scores.get(module_id)
        if existing:
            # Average with existing score for this module
            score.score = (existing.score + score.score) / 2
            score.attempts = existing.attempts + 1
        progress.module_scores[module_id] = score

        return score

    # ------------------------------------------------------------------
    # Tutoring
    # ------------------------------------------------------------------
    def get_tutor(self, session_key: str) -> TutoringEngine:
        """Get or create a tutoring engine for a session."""
        if session_key not in self._tutors:
            self._tutors[session_key] = TutoringEngine(self.client)
        return self._tutors[session_key]

    async def start_module_learning(
        self,
        student: Student,
        discipline: Discipline,
        module_id: str,
        message: str,
    ) -> str:
        """Start or continue a tutoring session for a module."""
        module = self.curriculum.get_module(module_id)

        # Check prerequisites
        prereqs = self.curriculum.get_prerequisites(module_id)
        progress = student.get_progress(discipline)
        missing = [
            p.id for p in prereqs
            if p.id not in progress.module_scores
            or progress.module_scores[p.id].score < 0.80
        ]
        if missing:
            raise PrerequisiteNotMetError(module_id, missing)

        # Get weakness areas if available
        score_data = progress.module_scores.get(module_id)
        weakness_areas = score_data.weakness_areas if score_data else None

        session_key = f"{student.id}:{module_id}"
        tutor = self.get_tutor(session_key)
        level = module.level or progress.current_level

        return await tutor.teach(module, level, message, weakness_areas)

    # ------------------------------------------------------------------
    # Assessment
    # ------------------------------------------------------------------
    async def assess_module(
        self, student: Student, discipline: Discipline, module_id: str, answer: str
    ) -> ModuleScore:
        """Run a module assessment and save the score."""
        module = self.curriculum.get_module(module_id)
        questions = await self.placement.generate_diagnostic(
            discipline, module, num_questions=5
        )
        # In a real flow, each question is answered individually.
        # For batch assessment, we evaluate the full answer against all objectives.
        score = await self.placement.evaluate_response(questions[0], answer, module)

        progress = student.get_progress(discipline)
        progress.module_scores[module_id] = score

        return score

    # ------------------------------------------------------------------
    # Progression
    # ------------------------------------------------------------------
    def check_progression(
        self, student: Student, discipline: Discipline
    ) -> GateStatus:
        """Check if the student can advance to the next level."""
        progress = student.get_progress(discipline)
        return self.gate.evaluate_gate(student, discipline, progress.current_level)

    def get_blocking_modules(
        self, student: Student, discipline: Discipline
    ) -> list[str]:
        """Get modules preventing advancement."""
        progress = student.get_progress(discipline)
        return self.gate.get_blocking_modules(
            student, discipline, progress.current_level
        )

    # ------------------------------------------------------------------
    # Remediation
    # ------------------------------------------------------------------
    async def get_remediation(
        self, student: Student, discipline: Discipline, module_id: str
    ) -> dict:
        """Get remediation content for a weak module."""
        path = self.remediator.build_remediation_path(student, discipline, module_id)
        if not path:
            return {"message": "No remediation needed", "path": []}

        # Generate remediation for the root weakness
        root = path[0]
        content = await self.remediator.generate_remediation(
            root["module"], root["weakness_areas"]
        )
        return {"path": path, "content": content}

    # ------------------------------------------------------------------
    # Capstone
    # ------------------------------------------------------------------
    async def generate_capstone(
        self, student: Student, discipline: Discipline
    ) -> list[CapstoneProposal]:
        """Generate personalized capstone proposals for the current level."""
        progress = student.get_progress(discipline)

        # Verify the student is ready for a capstone
        if not self.gate.can_attempt_defense(student, discipline, progress.current_level):
            blocking = self.gate.get_blocking_modules(
                student, discipline, progress.current_level
            )
            raise GateNotReadyError(progress.current_level.value, blocking)

        return await self.capstone_gen.generate_proposals(
            student, discipline, progress.current_level
        )

    async def evaluate_capstone(
        self, paper_text: str, discipline: Discipline, level: Level
    ) -> PreDefenseReview:
        """Run pre-defense review on a capstone paper."""
        return await self.capstone_eval.pre_defense_review(
            paper_text, discipline, level
        )

    # ------------------------------------------------------------------
    # Defense
    # ------------------------------------------------------------------
    async def run_defense(
        self,
        student: Student,
        discipline: Discipline,
        paper_text: str,
        student_respond_fn,
    ) -> DefenseResult:
        """Run a full defense session for the student's capstone.

        Args:
            student: The student being assessed.
            discipline: The discipline of the defense.
            paper_text: The capstone paper text.
            student_respond_fn: async callable(question: str) -> str
                Function that gets the student's response to reviewer questions.
        """
        progress = student.get_progress(discipline)
        level = progress.current_level

        # Get gate configuration to determine which journals review
        disc_curriculum = self.curriculum.get_discipline(discipline)
        level_data = disc_curriculum.levels.get(level.value)
        if level_data and level_data.gate.journals:
            journals = level_data.gate.journals
        else:
            journals = [f"{discipline.value} Reviewer {i+1}" for i in range(level.defense_panel_size)]

        # Assemble the review panel
        panel = self.reviewer_panel.assemble(journals, level)

        # Create a capstone submission record
        submission = CapstoneSubmission(title="Defense Submission", abstract=paper_text[:500])
        progress.capstones.append(submission)

        # Run the defense
        session = DefenseSession(panel, level, submission.id)
        result = await session.run_full_defense(paper_text, student_respond_fn)

        # Save the result
        progress.defenses.append(result)

        # If passed, advance to next level
        if result.overall_pass:
            next_level = level.next
            if next_level:
                progress.current_level = next_level
                progress.gate_statuses[level.value] = GateStatus.PASSED

        return result
