"""Adaptive remediation — detect weaknesses and generate targeted review material."""

from __future__ import annotations

from phd_platform.llm.client import LLMClient

from phd_platform.config import get_settings
from phd_platform.core.enums import Discipline
from phd_platform.core.models import Module, Student
from phd_platform.curriculum.loader import CurriculumLoader


class AdaptiveRemediator:
    """Traces weakness areas back through prerequisite chains and generates
    targeted remediation content.

    When a student scores below 80% on a module:
    1. Identify specific weakness areas from the assessment
    2. Trace prerequisites backward to find root cause
    3. Generate targeted review material for the root weakness
    4. Reassess after remediation before allowing retry
    """

    WEAKNESS_THRESHOLD = 0.80
    MAX_REMEDIATION_DEPTH = 2  # How many prerequisite levels to trace back

    def __init__(self, client: LLMClient, curriculum: CurriculumLoader):
        self.client = client
        self.curriculum = curriculum

    def identify_root_weaknesses(
        self, student: Student, discipline: Discipline, module_id: str
    ) -> list[Module]:
        """Trace backward through prerequisites to find the root cause of weakness.

        If a student fails Advanced Econometrics, the root cause might be
        gaps in Linear Algebra or Probability Theory. This method finds those roots.
        """
        progress = student.get_progress(discipline)
        score_data = progress.module_scores.get(module_id)
        if not score_data or score_data.score >= self.WEAKNESS_THRESHOLD:
            return []

        # Get the prerequisite chain
        prereq_chain = self.curriculum.get_prerequisite_chain(module_id)

        # Find prerequisites where the student also has weak scores
        weak_prereqs = []
        for prereq in prereq_chain:
            prereq_score = progress.module_scores.get(prereq.id)
            if not prereq_score or prereq_score.score < self.WEAKNESS_THRESHOLD:
                weak_prereqs.append(prereq)

        # If no weak prerequisites found, the weakness is in the module itself
        if not weak_prereqs:
            return [self.curriculum.get_module(module_id)]

        # Return the earliest (most foundational) weak prerequisites
        return weak_prereqs[:self.MAX_REMEDIATION_DEPTH]

    async def generate_remediation(
        self, module: Module, weakness_areas: list[str]
    ) -> dict:
        """Generate targeted review material for specific weakness areas."""
        settings = get_settings()
        objectives_text = "\n".join(f"- {obj}" for obj in module.objectives)
        weaknesses_text = "\n".join(f"- {w}" for w in weakness_areas)

        prompt = f"""Create targeted remediation material for a student struggling with:

Module: {module.name} ({module.id})
Level: {module.level.value if module.level else 'unknown'}

Module objectives:
{objectives_text}

Specific weakness areas identified:
{weaknesses_text}

Generate:
1. A concise explanation of the core concepts they're missing (2-3 paragraphs)
2. 3 worked examples that build understanding step-by-step
3. 3 practice problems (with solutions) targeting the weak areas
4. Common misconceptions to watch out for
5. Connections to prerequisite knowledge they should review

Calibrate difficulty to remediate gaps, not to challenge at the module's full level."""

        response = await self.client.messages.create(
            model=settings.anthropic_model,
            max_tokens=settings.anthropic_max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return {
            "module_id": module.id,
            "weakness_areas": weakness_areas,
            "remediation_content": response.content[0].text,
        }

    def build_remediation_path(
        self, student: Student, discipline: Discipline, target_module_id: str
    ) -> list[dict]:
        """Build an ordered remediation path from root weakness to target module."""
        root_weaknesses = self.identify_root_weaknesses(
            student, discipline, target_module_id
        )
        path = []
        for mod in root_weaknesses:
            progress = student.get_progress(discipline)
            score_data = progress.module_scores.get(mod.id)
            path.append({
                "module": mod,
                "current_score": score_data.score if score_data else 0.0,
                "weakness_areas": score_data.weakness_areas if score_data else [],
                "required_score": self.WEAKNESS_THRESHOLD,
            })
        return path
