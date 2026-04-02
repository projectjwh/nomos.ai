"""Tests for AI response parsing utilities."""

import pytest

from phd_platform.core.exceptions import AIParsingError
from phd_platform.core.parsing import (
    extract_json_from_text,
    parse_capstone_proposals,
    parse_diagnostic_questions,
    parse_evaluation_result,
    parse_pre_defense_review,
    parse_verdict,
)


class TestExtractJson:
    def test_plain_json_object(self):
        result = extract_json_from_text('{"key": "value"}')
        assert result == '{"key": "value"}'

    def test_plain_json_array(self):
        result = extract_json_from_text('[1, 2, 3]')
        assert result == '[1, 2, 3]'

    def test_json_in_markdown_fence(self):
        text = 'Here is the result:\n```json\n{"score": 0.9}\n```\nDone.'
        result = extract_json_from_text(text)
        assert '"score": 0.9' in result

    def test_json_in_plain_fence(self):
        text = 'Result:\n```\n[{"a": 1}]\n```'
        result = extract_json_from_text(text)
        assert '"a": 1' in result

    def test_json_embedded_in_prose(self):
        text = 'The evaluation yields: {"score": 0.85, "feedback": "good"} as shown above.'
        result = extract_json_from_text(text)
        assert "0.85" in result

    def test_nested_json(self):
        text = '{"outer": {"inner": [1, 2, {"deep": true}]}}'
        result = extract_json_from_text(text)
        assert '"deep": true' in result

    def test_no_json_raises_error(self):
        with pytest.raises(AIParsingError):
            extract_json_from_text("This is just plain text with no JSON.")

    def test_invalid_json_raises_error(self):
        with pytest.raises(AIParsingError):
            extract_json_from_text("Here: {broken json, no quotes}")

    def test_json_with_escaped_strings(self):
        text = '{"text": "He said \\"hello\\" to her"}'
        result = extract_json_from_text(text)
        assert "hello" in result


class TestParseDiagnosticQuestions:
    def test_valid_json_array(self):
        raw = '[{"question": "What is 2+2?", "type": "computation", "difficulty": 1, "objective_index": 0, "correct_answer": "4", "rubric": "Must be 4", "partial_credit_criteria": ""}]'
        questions = parse_diagnostic_questions(raw)
        assert len(questions) == 1
        assert questions[0].question == "What is 2+2?"
        assert questions[0].type == "computation"
        assert questions[0].difficulty == 1

    def test_multiple_questions(self):
        from tests.conftest import SAMPLE_DIAGNOSTIC_QUESTIONS
        questions = parse_diagnostic_questions(SAMPLE_DIAGNOSTIC_QUESTIONS)
        assert len(questions) == 2
        assert "Marshallian" in questions[1].question

    def test_fallback_on_unparseable(self):
        raw = "Here are some questions about economics that test understanding..."
        questions = parse_diagnostic_questions(raw)
        assert len(questions) == 1
        assert questions[0].type == "short_answer"

    def test_single_object_wrapped_in_list(self):
        raw = '{"question": "Explain GDP", "type": "short_answer", "difficulty": 2}'
        questions = parse_diagnostic_questions(raw)
        assert len(questions) == 1


class TestParseEvaluationResult:
    def test_valid_evaluation(self):
        from tests.conftest import SAMPLE_EVALUATION
        result = parse_evaluation_result(SAMPLE_EVALUATION)
        assert result.score == pytest.approx(0.78)
        assert "algebra error" in result.feedback
        assert "algebraic manipulation" in result.weakness_areas

    def test_score_extraction_fallback(self):
        raw = "The student scored 0.65 out of 1.0. They showed good understanding but..."
        result = parse_evaluation_result(raw)
        assert result.score == pytest.approx(0.65)

    def test_default_score_on_garbage(self):
        raw = "This response cannot be evaluated meaningfully."
        result = parse_evaluation_result(raw)
        assert 0.0 <= result.score <= 1.0  # Falls back to 0.5

    def test_zero_score(self):
        raw = '{"score": 0.0, "feedback": "Completely incorrect", "weakness_areas": ["everything"]}'
        result = parse_evaluation_result(raw)
        assert result.score == 0.0
        assert "everything" in result.weakness_areas


class TestParseCapstoneProposals:
    def test_valid_proposals(self):
        from tests.conftest import SAMPLE_PROPOSALS
        proposals = parse_capstone_proposals(SAMPLE_PROPOSALS)
        assert len(proposals) == 2
        assert "Remote Work" in proposals[0].title
        assert "Municipal Bond" in proposals[1].title

    def test_text_fallback(self):
        raw = """Proposal 1: Study the Effect of X on Y
        This proposal examines...

        Proposal 2: Another Study
        This one looks at..."""
        proposals = parse_capstone_proposals(raw)
        assert len(proposals) >= 1

    def test_single_proposal(self):
        raw = '{"title": "My Thesis", "research_question": "Why?", "methodology": "OLS"}'
        proposals = parse_capstone_proposals(raw)
        assert len(proposals) == 1
        assert proposals[0].title == "My Thesis"


class TestParsePreDefenseReview:
    def test_valid_review(self):
        raw = """{
            "dimension_scores": [
                {"dimension": "Clarity", "score": 4, "issues": ["Section 3 unclear"], "suggestions": ["Add transition"]},
                {"dimension": "Methodology", "score": 3, "issues": ["Weak IV"], "suggestions": ["Add first-stage F-stat"]}
            ],
            "overall_assessment": "NEEDS REVISION",
            "predicted_questions": ["What about endogeneity?", "How robust to X?"],
            "summary": "Solid work but methodology needs strengthening"
        }"""
        review = parse_pre_defense_review(raw)
        assert len(review.dimension_scores) == 2
        assert review.overall_assessment == "NEEDS REVISION"
        assert len(review.predicted_questions) == 2
        assert review.dimension_scores[0].score == 4

    def test_text_fallback_with_ready(self):
        raw = "After careful review, the paper is READY for defense. The methodology is sound..."
        review = parse_pre_defense_review(raw)
        assert review.overall_assessment == "READY"

    def test_text_fallback_with_not_ready(self):
        raw = "This paper is NOT READY for defense. Major issues include..."
        review = parse_pre_defense_review(raw)
        assert review.overall_assessment == "NOT READY"


class TestParseVerdict:
    def test_valid_verdict_json(self):
        from tests.conftest import SAMPLE_VERDICT
        result = parse_verdict(SAMPLE_VERDICT)
        assert result.verdict == "Minor Revision"
        assert "robustness" in result.justification
        assert len(result.strengths) == 2
        assert len(result.suggestions) == 2

    def test_text_fallback_accept(self):
        raw = "I recommend Accept. The paper makes a significant contribution..."
        result = parse_verdict(raw)
        assert result.verdict == "Accept"

    def test_text_fallback_reject(self):
        raw = "My verdict is Reject. The fundamental methodology is flawed..."
        result = parse_verdict(raw)
        assert result.verdict == "Reject"

    def test_ambiguous_defaults_to_major_revision(self):
        raw = "The paper needs significant work before it can be considered."
        result = parse_verdict(raw)
        assert result.verdict == "Major Revision"
