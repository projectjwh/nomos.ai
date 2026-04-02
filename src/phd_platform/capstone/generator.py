"""Capstone project generation — creates personalized research projects."""

from __future__ import annotations

from phd_platform.llm.client import LLMClient

from phd_platform.config import get_settings
from phd_platform.core.enums import Discipline, Level
from phd_platform.core.models import CapstoneProposal, Student
from phd_platform.core.parsing import parse_capstone_proposals
from phd_platform.curriculum.loader import CurriculumLoader


class CapstoneGenerator:
    """Generates personalized capstone projects based on student interests,
    strengths, and current research trends.

    Each capstone is customized to:
    - The student's declared interests and career goals
    - Their strongest modules (demonstrated through assessment scores)
    - The discipline and level requirements
    - Current research frontiers in the field
    """

    # Capstone complexity expectations by level
    LEVEL_EXPECTATIONS = {
        Level.UNDERGRADUATE: {
            "scope": "Original empirical paper or implementation project",
            "length": "20-30 pages",
            "methods": "At least one rigorous method from coursework",
            "originality": "Novel application of known methods to new data/context",
            "timeline_weeks": 8,
        },
        Level.MASTERS: {
            "scope": "Working paper of near-publishable quality",
            "length": "30-50 pages with appendix",
            "methods": "Advanced methods with proper identification/proofs",
            "originality": "Meaningful contribution to the literature",
            "timeline_weeks": 12,
        },
        Level.DOCTORAL: {
            "scope": "Three-essay dissertation suitable for top journal submission",
            "length": "Each essay 25-40 pages; dissertation 100+ pages total",
            "methods": "State-of-the-art or novel methodology",
            "originality": "Must advance the frontier of knowledge",
            "timeline_weeks": 52,
        },
    }

    def __init__(self, client: LLMClient, curriculum: CurriculumLoader):
        self.client = client
        self.curriculum = curriculum

    def _identify_strengths(self, student: Student, discipline: Discipline) -> list[str]:
        """Identify student's strongest areas from their module scores."""
        progress = student.get_progress(discipline)
        scored = [
            (mod_id, score.score)
            for mod_id, score in progress.module_scores.items()
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        top_modules = scored[:5]

        strengths = []
        for mod_id, score in top_modules:
            try:
                mod = self.curriculum.get_module(mod_id)
                strengths.append(f"{mod.name} ({score:.0%})")
            except KeyError:
                continue
        return strengths

    async def generate_proposals(
        self,
        student: Student,
        discipline: Discipline,
        level: Level,
        num_proposals: int = 3,
    ) -> list[CapstoneProposal]:
        """Generate personalized capstone project proposals."""
        settings = get_settings()
        strengths = self._identify_strengths(student, discipline)
        expectations = self.LEVEL_EXPECTATIONS.get(level, self.LEVEL_EXPECTATIONS[Level.MASTERS])
        disc_curriculum = self.curriculum.get_discipline(discipline)

        prompt = f"""Generate {num_proposals} capstone project proposals for a {level.value}-level
{disc_curriculum.name} student.

Student profile:
- Interests: {', '.join(student.interests) if student.interests else 'Not specified'}
- Strengths: {', '.join(strengths) if strengths else 'Still being assessed'}
- Level: {level.value}

Capstone expectations:
- Scope: {expectations['scope']}
- Length: {expectations['length']}
- Methods: {expectations['methods']}
- Originality: {expectations['originality']}
- Timeline: {expectations['timeline_weeks']} weeks

Return ONLY a JSON array of {num_proposals} objects with fields:
title, research_question, methodology, data_sources, contribution, milestones, risks

Make proposals progressively ambitious:
- Proposal 1: Achievable with current skills, builds confidence
- Proposal 2: Stretches capabilities, requires learning something new
- Proposal 3: Ambitious, high-impact if successful, higher risk"""

        response = await self.client.messages.create(
            model=settings.anthropic_model,
            max_tokens=settings.anthropic_max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return parse_capstone_proposals(response.content[0].text)

    async def consult(
        self, student: Student, discipline: Discipline, question: str, context: str = ""
    ) -> str:
        """Provide AI consultation on an in-progress capstone project."""
        settings = get_settings()
        prompt = f"""You are an academic advisor for a {discipline.value} capstone project.

Student: {student.name}
Interests: {', '.join(student.interests)}

Project context:
{context}

Student's question:
{question}

Provide helpful, specific guidance. Be honest about potential issues.
If the student is going down a wrong path, explain why and suggest alternatives.
If the approach is sound, validate it and suggest next steps."""

        response = await self.client.messages.create(
            model=settings.anthropic_model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
