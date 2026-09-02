from __future__ import annotations

import unittest

from core.models import (
    CaseSpec,
    CoalInputs,
    MethaneInputs,
    Scenario,
    TolueneInputs,
)


class CaseSpecTests(unittest.TestCase):
    def test_defaults_are_explicit_and_json_ready(self) -> None:
        spec = CaseSpec(Scenario.COAL, CoalInputs())
        self.assertEqual(spec.to_dict()["inputs"]["coal_mass_fraction"], 0.62)
        self.assertEqual(spec.to_dict()["scenario"], "coal_slurry_gasification")

    def test_scenario_rejects_wrong_input_type(self) -> None:
        with self.assertRaises(TypeError):
            CaseSpec(Scenario.COAL, TolueneInputs())

    def test_invalid_values_are_rejected(self) -> None:
        invalid_factories = (
            lambda: TolueneInputs(conversion=1.01),
            lambda: MethaneInputs(steam_to_carbon_ratio=0.0),
            lambda: CoalInputs(coal_mass_fraction=1.0),
            lambda: CoalInputs(pressure_bar=float("nan")),
        )
        for factory in invalid_factories:
            with self.subTest(factory=factory), self.assertRaises(ValueError):
                factory()


if __name__ == "__main__":
    unittest.main()
