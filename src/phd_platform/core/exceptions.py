"""Custom exceptions for the PhD Platform."""


class AIParsingError(Exception):
    """Raised when an AI response cannot be parsed into the expected structure."""

    def __init__(self, message: str, raw_response: str = ""):
        super().__init__(message)
        self.raw_response = raw_response


class ModuleNotFoundError(Exception):
    """Raised when a module ID does not exist in the curriculum."""


class PrerequisiteNotMetError(Exception):
    """Raised when a student attempts a module without meeting prerequisites."""

    def __init__(self, module_id: str, missing_prereqs: list[str]):
        self.module_id = module_id
        self.missing_prereqs = missing_prereqs
        super().__init__(
            f"Module {module_id} requires: {', '.join(missing_prereqs)}"
        )


class GateNotReadyError(Exception):
    """Raised when a student attempts a gate assessment before meeting requirements."""

    def __init__(self, level: str, blocking_modules: list[str]):
        self.level = level
        self.blocking_modules = blocking_modules
        super().__init__(
            f"Cannot attempt {level} gate. Blocking modules: {', '.join(blocking_modules)}"
        )
