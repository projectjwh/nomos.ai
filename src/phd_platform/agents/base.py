"""Agent base class and registry for the nomos.ai subagent system.

Agents are AI personas with distinct expertise, personality, and cognitive
profiles. They collaborate to generate platform content:
  - Teachers create problems and teach through topics
  - Students solve problems, leaving thought traces and failure patterns
  - Professors guide capstone research and design project banks
  - Journal reviewers elevate work to top publication standards
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class AgentRole(str, Enum):
    STUDENT = "student"
    TEACHER = "teacher"
    PROFESSOR = "professor"
    REVIEWER = "reviewer"


class CognitiveProfile(str, Enum):
    """Maps to LLM model quality — simulates different intellect levels."""
    STRUGGLING = "struggling"   # haiku — makes mistakes, gaps, shallow reasoning
    DEVELOPING = "developing"   # sonnet — competent but not brilliant
    ADVANCED = "advanced"       # sonnet (high temp) — strong but occasionally novel
    GIFTED = "gifted"           # opus — deep insight, cross-domain connections


# Model routing by cognitive profile
PROFILE_TO_MODEL = {
    CognitiveProfile.STRUGGLING: "haiku",
    CognitiveProfile.DEVELOPING: "sonnet",
    CognitiveProfile.ADVANCED: "sonnet",
    CognitiveProfile.GIFTED: "opus",
}


@dataclass
class Agent:
    """A subagent with a unique persona, expertise, and cognitive profile."""
    id: str
    name: str
    role: AgentRole
    profile: CognitiveProfile = CognitiveProfile.DEVELOPING
    disciplines: list[str] = field(default_factory=list)
    expertise_tags: list[str] = field(default_factory=list)
    backstory: str = ""
    system_prompt: str = ""
    behavioral_notes: str = ""  # Specific quirks, strengths, weaknesses

    @property
    def model_hint(self) -> str:
        """Suggested LLM model based on cognitive profile."""
        return PROFILE_TO_MODEL.get(self.profile, "sonnet")


class AgentRegistry:
    """Central registry of all subagents."""

    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}

    def register(self, agent: Agent) -> None:
        self._agents[agent.id] = agent

    def get(self, agent_id: str) -> Agent:
        return self._agents[agent_id]

    def by_role(self, role: AgentRole) -> list[Agent]:
        return [a for a in self._agents.values() if a.role == role]

    def by_discipline(self, discipline: str) -> list[Agent]:
        return [a for a in self._agents.values() if discipline in a.disciplines]

    def all(self) -> list[Agent]:
        return list(self._agents.values())

    @property
    def students(self) -> list[Agent]:
        return self.by_role(AgentRole.STUDENT)

    @property
    def teachers(self) -> list[Agent]:
        return self.by_role(AgentRole.TEACHER)

    @property
    def professors(self) -> list[Agent]:
        return self.by_role(AgentRole.PROFESSOR)

    @property
    def reviewers(self) -> list[Agent]:
        return self.by_role(AgentRole.REVIEWER)
