"""End-to-end HYSYS adapter for the fixed methane steam reforming scenario."""

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


COMPONENT_NAMES = ("Methane", "H2O", "CO", "CO2", "Hydrogen")
ELEMENT_COUNTS = {
    "Methane": {"C": 1.0, "H": 4.0, "O": 0.0},
    "H2O": {"C": 0.0, "H": 2.0, "O": 1.0},
    "CO": {"C": 1.0, "H": 0.0, "O": 1.0},
    "CO2": {"C": 1.0, "H": 0.0, "O": 2.0},
    "Hydrogen": {"C": 0.0, "H": 2.0, "O": 0.0},
}

SUI_ROOT = Path(__file__).resolve().parents[2]
SEED_PATH = SUI_ROOT / "cases" / "constant" / "methane_reforming_seed.hsc"
RUNTIME_DIR = SUI_ROOT / "cases" / "runtime"
RUNTIME_PATH = RUNTIME_DIR / "methane_reforming_run.hsc"

COMPONENT_LIST_NAME = "Component List - 1"
FLUID_PACKAGE_NAME = "Basis-1"
REACTOR_NAME = "ERV-100"
REACTION_NAMES = ("Rxn-1", "Rxn-2")
REACTION_SET_NAME = "Set-1"
FEED_NAME = "Feed"
VAPOUR_PRODUCT_NAME = "Vap_Prod"
LIQUID_PRODUCT_NAME = "liq_Prod"
ENERGY_STREAM_NAME = "Q_Reformer"

EXPECTED_STOICHIOMETRY = {
    "Rxn-1": (-1.0, -1.0, 3.0, 1.0),
    "Rxn-2": (-1.0, -1.0, 1.0, 1.0),
}

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
    total_feed_molar_flow_kgmole_h: float,
    steam_to_carbon_ratio: float,
    feed_temperature_c: float,
    pressure_bar: float,
    outlet_temperature_c: float,
) -> None:
    values = {
        "total_feed_molar_flow_kgmole_h": total_feed_molar_flow_kgmole_h,
        "steam_to_carbon_ratio": steam_to_carbon_ratio,
        "feed_temperature_c": feed_temperature_c,
        "pressure_bar": pressure_bar,
        "outlet_temperature_c": outlet_temperature_c,
    }
    for name, value in values.items():
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError(f"{name} 必须是有限数值，actual={value!r}")

    if total_feed_molar_flow_kgmole_h <= 0.0:
        raise ValueError("total_feed_molar_flow_kgmole_h 必须大于 0")
    if steam_to_carbon_ratio <= 0.0:
        raise ValueError("steam_to_carbon_ratio 必须大于 0")
    if pressure_bar <= 0.0:
        raise ValueError("pressure_bar 必须大于 0")
    if feed_temperature_c <= -273.15 or outlet_temperature_c <= -273.15:
        raise ValueError("温度必须高于绝对零度")


def feed_composition(steam_to_carbon_ratio: float) -> tuple[float, ...]:
    methane_fraction = 1.0 / (1.0 + steam_to_carbon_ratio)
    water_fraction = steam_to_carbon_ratio / (1.0 + steam_to_carbon_ratio)
    return (methane_fraction, water_fraction, 0.0, 0.0, 0.0)


def prepare_runtime_case() -> str:
    if not SEED_PATH.is_file():
        raise FileNotFoundError(f"甲烷重整 seed 不存在：{SEED_PATH}")
    if SEED_PATH.resolve() == RUNTIME_PATH.resolve():
        raise RuntimeError("seed 与 runtime 路径不能相同")

    seed_hash = sha256(SEED_PATH)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(SEED_PATH, RUNTIME_PATH)
    except PermissionError as exc:
        raise RuntimeError(
            f"无法覆盖 runtime：{RUNTIME_PATH}。请确认它没有被 HYSYS 占用。"
        ) from exc
    if sha256(RUNTIME_PATH) != seed_hash:
        raise RuntimeError("runtime 与 seed 的 SHA-256 不一致")
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
                f"FlexVariable 写入失败：SetValues={first_error}; Values={second_error}"
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
            f"{label} 校验失败：expected={expected}, actual={actual}, "
            f"tolerance={tolerance}"
        )


def get_model_objects(case: Any) -> dict[str, Any]:
    basis = case.BasisManager
    component_list = basis.ComponentLists.Item(COMPONENT_LIST_NAME)
    fluid_package = basis.FluidPackages.Item(FLUID_PACKAGE_NAME)
    components = collection_names(component_list.Components)
    if components != COMPONENT_NAMES:
        raise RuntimeError(
            f"组分或顺序错误：expected={COMPONENT_NAMES}, actual={components}"
        )
    if str(fluid_package.ComponentList.name) != COMPONENT_LIST_NAME:
        raise RuntimeError("物性包未绑定预期 Component List")
    if str(fluid_package.PropertyPackageName) != "Peng-Robinson":
        raise RuntimeError(
            f"物性包错误：actual={fluid_package.PropertyPackageName!r}"
        )

    flowsheet = case.Flowsheet
    reactor = flowsheet.Operations.Item(REACTOR_NAME)
    reaction_manager = basis.ReactionPackageManager
    reactions = {
        name: reaction_manager.Reactions.Item(name) for name in REACTION_NAMES
    }
    reaction_set = reaction_manager.ReactionSets.Item(REACTION_SET_NAME)
    feed = flowsheet.MaterialStreams.Item(FEED_NAME)
    vapour_product = flowsheet.MaterialStreams.Item(VAPOUR_PRODUCT_NAME)
    liquid_product = flowsheet.MaterialStreams.Item(LIQUID_PRODUCT_NAME)
    energy_stream = flowsheet.EnergyStreams.Item(ENERGY_STREAM_NAME)

    if str(reactor.TypeName).lower() != "equilibriumreactorop":
        raise RuntimeError(f"反应器 TypeName 错误：{reactor.TypeName!r}")
    if str(reaction_set.TypeName).lower() != "rxnset":
        raise RuntimeError(f"Reaction Set TypeName 错误：{reaction_set.TypeName!r}")
    if str(reactor.ReactionSet.name) != REACTION_SET_NAME:
        raise RuntimeError("反应器没有绑定 Set-1")
    if collection_names(reaction_set.ActiveReactions) != REACTION_NAMES:
        raise RuntimeError(
            "活动反应不符合预期："
            f"actual={collection_names(reaction_set.ActiveReactions)}"
        )

    for name, reaction in reactions.items():
        if str(reaction.TypeName).lower() != "equilibriumrxn":
            raise RuntimeError(f"{name} TypeName 错误：{reaction.TypeName!r}")
        actual_stoichiometry = tuple(float(value) for value in reaction.ReactantStoichCoefValue)
        if actual_stoichiometry != EXPECTED_STOICHIOMETRY[name]:
            raise RuntimeError(
                f"{name} 化学计量错误：expected={EXPECTED_STOICHIOMETRY[name]}, "
                f"actual={actual_stoichiometry}"
            )

    connection_names = {
        "feed": collection_names(reactor.Feeds),
        "vapour_product": str(reactor.VapourProduct.name),
        "liquid_product": str(reactor.LiquidProduct.name),
        "energy_stream": str(reactor.EnergyStream.name),
    }
    expected_connections = {
        "feed": (FEED_NAME,),
        "vapour_product": VAPOUR_PRODUCT_NAME,
        "liquid_product": LIQUID_PRODUCT_NAME,
        "energy_stream": ENERGY_STREAM_NAME,
    }
    if connection_names != expected_connections:
        raise RuntimeError(
            f"反应器连接错误：expected={expected_connections}, actual={connection_names}"
        )

    print("VALIDATE_MODEL_OK")
    return {
        "reactor": reactor,
        "reactions": reactions,
        "reaction_set": reaction_set,
        "feed": feed,
        "vapour_product": vapour_product,
        "liquid_product": liquid_product,
        "energy_stream": energy_stream,
    }


def read_stream(stream: Any) -> dict[str, Any]:
    molar_fraction = read_flex_values(stream.ComponentMolarFraction)
    component_molar_flow = read_flex_values(stream.ComponentMolarFlow, "kgmole/h")
    component_mass_flow = read_flex_values(stream.ComponentMassFlow, "kg/h")
    for label, values in (
        ("ComponentMolarFraction", molar_fraction),
        ("ComponentMolarFlow", component_molar_flow),
        ("ComponentMassFlow", component_mass_flow),
    ):
        if len(values) != len(COMPONENT_NAMES) or not all(
            math.isfinite(value) for value in values
        ):
            raise RuntimeError(f"{stream.name}.{label} 结果无效：{values}")

    result = {
        "name": str(stream.name),
        "temperature_c": float(stream.Temperature.GetValue("C")),
        "pressure_bar": float(stream.Pressure.GetValue("bar")),
        "mass_flow_kg_h": float(stream.MassFlow.GetValue("kg/h")),
        "molar_flow_kgmole_h": float(stream.MolarFlow.GetValue("kgmole/h")),
        "component_molar_fraction": dict(
            zip(COMPONENT_NAMES, molar_fraction, strict=True)
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
        raise RuntimeError(f"{stream.name} 包含非有限标量结果：{result}")
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
    return {
        element: abs(product_elements[element] - feed_elements[element])
        / feed_elements[element]
        * 100.0
        for element in feed_elements
    }


def configure_and_read_once(
    case: Any,
    total_feed_molar_flow_kgmole_h: float,
    steam_to_carbon_ratio: float,
    feed_temperature_c: float,
    pressure_bar: float,
    outlet_temperature_c: float,
) -> dict[str, Any]:
    objects = get_model_objects(case)
    feed = objects["feed"]
    vapour_product = objects["vapour_product"]
    liquid_product = objects["liquid_product"]
    expected_composition = feed_composition(steam_to_carbon_ratio)

    solver = case.Solver
    solver.CanSolve = False
    feed.Temperature.SetValue(feed_temperature_c, "C")
    feed.Pressure.SetValue(pressure_bar, "bar")
    feed.MolarFlow.SetValue(total_feed_molar_flow_kgmole_h, "kgmole/h")
    set_flex_values(feed.ComponentMolarFraction, expected_composition)
    vapour_product.Temperature.SetValue(outlet_temperature_c, "C")
    solver.CanSolve = True
    print("WRITE_INPUT_OK")

    feed_result = read_stream(feed)
    vapour_result = read_stream(vapour_product)
    liquid_result = read_stream(liquid_product)
    product_results = {
        VAPOUR_PRODUCT_NAME: vapour_result,
        LIQUID_PRODUCT_NAME: liquid_result,
    }

    assert_close(
        "Feed molar flow",
        feed_result["molar_flow_kgmole_h"],
        total_feed_molar_flow_kgmole_h,
        1e-6,
    )
    assert_close("Feed temperature", feed_result["temperature_c"], feed_temperature_c, 0.01)
    assert_close("Feed pressure", feed_result["pressure_bar"], pressure_bar, 0.01)
    assert_close(
        "Outlet temperature",
        vapour_result["temperature_c"],
        outlet_temperature_c,
        0.01,
    )
    for index, expected in enumerate(expected_composition):
        actual = tuple(feed_result["component_molar_fraction"].values())[index]
        assert_close(f"Feed composition[{index}]", actual, expected, 1e-8)
    if not bool(case.Solver.CanSolve):
        raise RuntimeError("Solver.CanSolve 为 False")

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
        feed_result["component_molar_flow_kgmole_h"],
        combined_molar_flows,
    )
    if mass_balance_error_percent >= BALANCE_TOLERANCE_PERCENT:
        raise RuntimeError(
            f"质量衡算误差超限：{mass_balance_error_percent}%"
        )
    failed_elements = {
        element: error
        for element, error in element_balance_error_percent.items()
        if error >= BALANCE_TOLERANCE_PERCENT
    }
    if failed_elements:
        raise RuntimeError(f"元素衡算误差超限：{failed_elements}")

    feed_methane = feed_result["component_molar_flow_kgmole_h"]["Methane"]
    product_methane = combined_molar_flows["Methane"]
    methane_conversion_percent = (feed_methane - product_methane) / feed_methane * 100.0
    heat_duty_kw = float(objects["energy_stream"].HeatFlow.GetValue("kW"))
    if not math.isfinite(methane_conversion_percent) or not math.isfinite(heat_duty_kw):
        raise RuntimeError("甲烷转化率或热负荷不是有限结果")

    print("SOLVED_OK")
    return {
        "reactor_type": "Equilibrium Reactor",
        "reactor_name": REACTOR_NAME,
        "selection_reason": "无动力学参数，反应可逆并受热力学平衡控制",
        "converged": True,
        "conditions": {
            "total_feed_molar_flow_kgmole_h": total_feed_molar_flow_kgmole_h,
            "steam_to_carbon_ratio": steam_to_carbon_ratio,
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
        "methane_conversion_percent": methane_conversion_percent,
        "heat_duty_kw": heat_duty_kw,
        "mass_balance_error_percent": mass_balance_error_percent,
        "element_balance_error_percent": element_balance_error_percent,
        "assumptions": [
            "题目未给定总进料流量，默认采用总进料 100 kgmol/h",
            "蒸汽碳比按进料 H2O/CH4 摩尔比定义",
            "指定出口温度，热负荷由 HYSYS 计算",
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
        f"在 {RETRY_TIMEOUT_SECONDS:.0f} 秒内无法完成求解及结果校验"
    ) from last_error


def run_methane_reforming_case(
    total_feed_molar_flow_kgmole_h: float = 100.0,
    steam_to_carbon_ratio: float = 2.7,
    feed_temperature_c: float = 520.0,
    pressure_bar: float = 13.5,
    outlet_temperature_c: float = 600.0,
) -> dict[str, Any]:
    validate_inputs(
        total_feed_molar_flow_kgmole_h,
        steam_to_carbon_ratio,
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
        total_feed_molar_flow_kgmole_h=total_feed_molar_flow_kgmole_h,
        steam_to_carbon_ratio=steam_to_carbon_ratio,
        feed_temperature_c=feed_temperature_c,
        pressure_bar=pressure_bar,
        outlet_temperature_c=outlet_temperature_c,
    )
    case.SaveAs(str(RUNTIME_PATH))
    if sha256(SEED_PATH) != seed_hash:
        raise RuntimeError("运行期间 methane seed 发生变化，拒绝报告成功")
    print("RUNTIME_CASE_SAVED_OK:", RUNTIME_PATH)
    case.Close()
    print("CLOSE_CASE_OK")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行甲烷蒸汽重整 HYSYS 固定场景")
    parser.add_argument("--total-feed-molar-flow-kgmole-h", type=float, default=100.0)
    parser.add_argument("--steam-to-carbon-ratio", type=float, default=2.7)
    parser.add_argument("--feed-temperature-c", type=float, default=520.0)
    parser.add_argument("--pressure-bar", type=float, default=13.5)
    parser.add_argument("--outlet-temperature-c", type=float, default=600.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_methane_reforming_case(
        total_feed_molar_flow_kgmole_h=args.total_feed_molar_flow_kgmole_h,
        steam_to_carbon_ratio=args.steam_to_carbon_ratio,
        feed_temperature_c=args.feed_temperature_c,
        pressure_bar=args.pressure_bar,
        outlet_temperature_c=args.outlet_temperature_c,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("RUN_METHANE_REFORMING_CASE_OK")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"RUN_METHANE_REFORMING_CASE_FAILED: {type(exc).__name__}: {exc}")
        raise
