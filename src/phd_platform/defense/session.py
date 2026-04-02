"""Defense session orchestration — with integrity enforcement.

Integrates:
- ResponseCapture: timing + paste detection on every student answer
- SocraticVerifier: follow-up probing when answers seem formulaic
- TimedResponse: flags suspiciously fast responses
"""

from __future__ import annotations

import time
from datetime import datetime
from uuid import UUID

from phd_platform.core.enums import Level, Verdict
from phd_platform.core.models import ConceptEngagement, DefenseResult
from phd_platform.defense.agents import ReviewerAgent
from phd_platform.integrity.socratic import SocraticVerifier
from phd_platform.integrity.telemetry import ResponseCapture
from phd_platform.integrity.timing import TimedResponse


class DefenseSession:
    """Orchestrates a full defense session with integrity enforcement.

    Flow:
    1. Student submits paper
    2. Each reviewer reads and prepares questions
    3. Interactive Q&A with timing + paste detection + Socratic probing
    4. Each reviewer renders verdict (sees integrity flags)
    5. Verdicts aggregated with integrity-adjusted scoring
    """

    BASE_QA_ROUNDS = {
        Level.UNDERGRADUATE: 2,
        Level.MASTERS: 3,
        Level.DOCTORAL: 5,
    }

    def __init__(
        self,
        panel: list[ReviewerAgent],
        level: Level,
        capstone_id: UUID,
        verifier: SocraticVerifier | None = None,
        concept_history: list[ConceptEngagement] | None = None,
    ):
        self.panel = panel
        self.level = level
        self.capstone_id = capstone_id
        self.transcript: list[dict] = []
        self.reviews: dict[str, dict] = {}
        self.verifier = verifier
        self.concept_history = concept_history or []
        self.integrity_capture = ResponseCapture("defense")
        self.integrity_flags: list[dict] = []

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
        """Phase 2: Interactive Q&A with integrity monitoring.

        Wraps student responses with timing capture and optionally
        triggers Socratic follow-up probes for suspicious answers.
        """
        base_rounds = self.BASE_QA_ROUNDS.get(self.level, 3)
        context = ""

        for round_num in range(base_rounds):
            for agent in self.panel:
                question = await agent.ask_question(context, paper_text)
                self.transcript.append({
                    "phase": "qa",
                    "round": round_num + 1,
                    "journal": agent.journal,
                    "role": "reviewer",
                    "content": question,
                })

                # Capture timing on student response
                self.integrity_capture.mark_question_shown()
                response = await student_respond_fn(question)
                event = self.integrity_capture.capture_response(response)

                # Check timing
                elapsed = (event.elapsed_ms or 0) / 1000.0
                timed = TimedResponse.evaluate(response, elapsed, "defense_qa")

                entry = {
                    "phase": "qa",
                    "round": round_num + 1,
                    "journal": agent.journal,
                    "role": "student",
                    "content": response,
                    "elapsed_seconds": round(elapsed, 1),
                }

                if event.flagged or timed.flagged:
                    flag = {
                        "round": round_num + 1,
                        "journal": agent.journal,
                        "reason": event.flag_reason or timed.flag_reason,
                    }
                    self.integrity_flags.append(flag)
                    entry["integrity_flag"] = flag

                self.transcript.append(entry)
                context += f"\n[{agent.journal}]: {question}\n[Student]: {response}\n"

                # Socratic probing: if verifier is available and answer is suspicious
                if self.verifier and await self.verifier.should_probe(
                    response, elapsed, self.concept_history
                ):
                    verification = await self.verifier.verify_understanding(
                        question, response, self.concept_history,
                        self.level.value,
                    )
                    self.transcript.append({
                        "phase": "socratic_probe",
                        "round": round_num + 1,
                        "journal": agent.journal,
                        "depth_rating": verification.depth_rating,
                        "followup_count": verification.followup_count,
                        "flags": verification.flags,
                    })
                    if verification.flags:
                        for f in verification.flags:
                            self.integrity_flags.append({
                                "round": round_num + 1,
                                "journal": agent.journal,
                                "reason": f"Socratic probe: {f}",
                            })
                    context += f"\n[Socratic probe: depth={verification.depth_rating}]\n"

        return self.transcript

    async def run_verdicts(self, paper_text: str) -> DefenseResult:
        """Phase 3: Each reviewer renders a final verdict.

        Reviewers see integrity flags in their context.
        """
        qa_text = "\n".join(
            f"[{t['journal']} - {t['role']}]: {t['content']}"
            for t in self.transcript if t.get("phase") == "qa"
        )

        # Add integrity summary for reviewers
        if self.integrity_flags:
            qa_text += "\n\n--- INTEGRITY FLAGS ---\n"
            for flag in self.integrity_flags:
                qa_text += f"Round {flag['round']} ({flag['journal']}): {flag['reason']}\n"

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

        # Determine pass/fail
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

    def get_integrity_summary(self) -> dict:
        """Summary of integrity flags for this defense."""
        return {
            "total_flags": len(self.integrity_flags),
            "paste_flags": sum(1 for f in self.integrity_flags if "Paste" in f.get("reason", "")),
            "timing_flags": sum(1 for f in self.integrity_flags if "timing" in f.get("reason", "").lower()),
            "socratic_flags": sum(1 for f in self.integrity_flags if "Socratic" in f.get("reason", "")),
            "flags": self.integrity_flags,
        }
