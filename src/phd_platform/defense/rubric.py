"""Evaluation rubrics for defense sessions — scoring criteria per discipline and level."""

from __future__ import annotations

from phd_platform.core.enums import Discipline, Level


# Rubric dimensions and their descriptions
RUBRIC_DIMENSIONS = {
    "methodology": {
        "name": "Methodology & Rigor",
        "description": "Technical soundness, appropriate methods, correct implementation",
        "levels": {
            5: "Flawless methodology; novel or state-of-the-art approach applied correctly",
            4: "Sound methodology with minor gaps; demonstrates strong technical command",
            3: "Adequate methodology; some questionable choices but core approach is valid",
            2: "Weak methodology; significant issues with identification, proofs, or experiments",
            1: "Fundamentally flawed approach; incorrect methods or invalid assumptions",
        },
    },
    "novelty": {
        "name": "Novelty & Originality",
        "description": "Contribution beyond existing literature; new insights, data, or methods",
        "levels": {
            5: "Highly original; opens a new research direction or solves an open problem",
            4: "Clear novelty; meaningfully extends the frontier of knowledge",
            3: "Moderate novelty; useful contribution but incremental",
            2: "Limited novelty; largely replicates existing work with minor variations",
            1: "No novelty; purely replicative or already known results",
        },
    },
    "significance": {
        "name": "Significance & Impact",
        "description": "Importance of the question; potential impact on the field or practice",
        "levels": {
            5: "Addresses a first-order question; findings reshape understanding of the field",
            4: "Important question; results will be widely cited and applied",
            3: "Relevant question; useful findings for a subfield",
            2: "Minor question; limited audience or applicability",
            1: "Trivial question; no clear reason anyone should care",
        },
    },
    "exposition": {
        "name": "Exposition & Clarity",
        "description": "Writing quality, organization, figures, accessibility",
        "levels": {
            5: "Exceptionally clear; a pleasure to read; perfect figures and notation",
            4: "Well-written; minor issues; good structure and flow",
            3: "Adequate writing; some confusing sections; could be reorganized",
            2: "Poor writing; unclear arguments; disorganized presentation",
            1: "Incomprehensible; major language or structural issues throughout",
        },
    },
}

# Default rubric weights by discipline (can be overridden by persona config)
DISCIPLINE_WEIGHTS: dict[Discipline, dict[str, float]] = {
    Discipline.ECONOMICS: {
        "methodology": 0.30,
        "novelty": 0.25,
        "significance": 0.25,
        "exposition": 0.20,
    },
    Discipline.DATA_SCIENCE: {
        "methodology": 0.30,
        "novelty": 0.25,
        "significance": 0.25,
        "exposition": 0.20,
    },
    Discipline.COMPUTER_SCIENCE: {
        "methodology": 0.30,
        "novelty": 0.30,
        "significance": 0.20,
        "exposition": 0.20,
    },
    Discipline.AI_ML: {
        "methodology": 0.30,
        "novelty": 0.30,
        "significance": 0.20,
        "exposition": 0.20,
    },
    Discipline.FINANCIAL_ENGINEERING: {
        "methodology": 0.35,
        "novelty": 0.25,
        "significance": 0.20,
        "exposition": 0.20,
    },
}

# Level-specific scoring thresholds for verdicts
VERDICT_THRESHOLDS: dict[Level, dict[str, float]] = {
    Level.UNDERGRADUATE: {
        "accept": 4.0,         # Average score >= 4.0 → Accept
        "minor_revision": 3.5, # >= 3.5 → Minor Revision
        "major_revision": 2.5, # >= 2.5 → Major Revision
        # Below 2.5 → Reject
    },
    Level.MASTERS: {
        "accept": 4.2,
        "minor_revision": 3.7,
        "major_revision": 3.0,
    },
    Level.DOCTORAL: {
        "accept": 4.5,
        "minor_revision": 4.0,
        "major_revision": 3.5,
    },
}


def compute_weighted_score(
    dimension_scores: dict[str, int],
    discipline: Discipline,
    persona_weights: dict[str, float] | None = None,
) -> float:
    """Compute a weighted average score from dimension scores.

    Args:
        dimension_scores: Scores (1-5) for each rubric dimension.
        discipline: The discipline (determines default weights).
        persona_weights: Optional override weights from the reviewer persona.

    Returns:
        Weighted average score (1.0 - 5.0).
    """
    weights = persona_weights or DISCIPLINE_WEIGHTS.get(discipline, {})
    total_weight = sum(weights.values())
    if total_weight == 0:
        return 0.0

    weighted_sum = sum(
        dimension_scores.get(dim, 3) * weights.get(dim, 0.25)
        for dim in RUBRIC_DIMENSIONS
    )
    return weighted_sum / total_weight


def score_to_verdict(score: float, level: Level) -> str:
    """Convert a weighted score to a verdict string."""
    thresholds = VERDICT_THRESHOLDS.get(level, VERDICT_THRESHOLDS[Level.MASTERS])
    if score >= thresholds["accept"]:
        return "Accept"
    elif score >= thresholds["minor_revision"]:
        return "Minor Revision"
    elif score >= thresholds["major_revision"]:
        return "Major Revision"
    else:
        return "Reject"
