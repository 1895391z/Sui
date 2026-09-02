"""Convert scenario-specific adapter dictionaries into one CaseResult schema."""

from __future__ import annotations

import math
from dataclasses import asdict
from typing import Any, Callable

from .models import (
    BalanceResult,
    CaseResult,
    CaseSpec,
    EngineeringValidationStatus,
    ReactorResult,
    Scenario,
)


def _dict(raw: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key)
    if not isinstance(value, dict):
        raise RuntimeError(f"Adapter result {key!r} must be a dictionary")
    return value


def _text(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"Adapter result {key!r} must be a non-empty string")
    return value


def _number(raw: dict[str, Any], key: str) -> float:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeError(f"Adapter result {key!r} must be numeric; actual={value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise RuntimeError(f"Adapter result {key!r} must be finite; actual={value!r}")
    return number


def _strings(raw: dict[str, Any], key: str) -> list[str]:
    value = raw.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise RuntimeError(f"Adapter result {key!r} must be a list of strings")
    return list(value)


def _common(
    spec: CaseSpec,
    raw: dict[str, Any],
) -> tuple[ReactorResult, dict[str, Any], dict[str, Any], dict[str, Any]]:
    if raw.get("converged") is not True:
        raise RuntimeError("Adapter result does not report converged=True")
    reactor = ReactorResult(
        type=_text(raw, "reactor_type"),
        name=_text(raw, "reactor_name"),
        selection_reason=_text(raw, "selection_reason"),
    )
    conditions = asdict(spec.inputs)
    native_conditions = raw.get("conditions", {})
    if not isinstance(native_conditions, dict):
        raise RuntimeError("Adapter result 'conditions' must be a dictionary when present")
    conditions.update(native_conditions)

    products = _dict(raw, "products")
    product_streams = products.get("streams")
    if not isinstance(product_streams, dict):
        raise RuntimeError("Adapter result products.streams must be a dictionary")
    streams = {"feed": _dict(raw, "feed"), "products": dict(product_streams)}
    aggregates = {key: value for key, value in products.items() if key != "streams"}
    return reactor, conditions, streams, aggregates


def _balance(raw: dict[str, Any]) -> BalanceResult:
    element_errors = raw.get("element_balance_error_percent", {})
    if not isinstance(element_errors, dict):
        raise RuntimeError("element_balance_error_percent must be a dictionary")
    normalized_elements = {
        str(element): float(error) for element, error in element_errors.items()
    }
    if not all(math.isfinite(error) for error in normalized_elements.values()):
        raise RuntimeError("Element-balance errors must be finite")
    return BalanceResult(
        mass_error_percent=_number(raw, "mass_balance_error_percent"),
        element_error_percent=normalized_elements,
    )


def normalize_toluene(spec: CaseSpec, raw: dict[str, Any]) -> CaseResult:
    reactor, conditions, streams, aggregates = _common(spec, raw)
    return CaseResult(
        scenario=Scenario.TOLUENE,
        reactor=reactor,
        conditions=conditions,
        metrics={
            "conversion_fraction": _number(raw, "conversion_fraction"),
            "conversion_percent": _number(raw, "conversion_percent"),
        },
        streams=streams,
        aggregates=aggregates,
        balances=_balance(raw),
        solver_converged=True,
        engineering_validation_status=EngineeringValidationStatus.NOT_ASSESSED,
        assumptions=_strings(raw, "assumptions"),
        warnings=_strings(raw, "warnings"),
    )


def normalize_methane(spec: CaseSpec, raw: dict[str, Any]) -> CaseResult:
    reactor, conditions, streams, aggregates = _common(spec, raw)
    return CaseResult(
        scenario=Scenario.METHANE,
        reactor=reactor,
        conditions=conditions,
        metrics={
            "methane_conversion_percent": _number(
                raw, "methane_conversion_percent"
            ),
            "heat_duty_kw": _number(raw, "heat_duty_kw"),
        },
        streams=streams,
        aggregates=aggregates,
        balances=_balance(raw),
        solver_converged=True,
        engineering_validation_status=EngineeringValidationStatus.NOT_ASSESSED,
        assumptions=_strings(raw, "assumptions"),
        warnings=_strings(raw, "warnings"),
    )


def normalize_coal(spec: CaseSpec, raw: dict[str, Any]) -> CaseResult:
    reactor, conditions, streams, aggregates = _common(spec, raw)
    thermodynamic_validity = _dict(raw, "thermodynamic_validity")
    aggregates["thermodynamic_validity"] = thermodynamic_validity
    return CaseResult(
        scenario=Scenario.COAL,
        reactor=reactor,
        conditions=conditions,
        metrics={
            "co_yield_percent": _number(raw, "co_yield_percent"),
            "carbon_conversion_percent": _number(raw, "carbon_conversion_percent"),
            "syngas_hydrogen_molar_fraction": _number(
                raw, "syngas_hydrogen_molar_fraction"
            ),
            "heat_duty_kw": _number(raw, "heat_duty_kw"),
        },
        streams=streams,
        aggregates=aggregates,
        balances=_balance(raw),
        solver_converged=True,
        engineering_validation_status=EngineeringValidationStatus.LIMITED,
        assumptions=_strings(raw, "assumptions"),
        warnings=_strings(raw, "warnings"),
    )


Normalizer = Callable[[CaseSpec, dict[str, Any]], CaseResult]

NORMALIZERS: dict[Scenario, Normalizer] = {
    Scenario.TOLUENE: normalize_toluene,
    Scenario.METHANE: normalize_methane,
    Scenario.COAL: normalize_coal,
}


def normalize_result(spec: CaseSpec, raw: dict[str, Any]) -> CaseResult:
    try:
        normalizer = NORMALIZERS[spec.scenario]
    except KeyError as exc:
        raise ValueError(
            f"No result normalizer for scenario {spec.scenario.value!r}"
        ) from exc
    return normalizer(spec, raw)
