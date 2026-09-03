from __future__ import annotations

import unittest

from core.models import (
    CaseSpec,
    CoalInputs,
    ComparisonPlan,
    ComparisonResult,
    BalanceResult,
    CaseResult,
    EngineeringValidationStatus,
    MethaneInputs,
    ReactorResult,
    Scenario,
    TolueneInputs,
    XyleneSplit,
)


class CaseSpecTests(unittest.TestCase):
    def test_comparison_result_serializes_nested_case_results(self) -> None:
        case_result = CaseResult(
            scenario=Scenario.METHANE,
            reactor=ReactorResult("Equilibrium Reactor", "ERV-100", "test"),
            conditions={"outlet_temperature_c": 710.0},
            metrics={"methane_conversion_percent": 54.0, "heat_duty_kw": 1080.0},
            streams={"feed": {}, "products": {}},
            aggregates={},
            balances=BalanceResult(0.0, {"C": 0.0, "H": 0.0, "O": 0.0}),
            solver_converged=True,
            engineering_validation_status=EngineeringValidationStatus.NOT_ASSESSED,
        )
        result = ComparisonResult(
            scenario=Scenario.METHANE,
            comparison_field="outlet_temperature_c",
            case_results=(case_result, case_result),
            case_summaries=({"case_index": 0}, {"case_index": 1}),
            adjacent_deltas=({"from_case_index": 0, "to_case_index": 1},),
        )
        payload = result.to_dict()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["execution_mode"], "sequential")
        self.assertEqual(payload["case_results"][0]["scenario"], Scenario.METHANE)

    def test_methane_comparison_plan_is_sequential_and_serializable(self) -> None:
        plan = ComparisonPlan(
            scenario=Scenario.METHANE,
            case_specs=(
                CaseSpec(
                    Scenario.METHANE,
                    MethaneInputs(outlet_temperature_c=710.0),
                ),
                CaseSpec(
                    Scenario.METHANE,
                    MethaneInputs(outlet_temperature_c=600.0),
                ),
            ),
            comparison_field="outlet_temperature_c",
        )
        payload = plan.to_dict()
        self.assertEqual(payload["execution_mode"], "sequential")
        self.assertEqual(len(payload["case_specs"]), 2)

    def test_comparison_plan_rejects_duplicate_values(self) -> None:
        case = CaseSpec(Scenario.METHANE, MethaneInputs())
        with self.assertRaises(ValueError):
            ComparisonPlan(
                scenario=Scenario.METHANE,
                case_specs=(case, case),
                comparison_field="outlet_temperature_c",
            )

    def test_comparison_plan_rejects_wrong_schema(self) -> None:
        with self.assertRaisesRegex(ValueError, "schema_version"):
            ComparisonPlan(
                scenario=Scenario.METHANE,
                case_specs=(
                    CaseSpec(
                        Scenario.METHANE,
                        MethaneInputs(outlet_temperature_c=710.0),
                    ),
                    CaseSpec(Scenario.METHANE, MethaneInputs()),
                ),
                comparison_field="outlet_temperature_c",
                schema_version="2.0",
            )

    def test_defaults_are_explicit_and_json_ready(self) -> None:
        spec = CaseSpec(Scenario.COAL, CoalInputs())
        self.assertEqual(spec.to_dict()["inputs"]["coal_mass_fraction"], 0.62)
        self.assertEqual(spec.to_dict()["scenario"], "coal_slurry_gasification")

        toluene = CaseSpec(Scenario.TOLUENE, TolueneInputs()).to_dict()
        self.assertAlmostEqual(
            sum(toluene["inputs"]["xylene_split"].values()), 1.0
        )

    def test_scenario_rejects_wrong_input_type(self) -> None:
        with self.assertRaises(TypeError):
            CaseSpec(Scenario.COAL, TolueneInputs())

    def test_case_spec_json_round_trip_for_all_scenarios(self) -> None:
        specs = (
            CaseSpec(Scenario.TOLUENE, TolueneInputs()),
            CaseSpec(Scenario.METHANE, MethaneInputs()),
            CaseSpec(Scenario.COAL, CoalInputs()),
        )
        for spec in specs:
            with self.subTest(scenario=spec.scenario):
                self.assertEqual(CaseSpec.from_dict(spec.to_dict()), spec)

    def test_case_spec_json_rejects_unknown_and_missing_fields(self) -> None:
        valid = CaseSpec(Scenario.COAL, CoalInputs()).to_dict()
        with self.assertRaisesRegex(ValueError, "unexpected"):
            CaseSpec.from_dict({**valid, "extra": True})

        missing_input = CaseSpec(Scenario.METHANE, MethaneInputs()).to_dict()
        del missing_input["inputs"]["pressure_bar"]
        with self.assertRaisesRegex(ValueError, "missing"):
            CaseSpec.from_dict(missing_input)

    def test_case_spec_json_rejects_invalid_nested_xylene_split(self) -> None:
        payload = CaseSpec(Scenario.TOLUENE, TolueneInputs()).to_dict()
        payload["inputs"]["xylene_split"]["unexpected"] = 0.0
        with self.assertRaisesRegex(ValueError, "xylene_split.*unexpected"):
            CaseSpec.from_dict(payload)

    def test_case_spec_json_rejects_schema_and_scenario_errors(self) -> None:
        wrong_version = CaseSpec(Scenario.COAL, CoalInputs()).to_dict()
        wrong_version["schema_version"] = "2.0"
        with self.assertRaisesRegex(ValueError, "schema_version"):
            CaseSpec.from_dict(wrong_version)

        wrong_scenario = CaseSpec(Scenario.COAL, CoalInputs()).to_dict()
        wrong_scenario["scenario"] = "unknown"
        with self.assertRaisesRegex(ValueError, "Unsupported CaseSpec scenario"):
            CaseSpec.from_dict(wrong_scenario)

    def test_invalid_values_are_rejected(self) -> None:
        invalid_factories = (
            lambda: TolueneInputs(conversion=1.01),
            lambda: MethaneInputs(steam_to_carbon_ratio=0.0),
            lambda: CoalInputs(coal_mass_fraction=1.0),
            lambda: CoalInputs(pressure_bar=float("nan")),
            lambda: XyleneSplit(0.2, 0.3, 0.4),
        )
        for factory in invalid_factories:
            with self.subTest(factory=factory), self.assertRaises(ValueError):
                factory()


if __name__ == "__main__":
    unittest.main()
