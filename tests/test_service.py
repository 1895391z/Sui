from __future__ import annotations

import unittest
from contextlib import contextmanager

from core.errors import AdapterExecutionError, ResultValidationError
from core.models import (
    BalanceResult,
    CaseResult,
    CaseSpec,
    ComparisonPlan,
    EngineeringValidationStatus,
    MethaneInputs,
    ReactorResult,
    Scenario,
    TolueneInputs,
)
from core.service import execute_case, execute_comparison_plan


class ServiceBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = CaseSpec(Scenario.TOLUENE, TolueneInputs())

    def test_adapter_exception_is_wrapped(self) -> None:
        def failing_runner(spec: CaseSpec) -> dict[str, object]:
            raise OSError("COM unavailable")

        with self.assertRaisesRegex(AdapterExecutionError, "COM unavailable"):
            execute_case(self.spec, runners={Scenario.TOLUENE: failing_runner})

    def test_invalid_native_result_is_wrapped(self) -> None:
        def invalid_runner(spec: CaseSpec) -> dict[str, object]:
            return {"converged": False}

        with self.assertRaisesRegex(ResultValidationError, "result validation failed"):
            execute_case(self.spec, runners={Scenario.TOLUENE: invalid_runner})

    def test_comparison_plan_uses_independent_sequential_sessions(self) -> None:
        specs = tuple(
            CaseSpec(
                Scenario.METHANE,
                MethaneInputs(outlet_temperature_c=temperature),
            )
            for temperature in (710.0, 600.0)
        )
        plan = ComparisonPlan(
            Scenario.METHANE, specs, "outlet_temperature_c"
        )
        events: list[str] = []

        @contextmanager
        def session():
            events.append("enter")
            try:
                yield
            finally:
                events.append("exit")

        def executor(spec: CaseSpec) -> CaseResult:
            temperature = spec.inputs.outlet_temperature_c
            events.append(f"execute:{temperature:g}")
            return methane_case_result(spec)

        result = execute_comparison_plan(
            plan, session_factory=session, case_executor=executor
        )
        self.assertEqual(
            events,
            ["enter", "execute:710", "exit", "enter", "execute:600", "exit"],
        )
        self.assertEqual(len(result.case_results), 2)

    def test_comparison_failure_cleans_current_session_and_stops(self) -> None:
        specs = tuple(
            CaseSpec(
                Scenario.METHANE,
                MethaneInputs(outlet_temperature_c=temperature),
            )
            for temperature in (710.0, 600.0)
        )
        plan = ComparisonPlan(
            Scenario.METHANE, specs, "outlet_temperature_c"
        )
        events: list[str] = []

        @contextmanager
        def session():
            events.append("enter")
            try:
                yield
            finally:
                events.append("exit")

        def executor(spec: CaseSpec) -> CaseResult:
            temperature = spec.inputs.outlet_temperature_c
            events.append(f"execute:{temperature:g}")
            if temperature == 600.0:
                raise AdapterExecutionError("second case failed")
            return methane_case_result(spec)

        with self.assertRaisesRegex(AdapterExecutionError, "second case failed"):
            execute_comparison_plan(
                plan, session_factory=session, case_executor=executor
            )
        self.assertEqual(
            events,
            ["enter", "execute:710", "exit", "enter", "execute:600", "exit"],
        )


def methane_case_result(spec: CaseSpec) -> CaseResult:
    temperature = spec.inputs.outlet_temperature_c
    return CaseResult(
        scenario=Scenario.METHANE,
        reactor=ReactorResult("Equilibrium Reactor", "ERV-100", "test"),
        conditions={"outlet_temperature_c": temperature},
        metrics={
            "methane_conversion_percent": temperature / 10.0,
            "heat_duty_kw": temperature,
        },
        streams={"feed": {}, "products": {}},
        aggregates={
            "combined_component_molar_flow_kgmole_h": {
                "Methane": 10.0,
                "H2O": 20.0,
                "CO": 5.0,
                "CO2": 5.0,
                "Hydrogen": 30.0,
            }
        },
        balances=BalanceResult(0.0, {"C": 0.0, "H": 0.0, "O": 0.0}),
        solver_converged=True,
        engineering_validation_status=EngineeringValidationStatus.NOT_ASSESSED,
    )


if __name__ == "__main__":
    unittest.main()
