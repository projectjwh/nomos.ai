"""Interactive tutoring engine — Socratic dialogue for module learning."""

from __future__ import annotations

from phd_platform.llm.client import LLMClient

from phd_platform.config import get_settings
from phd_platform.core.enums import Level
from phd_platform.core.models import Module


class TutoringEngine:
    """AI tutor that teaches module content through interactive Socratic dialogue.

    The engine adapts its teaching style based on:
    - The student's current level
    - Their demonstrated weaknesses
    - The specific module being taught
    - Prior conversation context

    Teaching methodology:
    - Foundation: Concrete examples -> intuition -> formal statement
    - Undergraduate: Motivation -> theorem -> proof -> applications
    - Masters: Problem -> literature -> approach -> execution -> reflection
    - Doctoral: Open question -> research frontier -> methodology -> contribution
    """

    STYLE_PROMPTS = {
        Level.FOUNDATION: """You are a patient, encouraging tutor for a student refreshing
foundational knowledge. Use concrete examples and build intuition before introducing
formal notation. Check understanding frequently with simple questions. Connect new
concepts to things they already know. Never make them feel bad for not knowing something.""",

        Level.UNDERGRADUATE: """You are a rigorous but supportive professor teaching an
advanced undergraduate course at a top university. Present material with full mathematical
precision. Motivate theorems before proving them. Assign challenging problems and walk
through solutions step-by-step when asked. Push the student to think deeply.""",

        Level.MASTERS: """You are a PhD advisor guiding a graduate student through advanced
material. Emphasize connections between theory and empirical application. Discuss the
research frontier and open questions. When the student gets something wrong, ask probing
questions rather than giving the answer directly. Expect professional-level discourse.""",

        Level.DOCTORAL: """You are a senior colleague and research collaborator. Engage as
an intellectual equal. Challenge assumptions, suggest alternative approaches, and debate
the merits of different methodological choices. Focus on original thinking, not textbook
answers. Push toward publishable insights.""",
    }

    def __init__(self, client: LLMClient):
        self.client = client
        self.conversation_history: list[dict] = []

    def _build_system_prompt(self, module: Module, level: Level) -> str:
        style = self.STYLE_PROMPTS.get(level, self.STYLE_PROMPTS[Level.UNDERGRADUATE])
        objectives = "\n".join(f"- {obj}" for obj in module.objectives)
        books = "\n".join(f"- {b}" for b in module.textbooks)

        return f"""{style}

You are currently teaching: {module.name} ({module.id})

Learning objectives for this module:
{objectives}

Reference textbooks:
{books if books else 'No specific textbooks assigned'}

Guidelines:
- Stay focused on the module's learning objectives
- Use LaTeX notation for math (wrapped in $ for inline, $$ for display)
- When introducing a concept, first check what the student already knows
- Provide worked examples when appropriate
- If the student seems to understand, increase difficulty gradually
- Track which objectives have been covered in the conversation
- Periodically check comprehension with targeted questions"""

    async def teach(
        self,
        module: Module,
        level: Level,
        student_message: str,
        weakness_areas: list[str] | None = None,
    ) -> str:
        """Process a student message and generate a tutoring response."""
        settings = get_settings()
        system = self._build_system_prompt(module, level)

        if weakness_areas and not self.conversation_history:
            # First message with known weaknesses — address them proactively
            weakness_context = (
                "\n\nNote: This student has demonstrated weakness in these areas: "
                + ", ".join(weakness_areas)
                + ". Gently address these gaps as you teach."
            )
            system += weakness_context

        self.conversation_history.append({"role": "user", "content": student_message})

        response = await self.client.messages.create(
            model=settings.anthropic_model,
            max_tokens=settings.anthropic_max_tokens,
            system=system,
            messages=self.conversation_history,
        )

        assistant_message = response.content[0].text
        self.conversation_history.append({"role": "assistant", "content": assistant_message})
        return assistant_message

    async def generate_practice_problem(
        self, module: Module, level: Level, difficulty: int = 3
    ) -> str:
        """Generate a practice problem calibrated to the student's level."""
        settings = get_settings()
        objectives = "\n".join(f"- {obj}" for obj in module.objectives)
        prompt = f"""Generate a practice problem for {module.name} at difficulty {difficulty}/5.

Learning objectives:
{objectives}

Level: {level.value}

Provide:
1. The problem statement (clear, complete, well-formatted)
2. Hints (hidden, 3 progressive hints from subtle to obvious)
3. Full solution with step-by-step working
4. Grading rubric (what earns full marks vs partial credit)"""

        response = await self.client.messages.create(
            model=settings.anthropic_model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    def reset_conversation(self) -> None:
        """Clear conversation history for a new topic or session."""
        self.conversation_history.clear()
