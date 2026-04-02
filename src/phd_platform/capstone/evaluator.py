"""Capstone evaluation — pre-defense quality checks and feedback."""

from __future__ import annotations

from phd_platform.llm.client import LLMClient

from phd_platform.config import get_settings
from phd_platform.core.enums import Discipline, Level
from phd_platform.core.models import PreDefenseReview
from phd_platform.core.parsing import parse_pre_defense_review


class CapstoneEvaluator:
    """Evaluates capstone submissions before they go to defense.

    Provides feedback on:
    - Writing quality and structure
    - Methodological soundness
    - Completeness of analysis
    - Readiness for defense
    """

    def __init__(self, client: LLMClient):
        self.client = client

    async def pre_defense_review(
        self, paper_text: str, discipline: Discipline, level: Level
    ) -> PreDefenseReview:
        """Run a pre-defense quality check on the capstone paper."""
        settings = get_settings()
        prompt = f"""You are a senior academic advisor reviewing a {level.value}-level
{discipline.value} capstone paper BEFORE it goes to defense.

Your job is to identify issues the student should fix before facing the panel.
Be specific, constructive, and thorough.

Paper:
{paper_text}

Return ONLY JSON with this structure:
{{
  "dimension_scores": [
    {{"dimension": "Clarity & Structure", "score": <1-5>, "issues": [...], "suggestions": [...]}},
    {{"dimension": "Methodology", "score": <1-5>, "issues": [...], "suggestions": [...]}},
    {{"dimension": "Literature Review", "score": <1-5>, "issues": [...], "suggestions": [...]}},
    {{"dimension": "Results", "score": <1-5>, "issues": [...], "suggestions": [...]}},
    {{"dimension": "Contribution", "score": <1-5>, "issues": [...], "suggestions": [...]}}
  ],
  "overall_assessment": "READY|NEEDS REVISION|NOT READY",
  "predicted_questions": ["question 1", "question 2", "question 3"],
  "summary": "overall review summary"
}}"""

        response = await self.client.messages.create(
            model=settings.anthropic_model,
            max_tokens=settings.anthropic_max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return parse_pre_defense_review(response.content[0].text)

    async def check_originality(self, paper_text: str) -> dict:
        """Check the paper for originality and proper attribution."""
        settings = get_settings()
        prompt = f"""Analyze this academic paper for originality concerns:

{paper_text[:8000]}

Check for:
1. Are claims properly attributed to sources?
2. Does the paper clearly distinguish its contribution from prior work?
3. Are there passages that seem derivative without attribution?
4. Is the methodology original or properly cited as borrowed?

Return JSON: {{"score": <0.0-1.0>, "concerns": [...], "summary": "..."}}"""

        response = await self.client.messages.create(
            model=settings.anthropic_model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return {"originality_check": response.content[0].text}
