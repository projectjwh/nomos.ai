"""Centralized AI response parsing utilities.

All AI-calling modules should use these functions to extract structured data
from Claude's responses rather than implementing ad-hoc parsing.
"""

from __future__ import annotations

import json
import re

from phd_platform.core.exceptions import AIParsingError
from phd_platform.core.models import (
    CapstoneProposal,
    DiagnosticQuestion,
    EvaluationResult,
    PreDefenseReview,
    ReviewDimensionScore,
    VerdictResult,
)


def extract_json_from_text(text: str) -> str:
    """Extract a JSON object or array from text that may contain markdown fences or prose.

    Tries in order:
    1. Direct JSON parse of the full text
    2. Extract from ```json ... ``` fences
    3. Extract from ``` ... ``` fences
    4. Find the first { or [ and extract to the matching closer
    """
    text = text.strip()

    # 1. Try direct parse
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass

    # 2. Extract from markdown fences
    fence_match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", text)
    if fence_match:
        candidate = fence_match.group(1).strip()
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    # 3. Find first JSON object or array
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start_idx = text.find(start_char)
        if start_idx == -1:
            continue
        depth = 0
        in_string = False
        escape_next = False
        for i in range(start_idx, len(text)):
            c = text[i]
            if escape_next:
                escape_next = False
                continue
            if c == "\\":
                escape_next = True
                continue
            if c == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == start_char:
                depth += 1
            elif c == end_char:
                depth -= 1
                if depth == 0:
                    candidate = text[start_idx : i + 1]
                    try:
                        json.loads(candidate)
                        return candidate
                    except json.JSONDecodeError:
                        break

    raise AIParsingError("Could not extract valid JSON from AI response", raw_response=text)


def parse_diagnostic_questions(raw: str) -> list[DiagnosticQuestion]:
    """Parse AI-generated diagnostic questions into structured objects."""
    try:
        json_str = extract_json_from_text(raw)
        data = json.loads(json_str)
    except AIParsingError:
        # Fallback: create a single question from the raw text
        return [DiagnosticQuestion(
            question=raw[:500],
            type="short_answer",
            difficulty=3,
            correct_answer="See AI-generated rubric",
            rubric="Evaluate based on understanding of core concepts",
        )]

    if isinstance(data, dict):
        data = [data]

    questions = []
    for item in data:
        if isinstance(item, dict):
            questions.append(DiagnosticQuestion(
                question=item.get("question", ""),
                type=item.get("type", "short_answer"),
                difficulty=item.get("difficulty", 3),
                objective_index=item.get("objective_index", 0),
                correct_answer=item.get("correct_answer", ""),
                rubric=item.get("rubric", ""),
                partial_credit_criteria=item.get("partial_credit_criteria", ""),
            ))

    if not questions:
        raise AIParsingError("Parsed JSON contained no valid questions", raw_response=raw)

    return questions


def parse_evaluation_result(raw: str) -> EvaluationResult:
    """Parse AI evaluation of a student response into a structured result."""
    try:
        json_str = extract_json_from_text(raw)
        data = json.loads(json_str)
    except AIParsingError:
        # Fallback: try to extract a numeric score from the text
        score = _extract_numeric_score(raw)
        return EvaluationResult(
            score=score,
            feedback=raw[:1000],
            weakness_areas=[],
        )

    if isinstance(data, list) and len(data) > 0:
        data = data[0]

    return EvaluationResult(
        score=float(data.get("score", 0.0)),
        feedback=data.get("feedback", ""),
        weakness_areas=data.get("weakness_areas", []),
    )


def parse_capstone_proposals(raw: str) -> list[CapstoneProposal]:
    """Parse AI-generated capstone proposals into structured objects."""
    try:
        json_str = extract_json_from_text(raw)
        data = json.loads(json_str)
    except AIParsingError:
        # Fallback: split by numbered sections and create proposals from text
        return _parse_proposals_from_text(raw)

    if isinstance(data, dict):
        data = [data]

    proposals = []
    for item in data:
        if isinstance(item, dict):
            proposals.append(CapstoneProposal(
                title=item.get("title", "Untitled Proposal"),
                research_question=item.get("research_question", ""),
                methodology=item.get("methodology", ""),
                data_sources=item.get("data_sources", ""),
                contribution=item.get("contribution", ""),
                milestones=item.get("milestones", ""),
                risks=item.get("risks", ""),
            ))

    return proposals if proposals else _parse_proposals_from_text(raw)


def parse_pre_defense_review(raw: str) -> PreDefenseReview:
    """Parse AI pre-defense review into a structured review object."""
    try:
        json_str = extract_json_from_text(raw)
        data = json.loads(json_str)
    except AIParsingError:
        # Fallback: extract what we can from text
        assessment = "NEEDS REVISION"
        # Check longer strings first to avoid "NOT READY" matching "READY"
        for keyword in ["NOT READY", "NEEDS REVISION", "READY"]:
            if keyword in raw.upper():
                assessment = keyword
                break
        return PreDefenseReview(
            overall_assessment=assessment,
            summary=raw[:2000],
        )

    dimensions = []
    for dim_data in data.get("dimension_scores", data.get("dimensions", [])):
        if isinstance(dim_data, dict):
            dimensions.append(ReviewDimensionScore(
                dimension=dim_data.get("dimension", dim_data.get("name", "")),
                score=dim_data.get("score", 3),
                issues=dim_data.get("issues", []),
                suggestions=dim_data.get("suggestions", []),
            ))

    return PreDefenseReview(
        dimension_scores=dimensions,
        overall_assessment=data.get("overall_assessment", data.get("assessment", "")),
        predicted_questions=data.get("predicted_questions", data.get("questions", [])),
        summary=data.get("summary", ""),
    )


def parse_verdict(raw: str) -> VerdictResult:
    """Parse a defense reviewer's verdict from AI response."""
    try:
        json_str = extract_json_from_text(raw)
        data = json.loads(json_str)
        return VerdictResult(
            verdict=data.get("verdict", "Major Revision"),
            justification=data.get("justification", ""),
            strengths=data.get("strengths", []),
            weaknesses=data.get("weaknesses", []),
            suggestions=data.get("suggestions", []),
        )
    except AIParsingError:
        pass

    # Fallback: scan text for verdict keywords
    verdict = "Major Revision"
    # Check in specificity order to avoid "Minor Revision" matching "Revision" for "Major Revision"
    for candidate in ["Accept", "Minor Revision", "Major Revision", "Reject"]:
        if candidate.lower() in raw.lower()[:200]:
            verdict = candidate
            break

    return VerdictResult(verdict=verdict, justification=raw)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _extract_numeric_score(text: str) -> float:
    """Try to extract a numeric score (0.0-1.0) from text."""
    # Look for patterns like "Score: 0.85" or "0.7/1.0"
    patterns = [
        r"[Ss]core[:\s]+([01]\.?\d*)",
        r"(\d\.\d+)\s*/\s*1\.0",
        r"(\d\.\d+)\s+out of\s+1",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            score = float(match.group(1))
            if 0.0 <= score <= 1.0:
                return score
    return 0.5  # Default to middle if we can't parse


def _parse_proposals_from_text(raw: str) -> list[CapstoneProposal]:
    """Fallback: split raw text into proposals by numbered headings."""
    sections = re.split(r"\n(?=(?:Proposal\s+\d|#{1,3}\s+Proposal\s+\d|\d+\.))", raw)
    proposals = []
    for section in sections:
        section = section.strip()
        if not section:
            continue
        # Try to extract title from first line
        lines = section.split("\n")
        title = lines[0].strip().lstrip("#").strip().lstrip("0123456789.").strip()
        if not title or len(title) > 200:
            title = "Untitled Proposal"
        proposals.append(CapstoneProposal(
            title=title,
            research_question=section[:2000],
        ))

    return proposals[:3] if proposals else [CapstoneProposal(
        title="Generated Proposal",
        research_question=raw[:2000],
    )]
