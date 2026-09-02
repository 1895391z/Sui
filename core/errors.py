"""Exception types used at the unified orchestration boundary."""


class AdapterExecutionError(RuntimeError):
    """The selected native adapter failed before returning a usable result."""


class ResultValidationError(RuntimeError):
    """A native adapter result could not be normalized into CaseResult."""
