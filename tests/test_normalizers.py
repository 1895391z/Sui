from __future__ import annotations

import unittest

from core.models import (
    CaseSpec,
    CoalInputs,
    ComparisonPlan,
    EngineeringValidationStatus,
    MethaneInputs,
    Scenario,
    TolueneInputs,
)
from core.normalizers import normalize_comparison_result, normalize_result


def base_raw(reactor_type: str) -> dict[str, object]:
    return {
        "reactor_type": reactor_type,
        "reactor_name": "R-TEST",
        "selection_reason": "test",
        "converged": True,
        "feed": {"name": "Feed"},
        "products": {
            "streams": {"Product": {"name": "Product"}},
            "total_mass_flow_kg_h": 1.0,
        },
        "mass_balance_error_percent": 0.0,
        "assumptions": ["test assumption"],
    }


class NormalizerTests(unittest.TestCase):
    def test_methane_comparison_summarizes_results_and_deltas(self) -> None:
        specs = tuple(
            CaseSpec(
                Scenario.METHANE,
                MethaneInputs(outlet_temperature_c=temperature),
            )
            for temperature in (710.0, 600.0)
        )
        plan = ComparisonPlan(
            scenario=Scenario.METHANE,
            case_specs=specs,
            comparison_field="outlet_temperature_c",
        )
        results = []
        for spec, conversion, duty, methane, hydrogen in (
            (specs[0], 54.0, 1080.0, 12.0, 52.0),
            (specs[1], 30.0, 545.0, 19.0, 31.0),
        ):
            raw = base_raw("Equilibrium Reactor")
            raw["products"]["combined_component_molar_flow_kgmole_h"] = {
                "Methane": methane,
                "H2O": 25.0,
                "CO": 5.0,
                "CO2": 7.0,
                "Hydrogen": hydrogen,
            }
            raw.update(
                {
                    "methane_conversion_percent": conversion,
                    "heat_duty_kw": duty,
                    "element_balance_error_percent": {
                        "C": 0.0,
                        "H": 0.0,
                        "O": 0.0,
                    },
                }
            )
            results.append(normalize_result(spec, raw))

        comparison = normalize_comparison_result(plan, tuple(results)).to_dict()
        self.assertEqual(comparison["status"], "success")
        self.assertEqual(
            [item["outlet_temperature_c"] for item in comparison["case_summaries"]],
            [710.0, 600.0],
        )
        delta = comparison["adjacent_deltas"][0]
        self.assertEqual(delta["outlet_temperature_delta_c"], -110.0)
        self.assertEqual(delta["methane_conversion_delta_percentage_points"], -24.0)
        self.assertEqual(delta["heat_duty_delta_kw"], -535.0)
        self.assertIn("Hydrogen", delta["product_component_molar_fraction_delta"])

    def test_toluene_mapping(self) -> None:
        spec = CaseSpec(Scenario.TOLUENE, TolueneInputs())
        raw = base_raw("Conversion Reactor")
        raw.update({"conversion_fraction": 0.5, "conversion_percent": 50.0})
        result = normalize_result(spec, raw)
        self.assertEqual(result.metrics["conversion_percent"], 50.0)
        self.assertEqual(
            result.engineering_validation_status,
            EngineeringValidationStatus.NOT_ASSESSED,
        )

    def test_toluene_preserves_assumed_xylene_distribution(self) -> None:
        spec = CaseSpec(Scenario.TOLUENE, TolueneInputs())
        raw = base_raw("Conversion Reactor")
        raw["products"]["xylene_isomer_distribution"] = {
            "derived_from_assumed_selectivity": True,
            "split_fraction": {"o_xylene": 1 / 3, "m_xylene": 1 / 3, "p_xylene": 1 / 3},
        }
        raw.update({"conversion_fraction": 0.5, "conversion_percent": 50.0})
        result = normalize_result(spec, raw)
        self.assertTrue(
            result.aggregates["xylene_isomer_distribution"]
            ["derived_from_assumed_selectivity"]
        )

    def test_methane_mapping(self) -> None:
        spec = CaseSpec(Scenario.METHANE, MethaneInputs())
        raw = base_raw("Equilibrium Reactor")
        raw.update(
            {
                "methane_conversion_percent": 30.0,
                "heat_duty_kw": 500.0,
                "element_balance_error_percent": {"C": 0.0, "H": 0.0, "O": 0.0},
            }
        )
        result = normalize_result(spec, raw)
        self.assertEqual(result.metrics["heat_duty_kw"], 500.0)
        self.assertEqual(result.balances.element_error_percent["C"], 0.0)

    def test_coal_mapping_preserves_warning(self) -> None:
        spec = CaseSpec(Scenario.COAL, CoalInputs())
        raw = base_raw("Gibbs Reactor")
        raw.update(
            {
                "co_yield_percent": 40.86,
                "carbon_conversion_percent": 61.29,
                "syngas_hydrogen_molar_fraction": 2.47e-7,
                "heat_duty_kw": 1487.58,
                "element_balance_error_percent": {"C": 0.0, "H": 0.0, "O": 0.0},
                "thermodynamic_validity": {
                    "within_reported_component_gibbs_range": False
                },
                "warnings": ["high-temperature extrapolation"],
            }
        )
        result = normalize_result(spec, raw)
        payload = result.to_dict()
        self.assertEqual(payload["engineering_validation_status"], "limited")
        self.assertEqual(payload["warnings"], ["high-temperature extrapolation"])
        self.assertFalse(
            payload["aggregates"]["thermodynamic_validity"]
            ["within_reported_component_gibbs_range"]
        )

    def test_unconverged_native_result_is_rejected(self) -> None:
        spec = CaseSpec(Scenario.TOLUENE, TolueneInputs())
        raw = base_raw("Conversion Reactor")
        raw["converged"] = False
        with self.assertRaisesRegex(RuntimeError, "converged=True"):
            normalize_result(spec, raw)


if __name__ == "__main__":
    unittest.main()
