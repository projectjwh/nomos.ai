"""Journal reviewer AI agents for defense sessions."""

from __future__ import annotations

from pathlib import Path

import yaml
from phd_platform.llm.client import LLMClient

from phd_platform.config import get_settings
from phd_platform.core.enums import Level, Verdict
from phd_platform.core.parsing import parse_verdict


class ReviewerAgent:
    """An AI agent that role-plays as a specific journal reviewer.

    Each agent adopts the reviewing style, focus areas, and standards of a
    particular academic journal. The persona is loaded from defense_personas.yaml.
    """

    def __init__(
        self,
        client: LLMClient,
        journal: str,
        persona: dict,
        difficulty: str = "rigorous",
    ):
        self.client = client
        self.journal = journal
        self.persona_name = persona.get("persona_name", f"{journal} Referee")
        self.review_focus = persona.get("review_focus", [])
        self.questioning_style = persona.get("questioning_style", "")
        self.common_concerns = persona.get("common_concerns", [])
        self.rubric_weights = persona.get("rubric_weights", {})
        self.rejection_triggers = persona.get("rejection_triggers", [])
        self.difficulty = difficulty

    def _build_system_prompt(self) -> str:
        focus = "\n".join(f"- {f}" for f in self.review_focus)
        concerns = "\n".join(f"- {c}" for c in self.common_concerns)
        triggers = "\n".join(f"- {t}" for t in self.rejection_triggers)

        return f"""You are {self.persona_name}, a reviewer for {self.journal}.

Your reviewing style: {self.questioning_style}

Your primary evaluation criteria:
{focus}

Common concerns you raise:
{concerns}

You will reject papers that:
{triggers}

Evaluation rubric weights:
- Methodology: {self.rubric_weights.get('methodology', 0.25):.0%}
- Novelty: {self.rubric_weights.get('novelty', 0.25):.0%}
- Significance: {self.rubric_weights.get('significance', 0.25):.0%}
- Exposition: {self.rubric_weights.get('exposition', 0.25):.0%}

Difficulty mode: {self.difficulty}
- constructive: Focus on helping the student improve. Be encouraging but honest.
- rigorous: Expect publishable quality. Probe weaknesses thoroughly.
- adversarial: Simulate real peer review. Find fatal flaws. Be tough but fair.

You must provide:
1. A detailed referee report (2-3 paragraphs)
2. Specific questions for the Q&A session
3. A verdict: Accept, Minor Revision, Major Revision, or Reject
4. Actionable feedback for improvement"""

    async def review_paper(self, paper_text: str) -> dict:
        """Read and evaluate a submitted paper."""
        settings = get_settings()
        response = await self.client.messages.create(
            model=settings.anthropic_model,
            max_tokens=settings.anthropic_max_tokens,
            system=self._build_system_prompt(),
            messages=[{
                "role": "user",
                "content": f"Please review the following paper submission:\n\n{paper_text}",
            }],
        )
        return {"journal": self.journal, "report": response.content[0].text}

    async def ask_question(self, context: str, paper_text: str) -> str:
        """Generate a probing question during the Q&A defense session."""
        settings = get_settings()
        response = await self.client.messages.create(
            model=settings.anthropic_model,
            max_tokens=1024,
            system=self._build_system_prompt(),
            messages=[
                {"role": "user", "content": f"Paper:\n{paper_text}\n\nDefense context so far:\n{context}"},
                {"role": "assistant", "content": "Based on my review and the discussion so far, I'd like to ask:"},
            ],
        )
        return response.content[0].text

    async def render_verdict(self, paper_text: str, qa_transcript: str) -> tuple[Verdict, str]:
        """Render a final verdict after the Q&A session."""
        settings = get_settings()
        response = await self.client.messages.create(
            model=settings.anthropic_model,
            max_tokens=2048,
            system=self._build_system_prompt(),
            messages=[{
                "role": "user",
                "content": f"""Based on the paper and defense Q&A, render your final verdict.

Paper:
{paper_text}

Q&A Transcript:
{qa_transcript}

Return ONLY JSON: {{"verdict": "Accept|Minor Revision|Major Revision|Reject", "justification": "...", "strengths": [...], "weaknesses": [...], "suggestions": [...]}}""",
            }],
        )
        result = parse_verdict(response.content[0].text)
        # Map parsed verdict string to Verdict enum
        verdict_map = {v.value.lower(): v for v in Verdict}
        verdict = verdict_map.get(result.verdict.lower(), Verdict.MAJOR_REVISION)
        return verdict, result.justification or response.content[0].text


class ReviewerPanel:
    """Assembles a panel of reviewer agents for a defense session."""

    def __init__(self, client: LLMClient, config_path: Path | None = None):
        self.client = client
        self.config_path = config_path or (
            Path(__file__).resolve().parents[3] / "config" / "defense_personas.yaml"
        )
        self._personas: dict = {}
        self._load_personas()

    def _load_personas(self) -> None:
        with open(self.config_path) as f:
            self._personas = yaml.safe_load(f)

    def _get_difficulty(self, level: Level) -> str:
        scaling = self._personas.get("defense_config", {}).get("difficulty_scaling", {})
        return scaling.get(level.value, "rigorous")

    def _find_persona(self, journal_name: str) -> dict:
        """Search all reviewer categories for a matching journal persona."""
        for category_key in [
            "economics_reviewers", "ai_ml_reviewers", "cs_reviewers",
            "data_science_reviewers", "finance_reviewers",
        ]:
            reviewers = self._personas.get(category_key, [])
            for reviewer in reviewers:
                if reviewer.get("journal", "").lower() in journal_name.lower():
                    return reviewer
        return {}

    def assemble(self, journals: list[str], level: Level) -> list[ReviewerAgent]:
        """Create a panel of reviewer agents for the specified journals and level."""
        difficulty = self._get_difficulty(level)
        agents = []
        for journal in journals:
            persona = self._find_persona(journal)
            if persona:
                agents.append(ReviewerAgent(
                    client=self.client,
                    journal=journal,
                    persona=persona,
                    difficulty=difficulty,
                ))
        return agents
