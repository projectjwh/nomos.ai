"""Process telemetry — passive integrity monitoring for all student interactions."""

from __future__ import annotations

import time
from typing import Callable

from phd_platform.config import get_settings
from phd_platform.core.enums import IntegrityFlag
from phd_platform.core.models import IntegrityEvent


class ResponseCapture:
    """Wraps student response functions to capture integrity telemetry.

    Records timing, character count, and detects paste-like patterns
    (high char_count with low elapsed time).
    """

    # Characters per second thresholds
    TYPING_SPEED_MAX = 12  # ~12 chars/sec is fast but human
    PASTE_SPEED_THRESHOLD = 50  # >50 chars/sec is almost certainly paste

    def __init__(self, session_type: str, module_id: str = ""):
        self.session_type = session_type
        self.module_id = module_id
        self.events: list[IntegrityEvent] = []
        self._question_shown_at: float | None = None

    def mark_question_shown(self) -> None:
        """Call when a question is displayed to the student."""
        self._question_shown_at = time.time()
        self.events.append(IntegrityEvent(
            event_type="response_started",
            session_type=self.session_type,
            module_id=self.module_id,
        ))

    def capture_response(self, response_text: str) -> IntegrityEvent:
        """Record telemetry for a submitted response. Returns the event with flags."""
        now = time.time()
        elapsed_ms = int((now - self._question_shown_at) * 1000) if self._question_shown_at else 0
        char_count = len(response_text)
        elapsed_sec = elapsed_ms / 1000.0

        # Detect paste patterns
        chars_per_sec = char_count / max(elapsed_sec, 0.1)
        flagged = False
        flag_reason = ""

        if chars_per_sec > self.PASTE_SPEED_THRESHOLD and char_count > 100:
            flagged = True
            flag_reason = f"Paste pattern: {chars_per_sec:.0f} chars/sec ({char_count} chars in {elapsed_sec:.1f}s)"

        event = IntegrityEvent(
            event_type="response_submitted",
            session_type=self.session_type,
            module_id=self.module_id,
            elapsed_ms=elapsed_ms,
            char_count=char_count,
            flagged=flagged,
            flag_reason=flag_reason,
            metadata={
                "chars_per_sec": round(chars_per_sec, 1),
                "paste_detected": flagged,
            },
        )
        self.events.append(event)
        self._question_shown_at = None  # Reset for next question
        return event

    def wrap_respond_fn(self, respond_fn: Callable) -> Callable:
        """Wrap an async student response function with telemetry capture.

        Usage in defense/session.py:
            capture = ResponseCapture("defense", module_id)
            wrapped_fn = capture.wrap_respond_fn(student_respond_fn)
            await session.run_qa(paper_text, wrapped_fn)
        """
        async def wrapped(question: str) -> str:
            self.mark_question_shown()
            response = await respond_fn(question)
            self.capture_response(response)
            return response
        return wrapped

    def get_flags(self) -> list[IntegrityEvent]:
        """Return all flagged events."""
        return [e for e in self.events if e.flagged]

    @property
    def flag_count(self) -> int:
        return sum(1 for e in self.events if e.flagged)

    @property
    def total_events(self) -> int:
        return len(self.events)
