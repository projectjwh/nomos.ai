"""Local grader — evaluates deterministic answer types without LLM calls.

Tier 1 cost optimization: MCQ, computation, and keyword-match questions
can be graded locally against pre-stored rubrics from the question bank.
"""

from __future__ import annotations

import re

from phd_platform.core.models import EvaluationResult


class LocalGrader:
    """Grades answers against pre-generated rubrics without LLM calls.

    Supported question types:
    - mcq: Exact match against correct_answer (case-insensitive, stripped)
    - computation: Numeric comparison with configurable tolerance
    - short_answer: Keyword matching against rubric terms

    For proof/essay questions, returns None (caller falls through to LLM).
    """

    NUMERIC_TOLERANCE = 0.01  # Default relative tolerance for computations

    def grade(
        self,
        question_type: str,
        student_answer: str,
        correct_answer: str,
        rubric: str = "",
    ) -> EvaluationResult | None:
        """Grade a student answer locally. Returns None if LLM is needed."""
        student_answer = student_answer.strip()
        correct_answer = correct_answer.strip()

        if question_type == "mcq":
            return self._grade_mcq(student_answer, correct_answer)
        elif question_type == "computation":
            return self._grade_computation(student_answer, correct_answer, rubric)
        elif question_type == "short_answer":
            return self._grade_short_answer(student_answer, correct_answer, rubric)
        else:
            return None  # proof, essay → needs LLM

    def _grade_mcq(self, student: str, correct: str) -> EvaluationResult:
        """Grade multiple choice: exact match (case-insensitive)."""
        # Handle formats like "A", "a)", "(A)", "Option A", etc.
        student_clean = re.sub(r"[^a-zA-Z0-9]", "", student).upper()
        correct_clean = re.sub(r"[^a-zA-Z0-9]", "", correct).upper()

        if student_clean == correct_clean:
            return EvaluationResult(score=1.0, feedback="Correct!")
        return EvaluationResult(
            score=0.0,
            feedback=f"Incorrect. The correct answer is: {correct}",
        )

    def _grade_computation(
        self, student: str, correct: str, rubric: str
    ) -> EvaluationResult:
        """Grade computation: extract numeric values and compare with tolerance."""
        student_nums = self._extract_numbers(student)
        correct_nums = self._extract_numbers(correct)

        if not correct_nums:
            return None  # Can't grade without a numeric answer

        if not student_nums:
            return EvaluationResult(
                score=0.0,
                feedback="No numeric answer found in your response.",
                weakness_areas=["computation"],
            )

        # Compare the last number in each (typically the final answer)
        student_val = student_nums[-1]
        correct_val = correct_nums[-1]

        if correct_val == 0:
            match = abs(student_val) < self.NUMERIC_TOLERANCE
        else:
            match = abs(student_val - correct_val) / abs(correct_val) < self.NUMERIC_TOLERANCE

        if match:
            return EvaluationResult(score=1.0, feedback="Correct computation!")

        # Check if any extracted number matches (partial credit for intermediate steps)
        for s_num in student_nums:
            for c_num in correct_nums:
                if c_num != 0 and abs(s_num - c_num) / abs(c_num) < self.NUMERIC_TOLERANCE:
                    return EvaluationResult(
                        score=0.5,
                        feedback=f"Partial credit: found correct intermediate value {s_num}, but final answer should be {correct_val}.",
                        weakness_areas=["algebraic manipulation"],
                    )

        return EvaluationResult(
            score=0.0,
            feedback=f"Incorrect. Expected {correct_val}, got {student_val}.",
            weakness_areas=["computation"],
        )

    def _grade_short_answer(
        self, student: str, correct: str, rubric: str
    ) -> EvaluationResult:
        """Grade short answer: keyword matching against rubric and correct answer."""
        # Extract key terms from correct answer and rubric
        key_terms = self._extract_key_terms(correct + " " + rubric)
        if not key_terms:
            return None  # Not enough rubric info for local grading

        student_lower = student.lower()
        matched = [t for t in key_terms if t.lower() in student_lower]
        coverage = len(matched) / len(key_terms) if key_terms else 0.0

        if coverage >= 0.8:
            return EvaluationResult(
                score=min(coverage, 1.0),
                feedback=f"Good coverage of key concepts ({len(matched)}/{len(key_terms)} terms).",
            )
        elif coverage >= 0.5:
            missing = [t for t in key_terms if t.lower() not in student_lower]
            return EvaluationResult(
                score=coverage * 0.8,  # Discount partial coverage
                feedback=f"Partial: covered {len(matched)}/{len(key_terms)} key terms.",
                weakness_areas=[f"missing: {', '.join(missing[:3])}"],
            )
        else:
            return EvaluationResult(
                score=coverage * 0.5,
                feedback=f"Incomplete: only {len(matched)}/{len(key_terms)} key concepts addressed.",
                weakness_areas=["comprehension"],
            )

    @staticmethod
    def _extract_numbers(text: str) -> list[float]:
        """Extract all numeric values from text."""
        # Match integers, decimals, negative numbers, and scientific notation
        pattern = r"-?\d+\.?\d*(?:[eE][+-]?\d+)?"
        matches = re.findall(pattern, text)
        return [float(m) for m in matches]

    @staticmethod
    def _extract_key_terms(text: str) -> list[str]:
        """Extract significant terms from rubric/answer text (>4 chars, not common words)."""
        stop_words = {
            "the", "and", "for", "are", "but", "not", "you", "all", "can",
            "her", "was", "one", "our", "out", "has", "have", "been", "from",
            "that", "this", "with", "they", "will", "each", "make", "like",
            "must", "should", "about", "would", "their", "which", "there",
            "could", "other", "than", "then", "when", "what", "some",
        }
        words = re.findall(r"\b[a-zA-Z]{4,}\b", text.lower())
        seen = set()
        terms = []
        for w in words:
            if w not in stop_words and w not in seen:
                seen.add(w)
                terms.append(w)
        return terms[:15]  # Cap at 15 key terms
