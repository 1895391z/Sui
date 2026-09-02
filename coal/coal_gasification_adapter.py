"""End-to-end HYSYS adapter for the fixed coal-slurry gasification scenario."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Iterable

import pythoncom
import win32com.client as win32


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")


COMPONENT_NAMES = ("Hydrogen", "H2O", "CO", "CO2", "Methane", "Carbon")
ELEMENT_COUNTS = {
    "Hydrogen": {"C": 0.0, "H": 2.0, "O": 0.0},
    "H2O": {"C": 0.0, "H": 2.0, "O": 1.0},
    "CO": {"C": 1.0, "H": 0.0, "O": 1.0},
    "CO2": {"C": 1.0, "H": 0.0, "O": 2.0},
    "Methane": {"C": 1.0, "H": 4.0, "O": 0.0},
    "Carbon": {"C": 1.0, "H": 0.0, "O": 0.0},
}

SUI_ROOT = Path(__file__).resolve().parent.parent
SEED_PATH = SUI_ROOT / "cases" / "constant" / "coal_gasification_seed.hsc"
RUNTIME_DIR = SUI_ROOT / "cases" / "runtime"
RUNTIME_PATH = RUNTIME_DIR / "coal_gasification_run.hsc"

COMPONENT_LIST_NAME = "Component List - 1"
FLUID_PACKAGE_NAME = "Basis-1"
REACTOR_NAME = "GBR-100"
FEED_NAME = "Feed"
VAPOUR_PRODUCT_NAME = "Syngas_Out"
BOTTOM_PRODUCT_NAME = "Bottom_Out"
ENERGY_STREAM_NAME = "Q_Heat"

RETRY_TIMEOUT_SECONDS = 30.0
RETRY_INTERVAL_SECONDS = 1.0
BALANCE_TOLERANCE_PERCENT = 0.1


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_inputs(
    slurry_mass_flow_kg_h: float,
    coal_mass_fraction: float,
    feed_temperature_c: float,
    pressure_bar: float,
    outlet_temperature_c: float,
) -> None:
    values = {
        "slurry_mass_flow_kg_h": slurry_mass_flow_kg_h,
        "coal_mass_fraction": coal_mass_fraction,
        "feed_temperature_c": feed_temperature_c,
        "pressure_bar": pressure_bar,
        "outlet_temperature_c": outlet_temperature_c,
    }
    for name, value in values.items():
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError(f"{name} must be a finite number; actual={value!r}")

    if slurry_mass_flow_kg_h <= 0.0:
        raise ValueError("slurry_mass_flow_kg_h must be greater than 0")
    if not 0.0 < coal_mass_fraction < 1.0:
        raise ValueError("coal_mass_fraction must be between 0 and 1")
    if pressure_bar <= 0.0:
        raise ValueError("pressure_bar must be greater than 0")
    if feed_temperature_c <= -273.15 or outlet_temperature_c <= -273.15:
        raise ValueError("temperatures must be above absolute zero")


def feed_mass_fractions(coal_mass_fraction: float) -> tuple[float, ...]:
    return (0.0, 1.0 - coal_mass_fraction, 0.0, 0.0, 0.0, coal_mass_fraction)


def prepare_runtime_case() -> str:
    if not SEED_PATH.is_file():
        raise FileNotFoundError(f"Coal gasification seed does not exist: {SEED_PATH}")
    if SEED_PATH.resolve() == RUNTIME_PATH.resolve():
        raise RuntimeError("Seed and runtime paths must be different")

    seed_hash = sha256(SEED_PATH)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(SEED_PATH, RUNTIME_PATH)
    except PermissionError as exc:
        raise RuntimeError(
            f"Cannot overwrite runtime case {RUNTIME_PATH}; close it in HYSYS first"
        ) from exc
    if sha256(RUNTIME_PATH) != seed_hash:
        raise RuntimeError("Runtime copy SHA-256 does not match the coal seed")
    print("RUNTIME_COPY_OK:", RUNTIME_PATH)
    return seed_hash


def collection_names(collection: Any) -> tuple[str, ...]:
    return tuple(str(collection.Item(index).name) for index in range(collection.Count))


def set_flex_values(variable: Any, values: Iterable[float]) -> None:
    values = tuple(float(value) for value in values)
    try:
        variable.SetValues(values)
    except Exception as first_error:
        try:
            variable.Values = values
        except Exception as second_error:
            raise RuntimeError(
                f"FlexVariable write failed: SetValues={first_error}; Values={second_error}"
            ) from second_error


def read_flex_values(variable: Any, unit: str | None = None) -> tuple[float, ...]:
    if unit is not None:
        try:
            return tuple(float(value) for value in variable.GetValues(unit))
        except Exception:
            pass
    return tuple(float(value) for value in variable.Values)


def assert_close(label: str, actual: float, expected: float, tolerance: float) -> None:
    if not math.isfinite(actual) or abs(actual - expected) > tolerance:
        raise RuntimeError(
            f"{label} validation failed: expected={expected}, actual={actual}, "
            f"tolerance={tolerance}"
        )


def get_model_objects(case: Any) -> dict[str, Any]:
    basis = case.BasisManager
    component_list = basis.ComponentLists.Item(COMPONENT_LIST_NAME)
    fluid_package = basis.FluidPackages.Item(FLUID_PACKAGE_NAME)
    component_names = collection_names(component_list.Components)

    if component_names != COMPONENT_NAMES:
        raise RuntimeError(
            f"Component names/order mismatch: expected={COMPONENT_NAMES}, "
            f"actual={component_names}"
        )
    if str(fluid_package.ComponentList.name) != COMPONENT_LIST_NAME:
        raise RuntimeError(
            f"{FLUID_PACKAGE_NAME} is not bound to {COMPONENT_LIST_NAME}"
        )
    if str(fluid_package.PropertyPackageName) != "Peng-Robinson":
        raise RuntimeError(
            f"Property package mismatch: actual={fluid_package.PropertyPackageName!r}"
        )

    flowsheet = case.Flowsheet
    reactor = flowsheet.Operations.Item(REACTOR_NAME)
    feed = flowsheet.MaterialStreams.Item(FEED_NAME)
    vapour_product = flowsheet.MaterialStreams.Item(VAPOUR_PRODUCT_NAME)
    bottom_product = flowsheet.MaterialStreams.Item(BOTTOM_PRODUCT_NAME)
    energy_stream = flowsheet.EnergyStreams.Item(ENERGY_STREAM_NAME)

    if str(reactor.TypeName).lower() != "gibbsreactorop":
        raise RuntimeError(
            f"Reactor type mismatch: expected='gibbsreactorop', actual={reactor.TypeName!r}"
        )

    actual_connections = {
        "feeds": collection_names(reactor.Feeds),
        "vapour_product": str(reactor.VapourProduct.name),
        "bottom_product": str(reactor.LiquidProduct.name),
        "energy_stream": str(reactor.EnergyStream.name),
    }
    expected_connections = {
        "feeds": (FEED_NAME,),
        "vapour_product": VAPOUR_PRODUCT_NAME,
        "bottom_product": BOTTOM_PRODUCT_NAME,
        "energy_stream": ENERGY_STREAM_NAME,
    }
    if actual_connections != expected_connections:
        raise RuntimeError(
            f"Reactor connections mismatch: expected={expected_connections}, "
            f"actual={actual_connections}"
        )

    print("VALIDATE_MODEL_OK")
    return {
        "reactor": reactor,
        "feed": feed,
        "vapour_product": vapour_product,
        "bottom_product": bottom_product,
        "energy_stream": energy_stream,
    }


def ensure_finite_vector(label: str, values: tuple[float, ...]) -> None:
    if len(values) != len(COMPONENT_NAMES):
        raise RuntimeError(
            f"{label} length mismatch: expected={len(COMPONENT_NAMES)}, "
            f"actual={len(values)}"
        )
    if not all(math.isfinite(value) for value in values):
        raise RuntimeError(f"{label} contains non-finite values: {values}")


def read_stream(stream: Any) -> dict[str, Any]:
    molar_fraction = read_flex_values(stream.ComponentMolarFraction)
    mass_fraction = read_flex_values(stream.ComponentMassFraction)
    component_molar_flow = read_flex_values(stream.ComponentMolarFlow, "kgmole/h")
    component_mass_flow = read_flex_values(stream.ComponentMassFlow, "kg/h")
    for label, values in (
        ("ComponentMolarFraction", molar_fraction),
        ("ComponentMassFraction", mass_fraction),
        ("ComponentMolarFlow", component_molar_flow),
        ("ComponentMassFlow", component_mass_flow),
    ):
        ensure_finite_vector(f"{stream.name}.{label}", values)

    result = {
        "name": str(stream.name),
        "temperature_c": float(stream.Temperature.GetValue("C")),
        "pressure_bar": float(stream.Pressure.GetValue("bar")),
        "mass_flow_kg_h": float(stream.MassFlow.GetValue("kg/h")),
        "molar_flow_kgmole_h": float(stream.MolarFlow.GetValue("kgmole/h")),
        "component_molar_fraction": dict(
            zip(COMPONENT_NAMES, molar_fraction, strict=True)
        ),
        "component_mass_fraction": dict(
            zip(COMPONENT_NAMES, mass_fraction, strict=True)
        ),
        "component_molar_flow_kgmole_h": dict(
            zip(COMPONENT_NAMES, component_molar_flow, strict=True)
        ),
        "component_mass_flow_kg_h": dict(
            zip(COMPONENT_NAMES, component_mass_flow, strict=True)
        ),
    }
    scalar_values = (
        result["temperature_c"],
        result["pressure_bar"],
        result["mass_flow_kg_h"],
        result["molar_flow_kgmole_h"],
    )
    if not all(math.isfinite(float(value)) for value in scalar_values):
        raise RuntimeError(f"{stream.name} contains non-finite scalar results: {result}")
    if result["mass_flow_kg_h"] <= 0.0 or result["molar_flow_kgmole_h"] <= 0.0:
        raise RuntimeError(f"{stream.name} has a non-positive flow: {result}")
    if any(value < -1e-8 for value in component_molar_flow + component_mass_flow):
        raise RuntimeError(f"{stream.name} contains a negative component flow")
    assert_close(
        f"{stream.name} molar-fraction sum", sum(molar_fraction), 1.0, 1e-6
    )
    assert_close(
        f"{stream.name} mass-fraction sum", sum(mass_fraction), 1.0, 1e-6
    )
    return result


def element_totals(component_molar_flows: dict[str, float]) -> dict[str, float]:
    return {
        element: sum(
            component_molar_flows[component] * ELEMENT_COUNTS[component][element]
            for component in COMPONENT_NAMES
        )
        for element in ("C", "H", "O")
    }


def balance_errors(
    feed_component_flows: dict[str, float],
    product_component_flows: dict[str, float],
) -> dict[str, float]:
    feed_elements = element_totals(feed_component_flows)
    product_elements = element_totals(product_component_flows)
    errors: dict[str, float] = {}
    for element, feed_total in feed_elements.items():
        if feed_total <= 0.0:
            raise RuntimeError(f"Feed contains no {element}; element balance is undefined")
        errors[element] = abs(product_elements[element] - feed_total) / feed_total * 100.0
    return errors


def configure_and_read_once(
    case: Any,
    slurry_mass_flow_kg_h: float,
    coal_mass_fraction: float,
    feed_temperature_c: float,
    pressure_bar: float,
    outlet_temperature_c: float,
) -> dict[str, Any]:
    objects = get_model_objects(case)
    feed = objects["feed"]
    vapour_product = objects["vapour_product"]
    bottom_product = objects["bottom_product"]
    expected_mass_fractions = feed_mass_fractions(coal_mass_fraction)

    solver = case.Solver
    solver.CanSolve = False
    feed.Temperature.SetValue(feed_temperature_c, "C")
    feed.Pressure.SetValue(pressure_bar, "bar")
    feed.MassFlow.SetValue(slurry_mass_flow_kg_h, "kg/h")
    set_flex_values(feed.ComponentMassFraction, expected_mass_fractions)
    vapour_product.Temperature.SetValue(outlet_temperature_c, "C")
    solver.CanSolve = True
    print("WRITE_INPUT_OK")

    feed_result = read_stream(feed)
    vapour_result = read_stream(vapour_product)
    bottom_result = read_stream(bottom_product)
    product_results = {
        VAPOUR_PRODUCT_NAME: vapour_result,
        BOTTOM_PRODUCT_NAME: bottom_result,
    }

    assert_close("Feed temperature", feed_result["temperature_c"], feed_temperature_c, 0.01)
    assert_close("Feed pressure", feed_result["pressure_bar"], pressure_bar, 0.01)
    assert_close("Feed mass flow", feed_result["mass_flow_kg_h"], slurry_mass_flow_kg_h, 0.1)
    assert_close(
        "Vapour outlet temperature",
        vapour_result["temperature_c"],
        outlet_temperature_c,
        0.01,
    )
    assert_close(
        "Bottom outlet temperature",
        bottom_result["temperature_c"],
        outlet_temperature_c,
        0.01,
    )
    assert_close("Vapour outlet pressure", vapour_result["pressure_bar"], pressure_bar, 0.01)
    assert_close("Bottom outlet pressure", bottom_result["pressure_bar"], pressure_bar, 0.01)
    for index, expected in enumerate(expected_mass_fractions):
        actual = tuple(feed_result["component_mass_fraction"].values())[index]
        assert_close(f"Feed mass fraction[{index}]", actual, expected, 1e-8)
    if not bool(case.Solver.CanSolve):
        raise RuntimeError("Solver.CanSolve is False")

    combined_molar_flows = {
        component: sum(
            stream["component_molar_flow_kgmole_h"][component]
            for stream in product_results.values()
        )
        for component in COMPONENT_NAMES
    }
    combined_mass_flows = {
        component: sum(
            stream["component_mass_flow_kg_h"][component]
            for stream in product_results.values()
        )
        for component in COMPONENT_NAMES
    }
    total_product_mass = sum(
        stream["mass_flow_kg_h"] for stream in product_results.values()
    )
    mass_balance_error_percent = (
        abs(total_product_mass - feed_result["mass_flow_kg_h"])
        / feed_result["mass_flow_kg_h"]
        * 100.0
    )
    element_balance_error_percent = balance_errors(
        feed_result["component_molar_flow_kgmole_h"], combined_molar_flows
    )
    if mass_balance_error_percent >= BALANCE_TOLERANCE_PERCENT:
        raise RuntimeError(
            f"Mass-balance error exceeds limit: {mass_balance_error_percent}%"
        )
    failed_elements = {
        element: error
        for element, error in element_balance_error_percent.items()
        if error >= BALANCE_TOLERANCE_PERCENT
    }
    if failed_elements:
        raise RuntimeError(f"Element-balance error exceeds limit: {failed_elements}")

    feed_coal_carbon = feed_result["component_molar_flow_kgmole_h"]["Carbon"]
    if feed_coal_carbon <= 0.0:
        raise RuntimeError("Feed coal-carbon molar flow is not positive")
    co_yield_percent = combined_molar_flows["CO"] / feed_coal_carbon * 100.0
    residual_carbon = combined_molar_flows["Carbon"]
    carbon_conversion_percent = (feed_coal_carbon - residual_carbon) / feed_coal_carbon * 100.0
    hydrogen_molar_fraction = vapour_result["component_molar_fraction"]["Hydrogen"]
    heat_duty_kw = float(objects["energy_stream"].HeatFlow.GetValue("kW"))
    metrics = {
        "co_yield_percent": co_yield_percent,
        "carbon_conversion_percent": carbon_conversion_percent,
        "syngas_hydrogen_molar_fraction": hydrogen_molar_fraction,
        "heat_duty_kw": heat_duty_kw,
    }
    if not all(math.isfinite(value) for value in metrics.values()):
        raise RuntimeError(f"A reported metric is non-finite: {metrics}")
    for label in ("co_yield_percent", "carbon_conversion_percent"):
        if not -BALANCE_TOLERANCE_PERCENT <= metrics[label] <= 100.0 + BALANCE_TOLERANCE_PERCENT:
            raise RuntimeError(f"{label} is outside the physical range: {metrics[label]}")

    print("SOLVED_OK")
    return {
        "reactor_type": "Gibbs Reactor",
        "reactor_name": REACTOR_NAME,
        "selection_reason": (
            "No reaction kinetics are specified; equilibrium products are obtained "
            "by Gibbs free-energy minimization"
        ),
        "converged": True,
        "conditions": {
            "slurry_mass_flow_kg_h": slurry_mass_flow_kg_h,
            "coal_mass_fraction": coal_mass_fraction,
            "water_mass_fraction": 1.0 - coal_mass_fraction,
            "feed_temperature_c": feed_temperature_c,
            "pressure_bar": pressure_bar,
            "outlet_temperature_c": outlet_temperature_c,
        },
        "feed": feed_result,
        "products": {
            "streams": product_results,
            "combined_component_molar_flow_kgmole_h": combined_molar_flows,
            "combined_component_mass_flow_kg_h": combined_mass_flows,
            "total_mass_flow_kg_h": total_product_mass,
        },
        **metrics,
        "mass_balance_error_percent": mass_balance_error_percent,
        "element_balance_error_percent": element_balance_error_percent,
        "assumptions": [
            "Coal is represented as pure carbon; ash, sulfur and nitrogen are omitted",
            "The ambiguous 80000 Nm3/h slurry rate is replaced by a 1000 kg/h mass basis",
            "No oxygen is fed; this is a steam-gasification approximation",
            "External heat maintains the specified 1400 C reactor outlet",
            "Equilibrium results require engineering review of phase settings and solid carbon",
        ],
    }


def run_with_retry(case: Any, **inputs: float) -> dict[str, Any]:
    deadline = time.monotonic() + RETRY_TIMEOUT_SECONDS
    attempt = 0
    last_error: Exception | None = None
    while True:
        attempt += 1
        try:
            result = configure_and_read_once(case, **inputs)
            print(f"RESULT_READ_OK: attempt={attempt}")
            return result
        except Exception as exc:
            last_error = exc
            remaining = deadline - time.monotonic()
            print(
                f"SOLVE_RETRY: attempt={attempt}, "
                f"remaining={max(remaining, 0.0):.1f}s, error={exc}"
            )
            if remaining <= 0.0:
                break
            pythoncom.PumpWaitingMessages()
            time.sleep(min(RETRY_INTERVAL_SECONDS, remaining))
    raise RuntimeError(
        f"HYSYS solve/result validation did not succeed within "
        f"{RETRY_TIMEOUT_SECONDS:.0f} seconds"
    ) from last_error


def run_coal_gasification_case(
    slurry_mass_flow_kg_h: float = 1000.0,
    coal_mass_fraction: float = 0.62,
    feed_temperature_c: float = 40.0,
    pressure_bar: float = 40.0,
    outlet_temperature_c: float = 1400.0,
) -> dict[str, Any]:
    validate_inputs(
        slurry_mass_flow_kg_h,
        coal_mass_fraction,
        feed_temperature_c,
        pressure_bar,
        outlet_temperature_c,
    )
    seed_hash = prepare_runtime_case()
    app = win32.Dispatch("HYSYS.Application")
    app.Visible = True
    case = app.SimulationCases.Open(str(RUNTIME_PATH))
    print("OPEN_CASE_OK:", case.name, RUNTIME_PATH)

    result = run_with_retry(
        case,
        slurry_mass_flow_kg_h=slurry_mass_flow_kg_h,
        coal_mass_fraction=coal_mass_fraction,
        feed_temperature_c=feed_temperature_c,
        pressure_bar=pressure_bar,
        outlet_temperature_c=outlet_temperature_c,
    )
    case.SaveAs(str(RUNTIME_PATH))
    if sha256(SEED_PATH) != seed_hash:
        raise RuntimeError("Coal seed changed during execution; refusing to report success")
    print("RUNTIME_CASE_SAVED_OK:", RUNTIME_PATH)
    case.Close()
    print("CLOSE_CASE_OK")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the fixed coal-slurry gasification HYSYS scenario"
    )
    parser.add_argument("--slurry-mass-flow-kg-h", type=float, default=1000.0)
    parser.add_argument("--coal-mass-fraction", type=float, default=0.62)
    parser.add_argument("--feed-temperature-c", type=float, default=40.0)
    parser.add_argument("--pressure-bar", type=float, default=40.0)
    parser.add_argument("--outlet-temperature-c", type=float, default=1400.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_coal_gasification_case(
        slurry_mass_flow_kg_h=args.slurry_mass_flow_kg_h,
        coal_mass_fraction=args.coal_mass_fraction,
        feed_temperature_c=args.feed_temperature_c,
        pressure_bar=args.pressure_bar,
        outlet_temperature_c=args.outlet_temperature_c,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("RUN_COAL_GASIFICATION_CASE_OK")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"RUN_COAL_GASIFICATION_CASE_FAILED: {type(exc).__name__}: {exc}")
        raise
