"""Create a runtime copy of the toluene seed and parameterize its feed.

This stage intentionally does not create or configure a Conversion Reactor.
"""

from __future__ import annotations

import hashlib
import shutil
import time
from pathlib import Path
from typing import Any, Iterable

import pythoncom
import win32com.client as win32


COMPONENT_NAMES = (
    "Toluene",
    "Benzene",
    "o-Xylene",
    "m-Xylene",
    "p-Xylene",
)
EXPECTED_COMPOSITION = (1.0, 0.0, 0.0, 0.0, 0.0)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SEED_PATH = PROJECT_ROOT / "cases" / "constant" / "toluene_seed.hsc"
RUNTIME_DIR = PROJECT_ROOT / "cases" / "runtime"
RUNTIME_PATH = RUNTIME_DIR / "toluene_run.hsc"

RETRY_TIMEOUT_SECONDS = 30.0
RETRY_INTERVAL_SECONDS = 1.0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_runtime_case() -> str:
    """Copy the immutable seed to the only writable runtime case path."""
    if not SEED_PATH.is_file():
        raise FileNotFoundError(f"种子模板不存在：{SEED_PATH}")
    if SEED_PATH.resolve() == RUNTIME_PATH.resolve():
        raise RuntimeError("种子模板与运行副本路径不能相同")

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    seed_hash = sha256(SEED_PATH)
    try:
        shutil.copy2(SEED_PATH, RUNTIME_PATH)
    except PermissionError as exc:
        raise RuntimeError(
            f"无法覆盖运行副本：{RUNTIME_PATH}。"
            "请确认该运行副本没有被 HYSYS 占用。"
        ) from exc

    if seed_hash != sha256(RUNTIME_PATH):
        raise RuntimeError("运行副本与种子模板的 SHA-256 不一致")

    print("RUNTIME_COPY_OK:", RUNTIME_PATH)
    return seed_hash


def collection_names(collection: Any) -> tuple[str, ...]:
    return tuple(str(collection.Item(index).name) for index in range(collection.Count))


def get_named_basis_objects(case: Any) -> tuple[Any, Any]:
    basis = case.BasisManager
    component_list = basis.ComponentLists.Item("AI Components")
    fluid_package = basis.FluidPackages.Item("AI Basis")

    component_names = collection_names(component_list.Components)
    if component_names != COMPONENT_NAMES:
        raise RuntimeError(
            "AI Components 的组分或顺序不符合预期："
            f"expected={COMPONENT_NAMES}, actual={component_names}"
        )
    if fluid_package.ComponentList.name != component_list.name:
        raise RuntimeError(
            "AI Basis 未绑定到 AI Components："
            f"actual={fluid_package.ComponentList.name!r}"
        )
    if fluid_package.PropertyPackageName != "Peng-Robinson":
        raise RuntimeError(
            "AI Basis 物性包不是 Peng-Robinson："
            f"actual={fluid_package.PropertyPackageName!r}"
        )

    return component_list, fluid_package


def get_existing_feed(case: Any) -> Any:
    streams = case.Flowsheet.MaterialStreams
    feed = streams.Item("Feed")

    if feed.name != "Feed":
        raise RuntimeError(f"取得的进料物流名称错误：{feed.name!r}")
    print("Using existing Feed")
    return feed


def set_molar_composition(stream: Any, values: Iterable[float]) -> None:
    values = tuple(values)
    variable = stream.ComponentMolarFraction

    try:
        variable.SetValues(values)
        return
    except Exception as first_error:
        try:
            variable.Values = values
            return
        except Exception as second_error:
            raise RuntimeError(
                "无法设置物流组成；"
                f"SetValues={first_error}; Values={second_error}"
            ) from second_error


def assert_close(label: str, actual: float, expected: float, tolerance: float) -> None:
    if abs(actual - expected) > tolerance:
        raise RuntimeError(
            f"{label} 回读校验失败：expected={expected}, actual={actual}, "
            f"tolerance={tolerance}"
        )


def validate_readback(case: Any, feed: Any) -> dict[str, Any]:
    temperature_c = float(feed.Temperature.GetValue("C"))
    pressure_bar = float(feed.Pressure.GetValue("bar"))
    mass_flow_kg_h = float(feed.MassFlow.GetValue("kg/h"))
    composition = tuple(float(value) for value in feed.ComponentMolarFraction.Values)
    can_solve = bool(case.Solver.CanSolve)

    assert_close("Temperature", temperature_c, 380.0, 0.01)
    assert_close("Pressure", pressure_bar, 25.0, 0.01)
    assert_close("MassFlow", mass_flow_kg_h, 10000.0, 0.1)

    if len(composition) != len(EXPECTED_COMPOSITION):
        raise RuntimeError(
            "Composition 长度校验失败："
            f"expected={len(EXPECTED_COMPOSITION)}, actual={len(composition)}"
        )
    for index, (actual, expected) in enumerate(
        zip(composition, EXPECTED_COMPOSITION, strict=True)
    ):
        assert_close(f"Composition[{index}]", actual, expected, 1e-8)
    assert_close("Composition sum", sum(composition), 1.0, 1e-8)

    if not can_solve:
        raise RuntimeError("Solver.CanSolve 回读为 False")

    return {
        "temperature_c": temperature_c,
        "pressure_bar": pressure_bar,
        "mass_flow_kg_h": mass_flow_kg_h,
        "composition": composition,
        "solver_can_solve": can_solve,
    }


def configure_and_validate_once(case: Any) -> dict[str, Any]:
    component_list, fluid_package = get_named_basis_objects(case)
    print(
        "Basis validated:",
        component_list.name,
        fluid_package.name,
        fluid_package.PropertyPackageName,
    )

    feed = get_existing_feed(case)
    solver = case.Solver
    solver.CanSolve = False

    feed.Temperature.SetValue(380.0, "C")
    feed.Pressure.SetValue(25.0, "bar")
    feed.MassFlow.SetValue(10000.0, "kg/h")
    set_molar_composition(feed, EXPECTED_COMPOSITION)

    solver.CanSolve = True
    return validate_readback(case, feed)


def configure_with_retry(case: Any) -> dict[str, Any]:
    deadline = time.monotonic() + RETRY_TIMEOUT_SECONDS
    attempt = 0
    last_error: Exception | None = None

    while True:
        attempt += 1
        try:
            result = configure_and_validate_once(case)
            print(f"WRITE_READBACK_OK: attempt={attempt}")
            return result
        except Exception as exc:
            last_error = exc
            remaining = deadline - time.monotonic()
            print(
                f"WRITE_READBACK_RETRY: attempt={attempt}, "
                f"remaining={max(remaining, 0.0):.1f}s, error={exc}"
            )
            if remaining <= 0:
                break

            pythoncom.PumpWaitingMessages()
            time.sleep(min(RETRY_INTERVAL_SECONDS, remaining))

    raise RuntimeError(
        f"在 {RETRY_TIMEOUT_SECONDS:.0f} 秒内无法完成进料写入及严格回读校验"
    ) from last_error


def main() -> None:
    seed_hash = prepare_runtime_case()

    app = win32.Dispatch("HYSYS.Application")
    app.Visible = True

    print("Opening runtime case:", RUNTIME_PATH)
    case = app.SimulationCases.Open(str(RUNTIME_PATH))
    print("OPEN_CASE_OK:", case.name, RUNTIME_PATH)

    result = configure_with_retry(case)

    # SaveAs is already verified against HYSYS V15 in this project. It writes only
    # the runtime copy; SEED_PATH is never passed to HYSYS.
    case.SaveAs(str(RUNTIME_PATH))
    if sha256(SEED_PATH) != seed_hash:
        raise RuntimeError("运行期间种子模板发生变化，拒绝报告成功")
    print("RUNTIME_CASE_SAVED_OK:", RUNTIME_PATH)
    print("Feed readback:", result)
    print("CREATE_TOLUENE_FEED_OK")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"CREATE_TOLUENE_FEED_FAILED: {type(exc).__name__}: {exc}")
        raise
