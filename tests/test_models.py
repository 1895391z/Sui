from __future__ import annotations

import unittest

from core.models import (
    CaseSpec,
    CoalInputs,
    MethaneInputs,
    Scenario,
    TolueneInputs,
    XyleneSplit,
)


class CaseSpecTests(unittest.TestCase):
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
