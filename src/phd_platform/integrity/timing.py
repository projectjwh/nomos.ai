"""Timed response enforcement — configurable windows per session type."""

from __future__ import annotations

from dataclasses import dataclass

from phd_platform.config import get_settings
from phd_platform.core.enums import IntegrityFlag


@dataclass
class ResponseWindow:
    """Time window for a response (in seconds)."""
    min_seconds: int
    max_seconds: int


# Default windows by session type
RESPONSE_WINDOWS: dict[str, ResponseWindow] = {
    "placement": ResponseWindow(min_seconds=30, max_seconds=600),
    "assessment": ResponseWindow(min_seconds=45, max_seconds=900),
    "defense_qa": ResponseWindow(min_seconds=60, max_seconds=300),
}


@dataclass
class TimedResponse:
    """A response annotated with timing data and integrity flags."""
    text: str
    elapsed_seconds: float
    window: ResponseWindow
    flagged: bool = False
    flag_reason: str = ""

    @property
    def too_fast(self) -> bool:
        return self.elapsed_seconds < self.window.min_seconds

    @property
    def too_slow(self) -> bool:
        return self.elapsed_seconds > self.window.max_seconds

    @classmethod
    def evaluate(
        cls, text: str, elapsed_seconds: float, session_type: str
    ) -> "TimedResponse":
        """Create a TimedResponse with automatic flag evaluation."""
        window = RESPONSE_WINDOWS.get(session_type, ResponseWindow(30, 600))
        settings = get_settings()

        flagged = False
        flag_reason = ""

        # Check minimum time (suspiciously fast)
        min_ratio = elapsed_seconds / window.max_seconds
        if min_ratio < settings.integrity_timing_min_ratio and len(text) > 50:
            flagged = True
            flag_reason = (
                f"{IntegrityFlag.TIMING_ANOMALY.value}: "
                f"Response in {elapsed_seconds:.0f}s "
                f"(min ratio {min_ratio:.2f} < {settings.integrity_timing_min_ratio})"
            )

        # Check if under absolute minimum
        if elapsed_seconds < window.min_seconds and len(text) > 20:
            flagged = True
            flag_reason = (
                f"{IntegrityFlag.TIMING_ANOMALY.value}: "
                f"Response in {elapsed_seconds:.0f}s < {window.min_seconds}s minimum"
            )

        return cls(
            text=text,
            elapsed_seconds=elapsed_seconds,
            window=window,
            flagged=flagged,
            flag_reason=flag_reason,
        )


def format_time_remaining(seconds: int) -> str:
    """Format seconds as MM:SS for display."""
    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes}:{secs:02d}"
