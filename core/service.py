"""Application service connecting a validated CaseSpec to its adapter."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Callable, Mapping

from .errors import AdapterExecutionError, ResultValidationError
from .models import CaseResult, CaseSpec, ComparisonPlan, ComparisonResult, Scenario
from .normalizers import normalize_comparison_result, normalize_result
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


def execute_comparison_plan(
    plan: ComparisonPlan,
    *,
    session_factory: Callable[[], AbstractContextManager[object]],
    case_executor: Callable[[CaseSpec], CaseResult] | None = None,
) -> ComparisonResult:
    """Execute each planned case in its own sequential HYSYS session."""

    executor = execute_case if case_executor is None else case_executor
    results: list[CaseResult] = []
    total = len(plan.case_specs)
    for index, spec in enumerate(plan.case_specs, start=1):
        value = getattr(spec.inputs, plan.comparison_field)
        print(
            f"COMPARISON_CASE_START: index={index}/{total} "
            f"{plan.comparison_field}={value}"
        )
        try:
            with session_factory():
                result = executor(spec)
        except Exception:
            print(
                f"COMPARISON_CASE_FAILED: index={index}/{total} "
                f"{plan.comparison_field}={value}"
            )
            raise
        results.append(result)
        print(
            f"COMPARISON_CASE_OK: index={index}/{total} "
            f"{plan.comparison_field}={value}"
        )

    try:
        return normalize_comparison_result(plan, tuple(results))
    except Exception as exc:
        raise ResultValidationError(
            f"{plan.scenario.value} comparison validation failed: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
