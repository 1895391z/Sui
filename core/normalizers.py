"""Convert scenario-specific adapter dictionaries into one CaseResult schema."""

from __future__ import annotations

import math
from dataclasses import asdict
from typing import Any, Callable

from .models import (
    BalanceResult,
    CaseResult,
    CaseSpec,
    ComparisonPlan,
    ComparisonResult,
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


def _finite_result_mapping(value: Any, label: str) -> dict[str, float]:
    if not isinstance(value, dict) or not value:
        raise RuntimeError(f"{label} must be a non-empty dictionary")
    result: dict[str, float] = {}
    for key, raw_number in value.items():
        if isinstance(raw_number, bool) or not isinstance(raw_number, (int, float)):
            raise RuntimeError(f"{label}.{key} must be numeric")
        number = float(raw_number)
        if not math.isfinite(number) or number < -1e-8:
            raise RuntimeError(f"{label}.{key} must be finite and non-negative")
        result[str(key)] = max(number, 0.0)
    return result


def _methane_case_summary(index: int, result: CaseResult) -> dict[str, Any]:
    component_flows = _finite_result_mapping(
        result.aggregates.get("combined_component_molar_flow_kgmole_h"),
        "combined_component_molar_flow_kgmole_h",
    )
    total_flow = sum(component_flows.values())
    if total_flow <= 0.0:
        raise RuntimeError("Combined product molar flow must be greater than zero")
    component_fractions = {
        component: flow / total_flow for component, flow in component_flows.items()
    }
    temperature = result.conditions.get("outlet_temperature_c")
    conversion = result.metrics.get("methane_conversion_percent")
    duty = result.metrics.get("heat_duty_kw")
    for label, value in (
        ("outlet_temperature_c", temperature),
        ("methane_conversion_percent", conversion),
        ("heat_duty_kw", duty),
    ):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise RuntimeError(f"Comparison result {label} must be numeric")
        if not math.isfinite(float(value)):
            raise RuntimeError(f"Comparison result {label} must be finite")
    return {
        "case_index": index,
        "outlet_temperature_c": float(temperature),
        "methane_conversion_percent": float(conversion),
        "heat_duty_kw": float(duty),
        "product_component_molar_flow_kgmole_h": component_flows,
        "product_component_molar_fraction": component_fractions,
        "mass_balance_error_percent": result.balances.mass_error_percent,
        "element_balance_error_percent": dict(result.balances.element_error_percent),
    }


def normalize_comparison_result(
    plan: ComparisonPlan,
    case_results: tuple[CaseResult, ...],
) -> ComparisonResult:
    if len(case_results) != len(plan.case_specs):
        raise RuntimeError("Comparison results do not match the planned case count")
    summaries = tuple(
        _methane_case_summary(index, result)
        for index, result in enumerate(case_results)
    )
    for spec, summary in zip(plan.case_specs, summaries, strict=True):
        planned = float(getattr(spec.inputs, plan.comparison_field))
        if not math.isclose(
            summary["outlet_temperature_c"], planned, rel_tol=0.0, abs_tol=0.05
        ):
            raise RuntimeError(
                "Comparison result temperature does not match the planned CaseSpec"
            )

    adjacent_deltas: list[dict[str, Any]] = []
    for current, following in zip(summaries, summaries[1:], strict=False):
        current_fractions = current["product_component_molar_fraction"]
        following_fractions = following["product_component_molar_fraction"]
        if set(current_fractions) != set(following_fractions):
            raise RuntimeError("Comparison product component sets do not match")
        current_flows = current["product_component_molar_flow_kgmole_h"]
        following_flows = following["product_component_molar_flow_kgmole_h"]
        adjacent_deltas.append(
            {
                "from_case_index": current["case_index"],
                "to_case_index": following["case_index"],
                "from_comparison_value": current["outlet_temperature_c"],
                "to_comparison_value": following["outlet_temperature_c"],
                "outlet_temperature_delta_c": (
                    following["outlet_temperature_c"]
                    - current["outlet_temperature_c"]
                ),
                "methane_conversion_delta_percentage_points": (
                    following["methane_conversion_percent"]
                    - current["methane_conversion_percent"]
                ),
                "heat_duty_delta_kw": (
                    following["heat_duty_kw"] - current["heat_duty_kw"]
                ),
                "product_component_molar_flow_delta_kgmole_h": {
                    component: following_flows[component] - current_flows[component]
                    for component in current_flows
                },
                "product_component_molar_fraction_delta": {
                    component: (
                        following_fractions[component] - current_fractions[component]
                    )
                    for component in current_fractions
                },
            }
        )

    warnings = tuple(
        dict.fromkeys(
            warning for result in case_results for warning in result.warnings
        )
    )
    return ComparisonResult(
        scenario=plan.scenario,
        comparison_field=plan.comparison_field,
        case_results=case_results,
        case_summaries=summaries,
        adjacent_deltas=tuple(adjacent_deltas),
        assumptions=plan.assumptions,
        warnings=warnings,
    )
