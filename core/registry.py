"""Lazy adapter registry; importing this module never imports pywin32 adapters."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Callable, Mapping

from .models import CaseSpec, Scenario


NativeRunner = Callable[[CaseSpec], dict[str, Any]]


def run_toluene(spec: CaseSpec) -> dict[str, Any]:
    from toluene.toluene_adapter import run_toluene_case

    return run_toluene_case(**asdict(spec.inputs))


def run_methane(spec: CaseSpec) -> dict[str, Any]:
    from methane.methane_reforming_adapter import run_methane_reforming_case

    return run_methane_reforming_case(**asdict(spec.inputs))


def run_coal(spec: CaseSpec) -> dict[str, Any]:
    from coal.coal_gasification_adapter import run_coal_gasification_case

    return run_coal_gasification_case(**asdict(spec.inputs))


DEFAULT_RUNNERS: Mapping[Scenario, NativeRunner] = {
    Scenario.TOLUENE: run_toluene,
    Scenario.METHANE: run_methane,
    Scenario.COAL: run_coal,
}


def dispatch_native(
    spec: CaseSpec,
    runners: Mapping[Scenario, NativeRunner] | None = None,
) -> dict[str, Any]:
    registry = DEFAULT_RUNNERS if runners is None else runners
    try:
        runner = registry[spec.scenario]
    except KeyError as exc:
        raise ValueError(f"No runner registered for scenario {spec.scenario.value!r}") from exc
    return runner(spec)
