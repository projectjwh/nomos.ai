from enum import Enum


class Discipline(str, Enum):
    ECONOMICS = "economics"
    DATA_SCIENCE = "data_science"
    COMPUTER_SCIENCE = "computer_science"
    AI_ML = "ai_ml"
    FINANCIAL_ENGINEERING = "financial_engineering"


class Level(str, Enum):
    FOUNDATION = "foundation"
    UNDERGRADUATE = "undergraduate"
    MASTERS = "masters"
    DOCTORAL = "doctoral"

    @property
    def next(self) -> "Level | None":
        order = list(Level)
        idx = order.index(self)
        return order[idx + 1] if idx < len(order) - 1 else None

    @property
    def mastery_threshold(self) -> float:
        """Minimum mastery score to advance past this level's gate."""
        return {
            Level.FOUNDATION: 0.90,
            Level.UNDERGRADUATE: 0.95,
            Level.MASTERS: 0.95,
            Level.DOCTORAL: 0.95,  # mastery check + defense required
        }[self]

    @property
    def defense_panel_size(self) -> int:
        return {
            Level.FOUNDATION: 0,
            Level.UNDERGRADUATE: 2,
            Level.MASTERS: 3,
            Level.DOCTORAL: 5,
        }[self]


class Verdict(str, Enum):
    ACCEPT = "Accept"
    MINOR_REVISION = "Minor Revision"
    MAJOR_REVISION = "Major Revision"
    REJECT = "Reject"

    @property
    def is_passing(self) -> bool:
        return self in (Verdict.ACCEPT, Verdict.MINOR_REVISION)

    @property
    def allows_resubmission(self) -> bool:
        return self == Verdict.MAJOR_REVISION


class GateStatus(str, Enum):
    LOCKED = "locked"
    IN_PROGRESS = "in_progress"
    READY_FOR_ASSESSMENT = "ready_for_assessment"
    PASSED = "passed"
    FAILED_RETAKEABLE = "failed_retakeable"


class IntegrityFlag(str, Enum):
    TIMING_ANOMALY = "timing_anomaly"
    PASTE_DETECTED = "paste_detected"
    CONCEPT_MISMATCH = "concept_mismatch"
    SURFACE_ONLY = "surface_only"
    ESCALATED = "escalated"


class SocraticDepth(str, Enum):
    SURFACE = "surface"           # Can restate but not explain
    PROCEDURAL = "procedural"     # Can explain the steps/mechanism
    CONCEPTUAL = "conceptual"     # Can apply to new contexts
    TRANSFERABLE = "transferable" # Can teach it and connect to other domains
