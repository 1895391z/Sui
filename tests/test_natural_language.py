from __future__ import annotations

import unittest

from core.models import Scenario
from core.natural_language import ClarificationRequired, parse_text_to_spec


class NaturalLanguageParserTests(unittest.TestCase):
    def test_parses_toluene_parameters_and_percent_conversion(self) -> None:
        spec = parse_text_to_spec(
            "运行甲苯歧化：进料流量 12000 kg/h，进料温度 390°C，"
            "压力 26 bar，转化率 60%。"
        )
        self.assertEqual(spec.scenario, Scenario.TOLUENE)
        self.assertEqual(spec.inputs.feed_mass_flow_kg_h, 12000.0)
        self.assertEqual(spec.inputs.feed_temperature_c, 390.0)
        self.assertEqual(spec.inputs.pressure_bar, 26.0)
        self.assertEqual(spec.inputs.conversion, 0.60)

    def test_parses_methane_parameters_and_aliases(self) -> None:
        spec = parse_text_to_spec(
            "Methane steam reforming, total feed molar flow 110 kgmol/h, "
            "S/C 3.0, feed temperature 530 C, pressure 14 bar, "
            "outlet temperature 710 C"
        )
        self.assertEqual(spec.scenario, Scenario.METHANE)
        self.assertEqual(spec.inputs.total_feed_molar_flow_kgmole_h, 110.0)
        self.assertEqual(spec.inputs.steam_to_carbon_ratio, 3.0)
        self.assertEqual(spec.inputs.feed_temperature_c, 530.0)
        self.assertEqual(spec.inputs.outlet_temperature_c, 710.0)

    def test_parses_coal_parameters(self) -> None:
        spec = parse_text_to_spec(
            "水煤浆气化，水煤浆质量流量 900 kg/h，煤浆浓度 60 wt%，"
            "进料温度 45°C，压力 38 bar，出口温度 1350°C"
        )
        self.assertEqual(spec.scenario, Scenario.COAL)
        self.assertEqual(spec.inputs.slurry_mass_flow_kg_h, 900.0)
        self.assertEqual(spec.inputs.coal_mass_fraction, 0.60)
        self.assertEqual(spec.inputs.outlet_temperature_c, 1350.0)

    def test_scenario_only_uses_explicit_defaults(self) -> None:
        spec = parse_text_to_spec("请运行甲烷蒸汽重整默认工况")
        self.assertEqual(spec.scenario, Scenario.METHANE)
        self.assertEqual(spec.inputs.outlet_temperature_c, 600.0)

    def test_missing_unit_requires_clarification(self) -> None:
        with self.assertRaises(ClarificationRequired) as caught:
            parse_text_to_spec("运行甲苯歧化，压力 25，转化率 50%")
        self.assertIn("压力", "".join(caught.exception.questions))

    def test_conflicting_values_require_clarification(self) -> None:
        with self.assertRaises(ClarificationRequired) as caught:
            parse_text_to_spec("甲烷蒸汽重整，出口温度 600°C，出口温度 710°C")
        self.assertIn("多个", "".join(caught.exception.questions))

    def test_multiple_scenarios_require_clarification(self) -> None:
        with self.assertRaises(ClarificationRequired):
            parse_text_to_spec("先做甲苯歧化，再做甲烷蒸汽重整")


if __name__ == "__main__":
    unittest.main()
