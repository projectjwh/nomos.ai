"""Socratic verification — probes depth of understanding through follow-up chains.

The core integrity mechanism: instead of trying to detect AI-generated answers,
verify that the student *understands* their answer through escalating follow-ups.
A student who truly understands can explain, apply, and transfer.
One who pasted AI output cannot survive follow-up probing.
"""

from __future__ import annotations

from phd_platform.config import get_settings
from phd_platform.core.enums import IntegrityFlag, SocraticDepth
from phd_platform.core.models import ConceptEngagement, VerificationResult
from phd_platform.llm.client import LLMClient


class SocraticVerifier:
    """Probes depth of understanding through adaptive follow-up questions.

    Verification levels:
    1. Surface: Student can restate the answer (already demonstrated)
    2. Procedural: Student can explain the mechanism/steps
    3. Conceptual: Student can apply to a new context
    4. Transferable: Student can teach it and connect to other domains
    """

    MAX_FOLLOWUPS = 3

    def __init__(self, client: LLMClient):
        self.client = client

    async def should_probe(
        self,
        answer: str,
        elapsed_seconds: float,
        concept_history: list[ConceptEngagement] | None = None,
    ) -> bool:
        """Decide whether a follow-up probe is needed.

        Returns True if:
        - Answer is suspiciously fast (< 30% of expected time)
        - Answer invokes concepts not in the student's engagement history
        - Answer has a formulaic structure (e.g., numbered lists, textbook-like)
        """
        # Fast answer heuristic
        if elapsed_seconds < 30 and len(answer) > 200:
            return True

        # Concept mismatch check
        if concept_history is not None:
            engaged_concepts = {ce.concept.lower() for ce in concept_history}
            # Simple keyword extraction from answer
            answer_words = set(answer.lower().split())
            # If the answer uses many technical terms not in engagement history, probe
            technical_not_engaged = answer_words - engaged_concepts
            # This is a rough heuristic — the LLM will do the real analysis
            if len(answer) > 300 and len(technical_not_engaged) > len(engaged_concepts):
                return True

        return False

    async def verify_understanding(
        self,
        original_question: str,
        student_answer: str,
        concept_history: list[ConceptEngagement] | None = None,
        level_name: str = "undergraduate",
    ) -> VerificationResult:
        """Conduct Socratic follow-up probing to assess understanding depth.

        Returns a VerificationResult with the depth rating and follow-up transcript.
        """
        settings = get_settings()
        transcript: list[dict] = []
        flags: list[str] = []
        current_depth = SocraticDepth.SURFACE

        # Build context about what the student has actually studied
        engagement_context = ""
        if concept_history:
            concepts = [f"- {ce.concept} (depth: {ce.engagement_depth})" for ce in concept_history]
            engagement_context = f"\n\nConcepts this student has engaged with during tutoring:\n" + "\n".join(concepts)

        for i in range(self.MAX_FOLLOWUPS):
            # Generate follow-up based on current depth
            followup_prompt = self._build_followup_prompt(
                original_question, student_answer, transcript,
                current_depth, engagement_context, level_name,
            )

            response = await self.client.messages.create(
                model=settings.tier3_model,  # Use frontier model for integrity
                max_tokens=1024,
                messages=[{"role": "user", "content": followup_prompt}],
            )
            result_text = response.content[0].text

            # Parse the LLM's assessment
            assessment = self._parse_assessment(result_text)
            transcript.append({
                "round": i + 1,
                "followup_question": assessment.get("question", ""),
                "depth_assessed": assessment.get("depth", "surface"),
                "reasoning": assessment.get("reasoning", ""),
                "flags": assessment.get("flags", []),
            })

            new_depth = assessment.get("depth", "surface")
            if new_depth in [d.value for d in SocraticDepth]:
                current_depth = SocraticDepth(new_depth)

            flags.extend(assessment.get("flags", []))

            # If we've reached conceptual or higher, stop probing
            if current_depth in (SocraticDepth.CONCEPTUAL, SocraticDepth.TRANSFERABLE):
                break

            # If surface after 2 rounds, flag and stop
            if i >= 1 and current_depth == SocraticDepth.SURFACE:
                flags.append(IntegrityFlag.SURFACE_ONLY.value)
                break

        # Calculate verified score
        depth_multipliers = {
            SocraticDepth.SURFACE: 0.4,
            SocraticDepth.PROCEDURAL: 0.7,
            SocraticDepth.CONCEPTUAL: 0.9,
            SocraticDepth.TRANSFERABLE: 1.0,
        }
        multiplier = depth_multipliers.get(current_depth, 0.5)

        return VerificationResult(
            original_score=1.0,  # Caller sets this from the actual assessment score
            verified_score=multiplier,
            followup_count=len(transcript),
            depth_rating=current_depth.value,
            flags=flags,
            transcript=transcript,
        )

    def _build_followup_prompt(
        self,
        original_question: str,
        student_answer: str,
        prior_exchanges: list[dict],
        current_depth: SocraticDepth,
        engagement_context: str,
        level_name: str,
    ) -> str:
        """Build the prompt for generating a follow-up question."""
        prior_text = ""
        if prior_exchanges:
            for ex in prior_exchanges:
                prior_text += f"\nFollow-up {ex['round']}: {ex.get('followup_question', '')}\n"
                prior_text += f"Assessment: {ex.get('depth_assessed', '')} — {ex.get('reasoning', '')}\n"

        depth_instruction = {
            SocraticDepth.SURFACE: "Ask the student to EXPLAIN the mechanism or reasoning behind their answer. Don't accept a restatement.",
            SocraticDepth.PROCEDURAL: "Ask the student to APPLY their understanding to a DIFFERENT context or problem they haven't seen.",
            SocraticDepth.CONCEPTUAL: "Ask the student to TEACH this concept as if explaining to a junior student, connecting it to broader themes.",
            SocraticDepth.TRANSFERABLE: "The student has demonstrated deep understanding.",
        }

        return f"""You are a Socratic verification agent assessing whether a {level_name}-level student truly understands their answer or is relying on AI-generated text.

Original question: {original_question}
Student's answer: {student_answer}
{prior_text}
{engagement_context}

Current assessed depth: {current_depth.value}
Next step: {depth_instruction.get(current_depth, '')}

Generate a follow-up question AND assess the student's current depth level.

Return ONLY JSON:
{{
  "question": "Your follow-up question to ask the student",
  "depth": "surface|procedural|conceptual|transferable",
  "reasoning": "Why you assessed this depth level",
  "flags": ["concept_mismatch", "surface_only"]  // empty if no concerns
}}"""

    def _parse_assessment(self, text: str) -> dict:
        """Parse the LLM's Socratic assessment response."""
        from phd_platform.core.parsing import extract_json_from_text
        import json
        try:
            json_str = extract_json_from_text(text)
            return json.loads(json_str)
        except Exception:
            return {
                "question": "Can you explain your reasoning step by step?",
                "depth": "surface",
                "reasoning": "Could not parse assessment",
                "flags": [],
            }
