"""Defense session orchestration — runs the full defense interaction."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from phd_platform.core.enums import Level, Verdict
from phd_platform.core.models import DefenseResult
from phd_platform.defense.agents import ReviewerAgent


class DefenseSession:
    """Orchestrates a full defense session with a panel of reviewer agents.

    The session follows this flow:
    1. Student submits their paper/presentation
    2. Each reviewer independently reads and prepares questions
    3. Interactive Q&A rounds (configurable number)
    4. Each reviewer renders an independent verdict
    5. Verdicts are aggregated and returned with detailed feedback
    """

    QA_ROUNDS = {
        Level.UNDERGRADUATE: 2,
        Level.MASTERS: 3,
        Level.DOCTORAL: 5,
    }

    def __init__(self, panel: list[ReviewerAgent], level: Level, capstone_id: UUID):
        self.panel = panel
        self.level = level
        self.capstone_id = capstone_id
        self.transcript: list[dict] = []
        self.reviews: dict[str, dict] = {}

    async def run_reviews(self, paper_text: str) -> dict[str, dict]:
        """Phase 1: Each reviewer reads the paper and writes a report."""
        for agent in self.panel:
            review = await agent.review_paper(paper_text)
            self.reviews[agent.journal] = review
            self.transcript.append({
                "phase": "review",
                "journal": agent.journal,
                "content": review["report"],
            })
        return self.reviews

    async def run_qa(self, paper_text: str, student_respond_fn) -> list[dict]:
        """Phase 2: Interactive Q&A session.

        Args:
            paper_text: The submitted paper.
            student_respond_fn: async callable(question: str) -> str
                Function that gets the student's response to a question.
        """
        num_rounds = self.QA_ROUNDS.get(self.level, 3)
        context = ""

        for round_num in range(num_rounds):
            for agent in self.panel:
                question = await agent.ask_question(context, paper_text)
                self.transcript.append({
                    "phase": "qa",
                    "round": round_num + 1,
                    "journal": agent.journal,
                    "role": "reviewer",
                    "content": question,
                })

                response = await student_respond_fn(question)
                self.transcript.append({
                    "phase": "qa",
                    "round": round_num + 1,
                    "journal": agent.journal,
                    "role": "student",
                    "content": response,
                })
                context += f"\n[{agent.journal}]: {question}\n[Student]: {response}\n"

        return self.transcript

    async def run_verdicts(self, paper_text: str) -> DefenseResult:
        """Phase 3: Each reviewer renders a final verdict."""
        qa_text = "\n".join(
            f"[{t['journal']} - {t['role']}]: {t['content']}"
            for t in self.transcript if t["phase"] == "qa"
        )

        verdicts: dict[str, Verdict] = {}
        feedback: dict[str, str] = {}

        for agent in self.panel:
            verdict, justification = await agent.render_verdict(paper_text, qa_text)
            verdicts[agent.journal] = verdict
            feedback[agent.journal] = justification
            self.transcript.append({
                "phase": "verdict",
                "journal": agent.journal,
                "verdict": verdict.value,
                "justification": justification,
            })

        result = DefenseResult(
            capstone_id=self.capstone_id,
            level=self.level,
            reviewer_verdicts=verdicts,
            feedback=feedback,
            conducted_at=datetime.now(),
        )

        # Determine if defense passes based on level-specific criteria
        if self.level == Level.DOCTORAL:
            accept_count = sum(1 for v in verdicts.values() if v == Verdict.ACCEPT)
            result.overall_pass = accept_count >= 3
        else:
            result.overall_pass = result.passing_count > len(self.panel) // 2

        return result

    async def run_full_defense(self, paper_text: str, student_respond_fn) -> DefenseResult:
        """Run the complete defense session end-to-end."""
        await self.run_reviews(paper_text)
        await self.run_qa(paper_text, student_respond_fn)
        return await self.run_verdicts(paper_text)

    def get_transcript(self) -> list[dict]:
        return list(self.transcript)
