"""Concept fingerprinting — builds unique learning trajectories from tutoring history.

Instead of generic plagiarism detection, this compares the student's paper
against their actual learning journey. A paper should reflect concepts the
student genuinely engaged with, using framings they developed during tutoring.
"""

from __future__ import annotations

from phd_platform.config import get_settings
from phd_platform.core.models import ConceptEngagement, OriginalityScore
from phd_platform.llm.client import LLMClient


class StudentFingerprint:
    """A student's unique learning trajectory."""

    def __init__(
        self,
        student_id: str,
        concepts: list[ConceptEngagement],
        misconceptions: list[str] = None,
        unique_framings: list[str] = None,
    ):
        self.student_id = student_id
        self.concepts = concepts
        self.misconceptions = misconceptions or []
        self.unique_framings = unique_framings or []

    @property
    def concept_set(self) -> set[str]:
        return {c.concept.lower() for c in self.concepts}

    @property
    def deep_concepts(self) -> set[str]:
        """Concepts with engagement depth >= 3 (applied or taught back)."""
        return {c.concept.lower() for c in self.concepts if c.engagement_depth >= 3}


class ConceptFingerprinter:
    """Builds and uses student learning fingerprints for originality scoring."""

    def __init__(self, client: LLMClient):
        self.client = client

    async def build_fingerprint(
        self, student_id: str, tutoring_histories: dict[str, list[dict]]
    ) -> StudentFingerprint:
        """Analyze tutoring session histories to extract the student's unique trajectory.

        Args:
            student_id: The student ID.
            tutoring_histories: {module_id: [conversation messages]}
        """
        if not tutoring_histories:
            return StudentFingerprint(student_id=student_id, concepts=[])

        settings = get_settings()

        # Combine all tutoring into a summary for analysis
        all_text = ""
        for module_id, messages in tutoring_histories.items():
            student_msgs = [m["content"] for m in messages if m.get("role") == "user"]
            if student_msgs:
                all_text += f"\n--- Module {module_id} ---\n"
                all_text += "\n".join(student_msgs[:20])  # Limit per module

        if not all_text.strip():
            return StudentFingerprint(student_id=student_id, concepts=[])

        prompt = f"""Analyze these tutoring session transcripts (student messages only) to build a learning fingerprint.

{all_text[:6000]}

Extract and return ONLY JSON:
{{
  "concepts": [
    {{"concept": "concept name", "module_id": "MOD-ID", "engagement_depth": 1-4, "evidence": "brief quote"}}
  ],
  "misconceptions": ["misconception the student demonstrated and was corrected on"],
  "unique_framings": ["unique analogies, metaphors, or ways of explaining that are specific to this student"]
}}

Engagement depth scale: 1=mentioned, 2=discussed, 3=applied in a problem, 4=taught back or explained to tutor"""

        response = await self.client.messages.create(
            model=settings.tier3_model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )

        from phd_platform.core.parsing import extract_json_from_text
        import json
        try:
            data = json.loads(extract_json_from_text(response.content[0].text))
        except Exception:
            return StudentFingerprint(student_id=student_id, concepts=[])

        concepts = [
            ConceptEngagement(
                concept=c.get("concept", ""),
                module_id=c.get("module_id", ""),
                engagement_depth=c.get("engagement_depth", 1),
                evidence=c.get("evidence", ""),
            )
            for c in data.get("concepts", [])
        ]

        return StudentFingerprint(
            student_id=student_id,
            concepts=concepts,
            misconceptions=data.get("misconceptions", []),
            unique_framings=data.get("unique_framings", []),
        )

    async def score_originality(
        self, paper_text: str, fingerprint: StudentFingerprint
    ) -> OriginalityScore:
        """Score how well a paper reflects the student's actual learning trajectory."""
        if not fingerprint.concepts:
            return OriginalityScore(
                score=0.5,
                trajectory_match=0.0,
                concept_coverage=0.0,
                concerns=["No tutoring history available for fingerprinting"],
            )

        settings = get_settings()
        concepts_text = "\n".join(
            f"- {c.concept} (depth {c.engagement_depth}, module {c.module_id})"
            for c in fingerprint.concepts
        )
        misconceptions_text = "\n".join(f"- {m}" for m in fingerprint.misconceptions)
        framings_text = "\n".join(f"- {f}" for f in fingerprint.unique_framings)

        prompt = f"""Compare this academic paper against the student's learning fingerprint.

PAPER (first 4000 chars):
{paper_text[:4000]}

STUDENT'S LEARNING FINGERPRINT:
Concepts engaged with:
{concepts_text}

Misconceptions demonstrated and corrected:
{misconceptions_text}

Unique framings/analogies used during tutoring:
{framings_text}

Score the paper's originality relative to this specific student's learning journey.

Return ONLY JSON:
{{
  "trajectory_match": <0.0-1.0 how well paper reflects the tutoring journey>,
  "concept_coverage": <0.0-1.0 what fraction of paper concepts appear in tutoring history>,
  "unique_framing_count": <int, how many of student's unique framings appear in paper>,
  "concerns": ["list of specific concerns about authenticity"]
}}"""

        response = await self.client.messages.create(
            model=settings.tier3_model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

        from phd_platform.core.parsing import extract_json_from_text
        import json
        try:
            data = json.loads(extract_json_from_text(response.content[0].text))
        except Exception:
            return OriginalityScore(score=0.5, concerns=["Could not parse originality assessment"])

        trajectory = data.get("trajectory_match", 0.5)
        coverage = data.get("concept_coverage", 0.5)
        score = (trajectory * 0.6) + (coverage * 0.4)  # Weighted average

        return OriginalityScore(
            score=score,
            trajectory_match=trajectory,
            concept_coverage=coverage,
            unique_framing_count=data.get("unique_framing_count", 0),
            concerns=data.get("concerns", []),
        )
