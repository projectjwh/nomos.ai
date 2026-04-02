"""Agent runner and content pipeline — orchestrates agent-to-agent collaboration.

The pipeline:
1. Teachers generate problems while going through each topic/agenda
2. Students solve problems, leaving thought traces and failure patterns
3. Domain expert reviewers evaluate student work and thought processes
4. Professors design research project banks combining different domains

Each interaction is stored as a reusable learning artifact:
- Question banks (from teachers)
- Thought trace exemplars (from students — showing HOW to think, not just answers)
- Review feedback patterns (from reviewers)
- Research project templates (from professors)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from phd_platform.agents.base import Agent, AgentRegistry, AgentRole, PROFILE_TO_MODEL
from phd_platform.agents.professors import PROFESSOR_AGENTS
from phd_platform.agents.reviewers import REVIEWER_AGENTS
from phd_platform.agents.students import STUDENT_AGENTS
from phd_platform.agents.teachers import TEACHER_AGENTS
from phd_platform.config import get_settings
from phd_platform.llm.client import LLMClient


def build_registry() -> AgentRegistry:
    """Create the full agent registry with all personas."""
    registry = AgentRegistry()
    for agents in [STUDENT_AGENTS, TEACHER_AGENTS, PROFESSOR_AGENTS, REVIEWER_AGENTS]:
        for agent in agents:
            registry.register(agent)
    return registry


@dataclass
class ThoughtTrace:
    """A student's thought process while solving a problem."""
    student_id: str
    student_name: str
    module_id: str
    question: str
    approach: str           # How they started
    working: str            # Step-by-step work with annotations
    stuck_points: list[str] # Where they got confused
    wrong_turns: list[str]  # Mistakes they made and (maybe) corrected
    final_answer: str
    followup_questions: list[str]  # Questions they'd ask a tutor
    confidence: str         # "high", "medium", "low", "guessing"
    cognitive_profile: str  # The student's profile that generated this


@dataclass
class ReviewedTrace:
    """A thought trace with expert review annotations."""
    trace: ThoughtTrace
    reviewer_id: str
    reviewer_name: str
    score: float
    strengths: list[str]
    errors: list[str]
    misconceptions: list[str]
    teaching_notes: str  # What a tutor should focus on for this student type


@dataclass
class ResearchProject:
    """A capstone research project designed by a professor."""
    professor_id: str
    title: str
    disciplines: list[str]
    level: str  # undergraduate, masters, doctoral
    question: str
    methodology: str
    data_sources: str
    theoretical_contribution: str
    practical_contribution: str
    stretch_goal: str
    prerequisites: list[str]  # Module IDs needed
    team_composition: str     # What expertise mix is needed
    estimated_weeks: int


class AgentRunner:
    """Runs individual agents with their persona as the system prompt."""

    def __init__(self, client: LLMClient):
        self.client = client

    async def run(self, agent: Agent, user_prompt: str, max_tokens: int = 4096) -> str:
        """Execute an agent with its persona and return the response."""
        settings = get_settings()
        # Route to appropriate model based on cognitive profile
        model_hint = agent.model_hint
        model_map = {
            "haiku": getattr(settings, "tier2_model", settings.ollama_model),
            "sonnet": settings.anthropic_model,
            "opus": settings.tier3_model,
        }
        model = model_map.get(model_hint, settings.anthropic_model)

        response = await self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=agent.system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text


class ContentPipeline:
    """Orchestrates the full agent-to-agent content generation pipeline.

    Usage:
        registry = build_registry()
        pipeline = ContentPipeline(client, registry)

        # Teachers generate problems
        problems = await pipeline.teacher_generates_problems("teacher-econ", "ECON-F-006", 5)

        # Students solve them (leaving thought traces)
        traces = await pipeline.students_solve(problems, "ECON-F-006")

        # Reviewers evaluate the traces
        reviewed = await pipeline.reviewers_evaluate(traces)

        # Professors design research projects
        projects = await pipeline.professors_design_projects("economics", "undergraduate")
    """

    def __init__(self, client: LLMClient, registry: AgentRegistry):
        self.client = client
        self.registry = registry
        self.runner = AgentRunner(client)

    async def teacher_generates_problems(
        self, teacher_id: str, module_id: str, count: int = 5,
        module_name: str = "", objectives: list[str] | None = None,
    ) -> list[dict]:
        """Have a teacher generate problems for a specific module."""
        teacher = self.registry.get(teacher_id)
        objectives_text = "\n".join(f"- {o}" for o in (objectives or []))

        prompt = f"""Generate {count} problems for module {module_id} ({module_name}).

Learning objectives:
{objectives_text if objectives_text else 'Generate problems appropriate for this module.'}

For EACH problem provide:
1. Problem statement (clear, complete)
2. Type: mcq / short_answer / computation / proof
3. Difficulty: 1-5
4. Which objective it tests (by index)
5. Complete solution with step-by-step working
6. Rubric (what earns full/partial credit)
7. Common errors students make on this problem
8. 3-tier hints: (a) conceptual nudge, (b) method suggestion, (c) first step

Return as JSON array with fields: question, type, difficulty, objective_index,
correct_answer, rubric, common_errors, hints"""

        response = await self.runner.run(teacher, prompt)
        from phd_platform.core.parsing import parse_diagnostic_questions
        questions = parse_diagnostic_questions(response)
        return [
            {
                "question": q.question,
                "type": q.type,
                "difficulty": q.difficulty,
                "objective_index": q.objective_index,
                "correct_answer": q.correct_answer,
                "rubric": q.rubric,
                "partial_credit_criteria": q.partial_credit_criteria,
                "generated_by": teacher_id,
            }
            for q in questions
        ]

    async def student_solves(
        self, student_id: str, module_id: str, question: str, correct_answer: str = "",
    ) -> ThoughtTrace:
        """Have a student attempt a problem, producing a thought trace."""
        student = self.registry.get(student_id)

        prompt = f"""Solve this problem. Show your COMPLETE thought process.

Problem: {question}

You MUST show:
1. APPROACH: How you're going to tackle this (what method/strategy)
2. WORKING: Step-by-step solution with annotations like "I think..." or "wait, that's wrong..."
3. STUCK POINTS: If you get stuck, say exactly where and why (don't skip this)
4. WRONG TURNS: If you make a mistake, show it before correcting (or leave it if you don't notice)
5. FINAL ANSWER: Your best answer
6. CONFIDENCE: How confident are you? (high/medium/low/guessing)
7. FOLLOW-UP QUESTIONS: What would you ask a tutor to deepen understanding?

Be authentic to your background and ability level. If you don't know something, show the struggle."""

        response = await self.runner.run(student, prompt)

        # Parse the thought trace (structured extraction from the response)
        return ThoughtTrace(
            student_id=student_id,
            student_name=student.name,
            module_id=module_id,
            question=question,
            approach=self._extract_section(response, "APPROACH"),
            working=self._extract_section(response, "WORKING"),
            stuck_points=self._extract_list(response, "STUCK"),
            wrong_turns=self._extract_list(response, "WRONG"),
            final_answer=self._extract_section(response, "FINAL ANSWER"),
            followup_questions=self._extract_list(response, "FOLLOW-UP"),
            confidence=self._extract_section(response, "CONFIDENCE") or "medium",
            cognitive_profile=student.profile.value,
        )

    async def students_solve(
        self, problems: list[dict], module_id: str
    ) -> list[ThoughtTrace]:
        """Have multiple students solve the same problems (parallel by student)."""
        students = self.registry.students
        traces = []
        for problem in problems:
            for student in students:
                # Match students to appropriate difficulty
                if student.profile.value == "struggling" and problem.get("difficulty", 3) > 3:
                    continue  # Struggling students skip hard problems
                if student.profile.value == "gifted" and problem.get("difficulty", 3) < 3:
                    continue  # Gifted students skip easy problems

                trace = await self.student_solves(
                    student.id, module_id,
                    problem["question"],
                    problem.get("correct_answer", ""),
                )
                traces.append(trace)
        return traces

    async def reviewer_evaluates(
        self, reviewer_id: str, trace: ThoughtTrace, correct_answer: str = "",
    ) -> ReviewedTrace:
        """Have a domain expert review a student's thought trace."""
        reviewer = self.registry.get(reviewer_id)

        prompt = f"""Review this student's attempt at solving a problem.

Student: {trace.student_name} (profile: {trace.cognitive_profile})
Module: {trace.module_id}

Problem: {trace.question}
{f'Correct answer: {correct_answer}' if correct_answer else ''}

Student's approach: {trace.approach}
Student's working: {trace.working}
Student's final answer: {trace.final_answer}
Student's confidence: {trace.confidence}
Stuck points: {'; '.join(trace.stuck_points)}
Wrong turns: {'; '.join(trace.wrong_turns)}
Follow-up questions: {'; '.join(trace.followup_questions)}

Evaluate and return JSON:
{{
  "score": <0.0-1.0>,
  "strengths": ["what the student did well"],
  "errors": ["specific errors in reasoning or computation"],
  "misconceptions": ["underlying misconceptions revealed by this attempt"],
  "teaching_notes": "what a tutor should focus on for a student with this profile"
}}"""

        response = await self.runner.run(reviewer, prompt)
        import json
        from phd_platform.core.parsing import extract_json_from_text
        try:
            data = json.loads(extract_json_from_text(response))
        except Exception:
            data = {"score": 0.5, "strengths": [], "errors": [], "misconceptions": [], "teaching_notes": response}

        return ReviewedTrace(
            trace=trace,
            reviewer_id=reviewer_id,
            reviewer_name=reviewer.name,
            score=data.get("score", 0.5),
            strengths=data.get("strengths", []),
            errors=data.get("errors", []),
            misconceptions=data.get("misconceptions", []),
            teaching_notes=data.get("teaching_notes", ""),
        )

    async def professor_designs_projects(
        self, professor_id: str, disciplines: list[str], level: str, count: int = 3,
    ) -> list[ResearchProject]:
        """Have a professor design capstone research projects."""
        professor = self.registry.get(professor_id)
        disc_text = ", ".join(disciplines)

        prompt = f"""Design {count} capstone research projects for {level}-level students
in {disc_text}.

For EACH project provide:
1. Title (specific, compelling)
2. Disciplines involved and what each contributes
3. Research question (1-2 sentences)
4. Methodology (specific techniques)
5. Data sources (realistic, accessible)
6. Theoretical contribution (what's new in theory)
7. Practical contribution (who benefits and how)
8. Stretch goal (what would make this a top-journal paper)
9. Prerequisites (module IDs or topic areas needed)
10. Team composition (what expertise mix is ideal)
11. Estimated weeks

Return as JSON array with fields: title, disciplines, question, methodology,
data_sources, theoretical_contribution, practical_contribution, stretch_goal,
prerequisites, team_composition, estimated_weeks"""

        response = await self.runner.run(professor, prompt)
        import json
        from phd_platform.core.parsing import extract_json_from_text
        try:
            data = json.loads(extract_json_from_text(response))
            if isinstance(data, dict):
                data = [data]
        except Exception:
            data = []

        projects = []
        for item in data:
            projects.append(ResearchProject(
                professor_id=professor_id,
                title=item.get("title", "Untitled Project"),
                disciplines=item.get("disciplines", disciplines),
                level=level,
                question=item.get("question", ""),
                methodology=item.get("methodology", ""),
                data_sources=item.get("data_sources", ""),
                theoretical_contribution=item.get("theoretical_contribution", ""),
                practical_contribution=item.get("practical_contribution", ""),
                stretch_goal=item.get("stretch_goal", ""),
                prerequisites=item.get("prerequisites", []),
                team_composition=item.get("team_composition", ""),
                estimated_weeks=item.get("estimated_weeks", 12),
            ))
        return projects

    # --- Internal helpers ---

    @staticmethod
    def _extract_section(text: str, header: str) -> str:
        """Extract content under a specific header from agent response."""
        import re
        pattern = rf"(?:^|\n)\s*\d*\.?\s*{header}[:\s]*\n?(.*?)(?=\n\s*\d*\.?\s*[A-Z]{{2,}}[:\s]|\Z)"
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _extract_list(text: str, header: str) -> list[str]:
        """Extract a list of items under a header."""
        section = ContentPipeline._extract_section(text, header)
        if not section:
            return []
        items = []
        for line in section.split("\n"):
            line = line.strip().lstrip("-•*0123456789.)")
            if line:
                items.append(line.strip())
        return items
