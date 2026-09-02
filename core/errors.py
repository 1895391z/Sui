"""Exception types used at the unified orchestration boundary."""


class AdapterExecutionError(RuntimeError):
    """The selected native adapter failed before returning a usable result."""


class HysysConnectionError(RuntimeError):
    """HYSYS could not be started, discovered, or safely managed."""


class ResultValidationError(RuntimeError):
    """A native adapter result could not be normalized into CaseResult."""
