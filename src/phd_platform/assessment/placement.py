"""Placement diagnostics — assess incoming students and identify starting points."""

from __future__ import annotations

from datetime import datetime

from phd_platform.llm.client import LLMClient

from phd_platform.config import get_settings
from phd_platform.core.enums import Discipline, Level
from phd_platform.core.models import DiagnosticQuestion, Module, ModuleScore, Student
from phd_platform.core.parsing import parse_diagnostic_questions, parse_evaluation_result
from phd_platform.curriculum.loader import CurriculumLoader


class PlacementEngine:
    """Generates adaptive diagnostic assessments to place students at the right level.

    The engine works by:
    1. Starting at Foundation level for the chosen discipline
    2. Generating questions that cover each module's learning objectives
    3. If a student scores >= 90% on a module, it's waived
    4. If a student scores < 80%, prerequisite chain remediation is triggered
    5. The student's starting level is the highest level where all prerequisites are met
    """

    def __init__(self, client: LLMClient, curriculum: CurriculumLoader):
        self.client = client
        self.curriculum = curriculum

    async def generate_diagnostic(
        self, discipline: Discipline, module: Module, num_questions: int = 5,
        question_bank: list[dict] | None = None,
    ) -> list[DiagnosticQuestion]:
        """Generate diagnostic questions for a specific module.

        If question_bank is provided (pre-generated from local DB), uses those
        instead of calling the LLM. This enables fully offline operation.
        """
        # Prefer local question bank if available
        if question_bank:
            return [
                DiagnosticQuestion(
                    question=q.get("question", ""),
                    type=q.get("type", "short_answer"),
                    difficulty=q.get("difficulty", 3),
                    objective_index=q.get("objective_index", 0),
                    correct_answer=q.get("correct_answer", ""),
                    rubric=q.get("rubric", ""),
                    partial_credit_criteria=q.get("partial_credit_criteria", ""),
                )
                for q in question_bank[:num_questions]
            ]

        settings = get_settings()
        objectives_text = "\n".join(f"- {obj}" for obj in module.objectives)
        prompt = f"""Generate {num_questions} diagnostic assessment questions for the module:
"{module.name}" ({module.id})

Learning objectives:
{objectives_text}

Requirements:
- Questions should test deep understanding, not just recall
- Include a mix of conceptual, computational, and application questions
- Each question should map to specific learning objectives
- Provide the correct answer and a detailed rubric for each
- Difficulty should be calibrated to {module.level.value if module.level else 'intermediate'} level

Return ONLY a JSON array with fields: question, type (mcq|short_answer|proof|computation),
difficulty (1-5), objective_index, correct_answer, rubric, partial_credit_criteria"""

        response = await self.client.messages.create(
            model=settings.anthropic_model,
            max_tokens=settings.anthropic_max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return parse_diagnostic_questions(response.content[0].text)

    async def evaluate_response(
        self, question: DiagnosticQuestion | dict, student_answer: str, module: Module
    ) -> ModuleScore:
        """Evaluate a student's answer against the rubric using AI."""
        settings = get_settings()
        if isinstance(question, DiagnosticQuestion):
            q_text = question.question
            q_answer = question.correct_answer
            q_rubric = question.rubric
        else:
            q_text = question.get("question", "")
            q_answer = question.get("correct_answer", "")
            q_rubric = question.get("rubric", "")

        prompt = f"""Evaluate this student answer for module {module.id} ({module.name}):

Question: {q_text}
Expected answer: {q_answer}
Rubric: {q_rubric}
Student answer: {student_answer}

Score from 0.0 to 1.0 based on:
- Correctness of the core answer
- Depth of understanding demonstrated
- Proper use of notation and terminology
- Completeness of reasoning

Return ONLY JSON: {{"score": <float>, "feedback": "<string>", "weakness_areas": ["<string>"]}}"""

        response = await self.client.messages.create(
            model=settings.anthropic_model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        result = parse_evaluation_result(response.content[0].text)
        return ModuleScore(
            module_id=module.id,
            score=result.score,
            weakness_areas=result.weakness_areas,
            completed_at=datetime.now(),
        )

    def determine_starting_level(
        self, student: Student, discipline: Discipline, scores: dict[str, float]
    ) -> Level:
        """Determine the highest level a student can start at based on diagnostic scores.

        Walks up from Foundation: if all modules in a level score >= 90%,
        the student is placed into the next level.
        """
        for level in Level:
            modules = self.curriculum.get_modules_for_level(discipline, level)
            if not modules:
                continue
            level_scores = [scores.get(m.id, 0.0) for m in modules]
            avg = sum(level_scores) / len(level_scores) if level_scores else 0.0
            if avg < 0.90:
                return level
        return Level.DOCTORAL

    def identify_gaps(self, scores: dict[str, float], threshold: float = 0.80) -> list[str]:
        """Find modules where the student scored below the weakness threshold."""
        return [mod_id for mod_id, score in scores.items() if score < threshold]
