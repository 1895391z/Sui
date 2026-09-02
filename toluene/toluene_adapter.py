"""End-to-end adapter for the fixed HYSYS toluene conversion scenario."""

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


COMPONENT_NAMES = (
    "Toluene",
    "Benzene",
    "o-Xylene",
    "m-Xylene",
    "p-Xylene",
)
PURE_TOLUENE_COMPOSITION = (1.0, 0.0, 0.0, 0.0, 0.0)

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
SEED_PATH = REPOSITORY_ROOT / "cases" / "constant" / "toluene_reactor_seed.hsc"
RUNTIME_DIR = REPOSITORY_ROOT / "cases" / "runtime"
RUNTIME_PATH = RUNTIME_DIR / "toluene_reactor_run.hsc"

COMPONENT_LIST_NAME = "AI Components"
FLUID_PACKAGE_NAME = "AI Basis"
REACTOR_NAME = "CRV-100"
REACTION_NAME = "Rxn-1"
REACTION_SET_NAME = "RS-1"
FEED_NAME = "Feed"
PRODUCT_STREAM_NAMES = ("Vap_Prod", "Liq_Prod")

RETRY_TIMEOUT_SECONDS = 30.0
RETRY_INTERVAL_SECONDS = 1.0
MASS_BALANCE_TOLERANCE_PERCENT = 0.1


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_inputs(
    feed_mass_flow_kg_h: float,
    feed_temperature_c: float,
    pressure_bar: float,
    conversion: float,
    xylene_split: dict[str, float],
) -> None:
    values = {
        "feed_mass_flow_kg_h": feed_mass_flow_kg_h,
        "feed_temperature_c": feed_temperature_c,
        "pressure_bar": pressure_bar,
        "conversion": conversion,
    }
    for name, value in values.items():
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError(f"{name} 必须是有限数值，actual={value!r}")

    if feed_mass_flow_kg_h <= 0.0:
        raise ValueError("feed_mass_flow_kg_h 必须大于 0")
    if pressure_bar <= 0.0:
        raise ValueError("pressure_bar 必须大于 0")
    if not 0.0 <= conversion <= 1.0:
        raise ValueError("conversion 必须位于 [0, 1]，例如 50% 应传入 0.50")
    expected_keys = {"o_xylene", "m_xylene", "p_xylene"}
    if set(xylene_split) != expected_keys:
        raise ValueError(f"xylene_split 必须且只能包含 {sorted(expected_keys)}")
    if any(
        not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or value < 0.0
        for value in xylene_split.values()
    ):
        raise ValueError("xylene_split 必须包含三个非负有限数值")
    if not math.isclose(sum(xylene_split.values()), 1.0, abs_tol=1e-9):
        raise ValueError("xylene_split 三项之和必须为1")


def prepare_runtime_case() -> str:
    if not SEED_PATH.is_file():
        raise FileNotFoundError(f"甲苯反应器种子不存在：{SEED_PATH}")
    if SEED_PATH.resolve() == RUNTIME_PATH.resolve():
        raise RuntimeError("种子与运行副本路径不能相同")

    seed_hash = sha256(SEED_PATH)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(SEED_PATH, RUNTIME_PATH)
    except PermissionError as exc:
        raise RuntimeError(
            f"无法覆盖运行副本：{RUNTIME_PATH}。请确认它没有被 HYSYS 占用。"
        ) from exc

    if sha256(RUNTIME_PATH) != seed_hash:
        raise RuntimeError("运行副本与反应器种子的 SHA-256 不一致")
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
    component_names = collection_names(component_list.Components)

    if component_names != COMPONENT_NAMES:
        raise RuntimeError(
            f"组分或顺序错误：expected={COMPONENT_NAMES}, actual={component_names}"
        )
    if str(fluid_package.ComponentList.name) != COMPONENT_LIST_NAME:
        raise RuntimeError("AI Basis 未绑定到 AI Components")
    if str(fluid_package.PropertyPackageName) != "Peng-Robinson":
        raise RuntimeError(
            f"物性包错误：actual={fluid_package.PropertyPackageName!r}"
        )

    flowsheet = case.Flowsheet
    reactor = flowsheet.Operations.Item(REACTOR_NAME)
    reaction_manager = basis.ReactionPackageManager
    reaction = reaction_manager.Reactions.Item(REACTION_NAME)
    reaction_set = reaction_manager.ReactionSets.Item(REACTION_SET_NAME)
    feed = flowsheet.MaterialStreams.Item(FEED_NAME)
    products = {
        name: flowsheet.MaterialStreams.Item(name) for name in PRODUCT_STREAM_NAMES
    }

    expected_types = (
        ("reactor", reactor, "conversionreactorop"),
        ("reaction", reaction, "conversionrxn"),
        ("reaction_set", reaction_set, "rxnset"),
    )
    for label, obj, expected_type in expected_types:
        if str(obj.TypeName).lower() != expected_type:
            raise RuntimeError(
                f"{label} TypeName 错误：expected={expected_type}, actual={obj.TypeName}"
            )

    if str(reactor.ReactionSet.name) != REACTION_SET_NAME:
        raise RuntimeError(
            f"反应器未绑定 {REACTION_SET_NAME}：actual={reactor.ReactionSet.name!r}"
        )
    active_reactions = collection_names(reaction_set.ActiveReactions)
    if REACTION_NAME not in active_reactions:
        raise RuntimeError(
            f"{REACTION_NAME} 不是活动反应：actual={active_reactions}"
        )
    if str(reaction.BaseComponent.name) != "Toluene":
        raise RuntimeError(
            f"反应基准组分不是 Toluene：actual={reaction.BaseComponent.name!r}"
        )

    print("VALIDATE_MODEL_OK")
    return {
        "component_list": component_list,
        "reactor": reactor,
        "reaction": reaction,
        "reaction_set": reaction_set,
        "feed": feed,
        "products": products,
    }


def configure_inputs_once(
    case: Any,
    objects: dict[str, Any],
    feed_mass_flow_kg_h: float,
    feed_temperature_c: float,
    pressure_bar: float,
    conversion: float,
) -> None:
    solver = case.Solver
    feed = objects["feed"]
    reaction = objects["reaction"]

    solver.CanSolve = False
    feed.Temperature.SetValue(feed_temperature_c, "C")
    feed.Pressure.SetValue(pressure_bar, "bar")
    feed.MassFlow.SetValue(feed_mass_flow_kg_h, "kg/h")
    set_flex_values(feed.ComponentMolarFraction, PURE_TOLUENE_COMPOSITION)
    reaction.Conversion = conversion * 100.0
    solver.CanSolve = True


def read_flex_values(variable: Any, unit: str | None = None) -> tuple[float, ...]:
    if unit is not None:
        try:
            return tuple(float(value) for value in variable.GetValues(unit))
        except Exception:
            pass
    return tuple(float(value) for value in variable.Values)


def ensure_finite_vector(label: str, values: tuple[float, ...]) -> None:
    if len(values) != len(COMPONENT_NAMES):
        raise RuntimeError(
            f"{label} 长度错误：expected={len(COMPONENT_NAMES)}, actual={len(values)}"
        )
    if not all(math.isfinite(value) for value in values):
        raise RuntimeError(f"{label} 包含非有限结果：{values}")


def read_stream(stream: Any) -> dict[str, Any]:
    mass_flow = float(stream.MassFlow.GetValue("kg/h"))
    temperature = float(stream.Temperature.GetValue("C"))
    pressure = float(stream.Pressure.GetValue("bar"))
    molar_fraction = read_flex_values(stream.ComponentMolarFraction)
    component_mass_flow = read_flex_values(stream.ComponentMassFlow, "kg/h")

    ensure_finite_vector(f"{stream.name}.ComponentMolarFraction", molar_fraction)
    ensure_finite_vector(f"{stream.name}.ComponentMassFlow", component_mass_flow)
    for label, value in (
        ("MassFlow", mass_flow),
        ("Temperature", temperature),
        ("Pressure", pressure),
    ):
        if not math.isfinite(value):
            raise RuntimeError(f"{stream.name}.{label} 不是有限结果：{value}")

    return {
        "name": str(stream.name),
        "temperature_c": temperature,
        "pressure_bar": pressure,
        "mass_flow_kg_h": mass_flow,
        "component_molar_fraction": dict(zip(COMPONENT_NAMES, molar_fraction, strict=True)),
        "component_mass_flow_kg_h": dict(
            zip(COMPONENT_NAMES, component_mass_flow, strict=True)
        ),
    }


def configure_and_read_result(
    case: Any,
    objects: dict[str, Any],
    feed_mass_flow_kg_h: float,
    feed_temperature_c: float,
    pressure_bar: float,
    conversion: float,
    xylene_split: dict[str, float],
) -> dict[str, Any]:
    configure_inputs_once(
        case,
        objects,
        feed_mass_flow_kg_h,
        feed_temperature_c,
        pressure_bar,
        conversion,
    )
    print("WRITE_INPUT_OK")

    feed_result = read_stream(objects["feed"])
    product_results = {
        name: read_stream(stream) for name, stream in objects["products"].items()
    }
    conversion_percent = float(objects["reaction"].Conversion)
    can_solve = bool(case.Solver.CanSolve)

    assert_close("Feed temperature", feed_result["temperature_c"], feed_temperature_c, 0.01)
    assert_close("Feed pressure", feed_result["pressure_bar"], pressure_bar, 0.01)
    assert_close("Feed mass flow", feed_result["mass_flow_kg_h"], feed_mass_flow_kg_h, 0.1)
    assert_close("Reaction conversion", conversion_percent, conversion * 100.0, 1e-8)
    for index, expected in enumerate(PURE_TOLUENE_COMPOSITION):
        actual = tuple(feed_result["component_molar_fraction"].values())[index]
        assert_close(f"Feed composition[{index}]", actual, expected, 1e-8)
    if not can_solve:
        raise RuntimeError("Solver.CanSolve 为 False")

    combined_component_flows = {
        component: sum(
            stream["component_mass_flow_kg_h"][component]
            for stream in product_results.values()
        )
        for component in COMPONENT_NAMES
    }
    total_xylene_mass_flow = combined_component_flows["p-Xylene"]
    derived_xylene_mass_flows = {
        name: total_xylene_mass_flow * fraction
        for name, fraction in xylene_split.items()
    }
    total_product_mass = sum(
        stream["mass_flow_kg_h"] for stream in product_results.values()
    )
    mass_balance_error_percent = (
        abs(total_product_mass - feed_mass_flow_kg_h)
        / feed_mass_flow_kg_h
        * 100.0
    )
    if mass_balance_error_percent >= MASS_BALANCE_TOLERANCE_PERCENT:
        raise RuntimeError(
            "质量衡算误差超限："
            f"actual={mass_balance_error_percent}%, "
            f"limit={MASS_BALANCE_TOLERANCE_PERCENT}%"
        )

    print("SOLVED_OK")
    return {
        "reactor_type": "Conversion Reactor",
        "reactor_name": REACTOR_NAME,
        "selection_reason": "已知甲苯转化率且不要求动力学",
        "converged": True,
        "conversion_fraction": conversion,
        "conversion_percent": conversion_percent,
        "feed": feed_result,
        "products": {
            "streams": product_results,
            "combined_component_mass_flow_kg_h": combined_component_flows,
            "total_mass_flow_kg_h": total_product_mass,
            "xylene_isomer_distribution": {
                "derived_from_assumed_selectivity": True,
                "basis": "HYSYS p-Xylene component interpreted as total xylene",
                "split_fraction": dict(xylene_split),
                "mass_flow_kg_h": derived_xylene_mass_flows,
            },
        },
        "mass_balance_error_percent": mass_balance_error_percent,
        "assumptions": [
            "HYSYS 仍以 p-Xylene 代表总二甲苯；o/m/p 分布由选择性假设推导，并非原生组分结果",
            "输入 conversion 使用 0 到 1 的比例，写入 HYSYS 时转换为百分数",
        ],
    }


def run_with_retry(
    case: Any,
    objects: dict[str, Any],
    feed_mass_flow_kg_h: float,
    feed_temperature_c: float,
    pressure_bar: float,
    conversion: float,
    xylene_split: dict[str, float],
) -> dict[str, Any]:
    deadline = time.monotonic() + RETRY_TIMEOUT_SECONDS
    attempt = 0
    last_error: Exception | None = None

    while True:
        attempt += 1
        try:
            result = configure_and_read_result(
                case,
                objects,
                feed_mass_flow_kg_h,
                feed_temperature_c,
                pressure_bar,
                conversion,
                xylene_split,
            )
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


def run_toluene_case(
    feed_mass_flow_kg_h: float = 10000.0,
    feed_temperature_c: float = 380.0,
    pressure_bar: float = 25.0,
    conversion: float = 0.50,
    xylene_split: dict[str, float] | None = None,
) -> dict[str, Any]:
    if xylene_split is None:
        xylene_split = {
            "o_xylene": 1.0 / 3.0,
            "m_xylene": 1.0 / 3.0,
            "p_xylene": 1.0 / 3.0,
        }
    validate_inputs(
        feed_mass_flow_kg_h,
        feed_temperature_c,
        pressure_bar,
        conversion,
        xylene_split,
    )
    seed_hash = prepare_runtime_case()

    app = win32.Dispatch("HYSYS.Application")
    app.Visible = True
    case = app.SimulationCases.Open(str(RUNTIME_PATH))
    print("OPEN_CASE_OK:", case.name, RUNTIME_PATH)

    objects = get_model_objects(case)
    result = run_with_retry(
        case,
        objects,
        feed_mass_flow_kg_h,
        feed_temperature_c,
        pressure_bar,
        conversion,
        xylene_split,
    )

    case.SaveAs(str(RUNTIME_PATH))
    if sha256(SEED_PATH) != seed_hash:
        raise RuntimeError("运行期间反应器种子发生变化，拒绝报告成功")
    print("RUNTIME_CASE_SAVED_OK:", RUNTIME_PATH)
    case.Close()
    print("CLOSE_CASE_OK")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行甲苯歧化 HYSYS 固定场景")
    parser.add_argument("--feed-mass-flow-kg-h", type=float, default=10000.0)
    parser.add_argument("--feed-temperature-c", type=float, default=380.0)
    parser.add_argument("--pressure-bar", type=float, default=25.0)
    parser.add_argument("--conversion", type=float, default=0.50)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_toluene_case(
        feed_mass_flow_kg_h=args.feed_mass_flow_kg_h,
        feed_temperature_c=args.feed_temperature_c,
        pressure_bar=args.pressure_bar,
        conversion=args.conversion,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("RUN_TOLUENE_CASE_OK")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"RUN_TOLUENE_CASE_FAILED: {type(exc).__name__}: {exc}")
        raise
