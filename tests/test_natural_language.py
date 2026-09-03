from __future__ import annotations

import unittest

from core.models import ComparisonPlan, Scenario
from core.natural_language import (
    ClarificationRequired,
    parse_text_request,
    parse_text_to_spec,
)


METHANE_ASSESSMENT_TEXT = (
    "我需要模拟甲烷蒸汽重整。进料是甲烷和水蒸气（摩尔比 1:2.7）有两个反应，"
    "主反应甲烷和水反应生成一氧化碳和氢气；副反应一样化碳和水蒸汽反应生成"
    "二氧化碳和氢气，请分析以下两种情况下反应炉的组分分布："
    "1、重整炉出口气温度为 710°C，压力 13.5 bar，进料温度520℃；"
    "2、重整炉出口气温度为600℃，压力13.5bar，进料温度520℃。"
    "进料流量可以自定，要求符合一个工厂一年正常的处理量"
)

TOLUENE_ASSESSMENT_TEXT = (
    "请帮我完成甲苯歧化反应的模拟，甲苯原料进入转化率反应器，发生歧化反应："
    "2C₇H₈ → C₆H₆ + C₈H₁₀。甲苯进料流量10000kg/h，进料温度为380℃，"
    "操作压力2.5MPa，甲苯转化率为50%，反应产物为苯和二甲苯（邻、间、对三种异构体），"
    "请配置反应并模拟产物分布和流股组成。用户明确提出不对反应动力学进行深入探讨，"
    "只需要知道在该转化率下反应器出口的浓度分布，不考虑其他副反应"
)

COAL_ASSESSMENT_TEXT = (
    "我要模拟水煤浆的气化过程。进料为煤炭和水，流量80000Nm3/h，压力40bar，"
    "水煤浆进料浓度62wt%，进料温度40摄氏度，主要反应：C+H2O → CO+H2。"
    "请帮我计算一下气化炉出口温度为1400度时出口组成及CO的收率。反应器灰分不做考虑。"
    "CO收率就是煤炭有多少转化成CO，同时希望考虑到里面有副反应的情况"
)


class NaturalLanguageParserTests(unittest.TestCase):
    def test_assessment_toluene_text_converts_mpa_to_bar(self) -> None:
        spec = parse_text_request(TOLUENE_ASSESSMENT_TEXT)
        self.assertEqual(spec.scenario, Scenario.TOLUENE)
        self.assertEqual(spec.inputs.feed_mass_flow_kg_h, 10000.0)
        self.assertEqual(spec.inputs.feed_temperature_c, 380.0)
        self.assertEqual(spec.inputs.pressure_bar, 25.0)
        self.assertEqual(spec.inputs.conversion, 0.50)

    def test_assessment_methane_text_builds_sequential_comparison(self) -> None:
        plan = parse_text_request(METHANE_ASSESSMENT_TEXT)
        self.assertIsInstance(plan, ComparisonPlan)
        self.assertEqual(plan.scenario, Scenario.METHANE)
        self.assertEqual(plan.execution_mode, "sequential")
        self.assertEqual(plan.comparison_field, "outlet_temperature_c")
        self.assertEqual(
            [case.inputs.outlet_temperature_c for case in plan.case_specs],
            [710.0, 600.0],
        )
        for case in plan.case_specs:
            self.assertEqual(case.inputs.steam_to_carbon_ratio, 2.7)
            self.assertEqual(case.inputs.feed_temperature_c, 520.0)
            self.assertEqual(case.inputs.pressure_bar, 13.5)

    def test_assessment_coal_text_rejects_nm3_flow(self) -> None:
        with self.assertRaises(ClarificationRequired) as caught:
            parse_text_request(COAL_ASSESSMENT_TEXT)
        questions = "".join(caught.exception.questions)
        self.assertIn("Nm3/h", questions)
        self.assertIn("kg/h", questions)

    def test_corrected_assessment_coal_wording_is_supported(self) -> None:
        spec = parse_text_request(
            "水煤浆气化，水煤浆质量流量1000 kg/h，压力40bar，"
            "水煤浆进料浓度62wt%，进料温度40摄氏度，出口气温度1400度"
        )
        self.assertEqual(spec.inputs.slurry_mass_flow_kg_h, 1000.0)
        self.assertEqual(spec.inputs.coal_mass_fraction, 0.62)
        self.assertEqual(spec.inputs.outlet_temperature_c, 1400.0)

    def test_unconsumed_engineering_value_requires_clarification(self) -> None:
        with self.assertRaises(ClarificationRequired) as caught:
            parse_text_request("甲苯歧化，进料流量12 t/h，转化率50%")
        self.assertIn("12 t/h", "".join(caught.exception.questions))

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

    def test_parses_assumed_xylene_split(self) -> None:
        spec = parse_text_to_spec("甲苯歧化，o/m/p 20/30/50，转化率 50%")
        self.assertEqual(spec.inputs.xylene_split.o_xylene, 0.2)
        self.assertEqual(spec.inputs.xylene_split.m_xylene, 0.3)
        self.assertEqual(spec.inputs.xylene_split.p_xylene, 0.5)

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
