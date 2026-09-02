"""Application service connecting a validated CaseSpec to its adapter."""

from __future__ import annotations

from typing import Mapping

from .errors import AdapterExecutionError, ResultValidationError
from .models import CaseResult, CaseSpec, Scenario
from .normalizers import normalize_result
from .registry import NativeRunner, dispatch_native


def execute_case(
    spec: CaseSpec,
    runners: Mapping[Scenario, NativeRunner] | None = None,
) -> CaseResult:
    try:
        raw_result = dispatch_native(spec, runners=runners)
    except FileNotFoundError:
        raise
    except Exception as exc:
        raise AdapterExecutionError(
            f"{spec.scenario.value} adapter failed: {type(exc).__name__}: {exc}"
        ) from exc

    try:
        return normalize_result(spec, raw_result)
    except Exception as exc:
        raise ResultValidationError(
            f"{spec.scenario.value} result validation failed: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
