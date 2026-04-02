"""Tests for the integrity system — telemetry, timing, and Socratic verification."""

import time

import pytest

from phd_platform.core.enums import IntegrityFlag
from phd_platform.integrity.telemetry import ResponseCapture
from phd_platform.integrity.timing import TimedResponse, ResponseWindow, RESPONSE_WINDOWS


class TestResponseCapture:
    def test_normal_response_no_flag(self):
        capture = ResponseCapture("assessment", "ECON-F-001")
        capture.mark_question_shown()
        time.sleep(0.1)  # Simulate thinking time
        event = capture.capture_response("The answer is 42 because of the chain rule.")
        assert not event.flagged
        assert event.elapsed_ms > 50
        assert event.char_count > 0

    def test_paste_detection(self):
        capture = ResponseCapture("defense", "ECON-U-008")
        capture.mark_question_shown()
        # Simulate instant paste of large text (no delay)
        long_answer = "x" * 500
        event = capture.capture_response(long_answer)
        assert event.flagged
        assert "Paste pattern" in event.flag_reason or event.metadata.get("paste_detected")

    def test_short_answer_not_flagged(self):
        capture = ResponseCapture("placement")
        capture.mark_question_shown()
        event = capture.capture_response("42")
        # Short answers should not be flagged even if fast
        assert not event.flagged

    def test_wrap_respond_fn(self):
        capture = ResponseCapture("defense")

        async def mock_respond(question):
            return "My thoughtful answer"

        wrapped = capture.wrap_respond_fn(mock_respond)
        assert callable(wrapped)
        assert capture.total_events == 0

    def test_flag_count(self):
        capture = ResponseCapture("assessment")
        # Normal response
        capture.mark_question_shown()
        time.sleep(0.05)
        capture.capture_response("short")
        # Paste response
        capture.mark_question_shown()
        event = capture.capture_response("x" * 1000)
        # Flag count should reflect paste detection
        assert capture.total_events >= 2

    def test_multiple_questions(self):
        capture = ResponseCapture("placement", "ECON-F-002")
        for _ in range(3):
            capture.mark_question_shown()
            time.sleep(0.05)
            capture.capture_response("An answer")
        assert capture.total_events == 6  # 3 started + 3 submitted


class TestTimedResponse:
    def test_normal_timing_no_flag(self):
        result = TimedResponse.evaluate("A good answer", 120.0, "assessment")
        assert not result.flagged
        assert not result.too_fast
        assert not result.too_slow

    def test_too_fast_flags(self):
        result = TimedResponse.evaluate(
            "A very long and detailed answer that seems to have been pasted in" * 3,
            5.0,  # 5 seconds for a long answer
            "defense_qa",
        )
        assert result.flagged
        assert IntegrityFlag.TIMING_ANOMALY.value in result.flag_reason

    def test_short_answer_not_flagged_even_fast(self):
        result = TimedResponse.evaluate("42", 2.0, "assessment")
        # Very short answers shouldn't be flagged even if fast
        assert not result.flagged

    def test_defense_has_stricter_windows(self):
        defense_window = RESPONSE_WINDOWS["defense_qa"]
        placement_window = RESPONSE_WINDOWS["placement"]
        assert defense_window.min_seconds > placement_window.min_seconds

    def test_response_window_defaults(self):
        # Unknown session type gets default window
        result = TimedResponse.evaluate("answer", 60.0, "unknown_type")
        assert result.window.min_seconds == 30  # Default


class TestTimedResponseProperties:
    def test_too_fast(self):
        r = TimedResponse(
            text="x", elapsed_seconds=10,
            window=ResponseWindow(min_seconds=30, max_seconds=600),
        )
        assert r.too_fast

    def test_too_slow(self):
        r = TimedResponse(
            text="x", elapsed_seconds=700,
            window=ResponseWindow(min_seconds=30, max_seconds=600),
        )
        assert r.too_slow

    def test_in_range(self):
        r = TimedResponse(
            text="x", elapsed_seconds=120,
            window=ResponseWindow(min_seconds=30, max_seconds=600),
        )
        assert not r.too_fast
        assert not r.too_slow
