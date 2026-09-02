"""Typed input and output contracts for the three fixed HYSYS scenarios."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


SCHEMA_VERSION = "1.0"


class Scenario(StrEnum):
    TOLUENE = "toluene_disproportionation"
    METHANE = "methane_steam_reforming"
    COAL = "coal_slurry_gasification"


class EngineeringValidationStatus(StrEnum):
    NOT_ASSESSED = "not_assessed"
    VALIDATED = "validated"
    LIMITED = "limited"


def _finite(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number; actual={value!r}")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be a finite number; actual={value!r}")
    return normalized


@dataclass(frozen=True)
class XyleneSplit:
    o_xylene: float = 1.0 / 3.0
    m_xylene: float = 1.0 / 3.0
    p_xylene: float = 1.0 / 3.0

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            object.__setattr__(self, name, _finite(name, getattr(self, name)))
            if getattr(self, name) < 0.0:
                raise ValueError(f"{name} must be greater than or equal to 0")
        if not math.isclose(
            self.o_xylene + self.m_xylene + self.p_xylene,
            1.0,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError("xylene_split fractions must sum to 1")


@dataclass(frozen=True)
class TolueneInputs:
    feed_mass_flow_kg_h: float = 10000.0
    feed_temperature_c: float = 380.0
    pressure_bar: float = 25.0
    conversion: float = 0.50
    xylene_split: XyleneSplit = field(default_factory=XyleneSplit)

    def __post_init__(self) -> None:
        for name in (
            "feed_mass_flow_kg_h",
            "feed_temperature_c",
            "pressure_bar",
            "conversion",
        ):
            object.__setattr__(self, name, _finite(name, getattr(self, name)))
        if not isinstance(self.xylene_split, XyleneSplit):
            raise TypeError("xylene_split must be an XyleneSplit")
        if self.feed_mass_flow_kg_h <= 0.0:
            raise ValueError("feed_mass_flow_kg_h must be greater than 0")
        if self.pressure_bar <= 0.0:
            raise ValueError("pressure_bar must be greater than 0")
        if self.feed_temperature_c <= -273.15:
            raise ValueError("feed_temperature_c must be above absolute zero")
        if not 0.0 <= self.conversion <= 1.0:
            raise ValueError("conversion must be between 0 and 1")


@dataclass(frozen=True)
class MethaneInputs:
    total_feed_molar_flow_kgmole_h: float = 100.0
    steam_to_carbon_ratio: float = 2.7
    feed_temperature_c: float = 520.0
    pressure_bar: float = 13.5
    outlet_temperature_c: float = 600.0

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            object.__setattr__(self, name, _finite(name, getattr(self, name)))
        if self.total_feed_molar_flow_kgmole_h <= 0.0:
            raise ValueError("total_feed_molar_flow_kgmole_h must be greater than 0")
        if self.steam_to_carbon_ratio <= 0.0:
            raise ValueError("steam_to_carbon_ratio must be greater than 0")
        if self.pressure_bar <= 0.0:
            raise ValueError("pressure_bar must be greater than 0")
        if self.feed_temperature_c <= -273.15 or self.outlet_temperature_c <= -273.15:
            raise ValueError("temperatures must be above absolute zero")


@dataclass(frozen=True)
class CoalInputs:
    slurry_mass_flow_kg_h: float = 1000.0
    coal_mass_fraction: float = 0.62
    feed_temperature_c: float = 40.0
    pressure_bar: float = 40.0
    outlet_temperature_c: float = 1400.0

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            object.__setattr__(self, name, _finite(name, getattr(self, name)))
        if self.slurry_mass_flow_kg_h <= 0.0:
            raise ValueError("slurry_mass_flow_kg_h must be greater than 0")
        if not 0.0 < self.coal_mass_fraction < 1.0:
            raise ValueError("coal_mass_fraction must be between 0 and 1")
        if self.pressure_bar <= 0.0:
            raise ValueError("pressure_bar must be greater than 0")
        if self.feed_temperature_c <= -273.15 or self.outlet_temperature_c <= -273.15:
            raise ValueError("temperatures must be above absolute zero")


ScenarioInputs = TolueneInputs | MethaneInputs | CoalInputs

EXPECTED_INPUT_TYPE: dict[Scenario, type[ScenarioInputs]] = {
    Scenario.TOLUENE: TolueneInputs,
    Scenario.METHANE: MethaneInputs,
    Scenario.COAL: CoalInputs,
}


@dataclass(frozen=True)
class CaseSpec:
    scenario: Scenario
    inputs: ScenarioInputs
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.scenario, Scenario):
            raise TypeError(f"scenario must be a Scenario; actual={self.scenario!r}")
        expected = EXPECTED_INPUT_TYPE[self.scenario]
        if not isinstance(self.inputs, expected):
            raise TypeError(
                f"{self.scenario.value} requires {expected.__name__}; "
                f"actual={type(self.inputs).__name__}"
            )
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported CaseSpec schema_version={self.schema_version!r}; "
                f"expected={SCHEMA_VERSION!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "scenario": self.scenario.value,
            "inputs": asdict(self.inputs),
        }


@dataclass(frozen=True)
class ReactorResult:
    type: str
    name: str
    selection_reason: str


@dataclass(frozen=True)
class BalanceResult:
    mass_error_percent: float
    element_error_percent: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class CaseResult:
    scenario: Scenario
    reactor: ReactorResult
    conditions: dict[str, Any]
    metrics: dict[str, float]
    streams: dict[str, Any]
    aggregates: dict[str, Any]
    balances: BalanceResult
    solver_converged: bool
    engineering_validation_status: EngineeringValidationStatus
    assumptions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    status: str = "success"
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.status != "success":
            raise ValueError("CaseResult status must be 'success'")
        if not self.solver_converged:
            raise ValueError("A successful CaseResult requires solver_converged=True")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["scenario"] = self.scenario.value
        result["engineering_validation_status"] = (
            self.engineering_validation_status.value
        )
        return result
