"""Read-only inspection of a coal gasification HYSYS case or probe copy."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path
from typing import Any, Iterable

import win32com.client as win32


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_CASE_PATH = (
    PROJECT_ROOT
    / "cases"
    / "coal_gasification_baseline"
    / "coal_gasification_baseline.hsc"
)
PROBE_CASE_PATH = PROJECT_ROOT / "cases" / "runtime" / "coal_gasification_probe.hsc"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_get(obj: Any, name: str) -> tuple[bool, Any]:
    try:
        return True, getattr(obj, name)
    except Exception as exc:
        return False, f"<{type(exc).__name__}: {exc}>"


def describe(value: Any) -> str:
    if value is None or isinstance(value, (str, int, float, bool)):
        return repr(value)
    if isinstance(value, (tuple, list)):
        return repr(value)
    fields = [f"python_type={type(value).__name__}"]
    for name in ("name", "TypeName", "VisibleTypeName"):
        ok, item = safe_get(value, name)
        if ok and isinstance(item, (str, int, float, bool)):
            fields.append(f"{name}={item!r}")
    return "<" + ", ".join(fields) + ">"


def collection_items(collection: Any) -> list[Any]:
    return [collection.Item(index) for index in range(int(collection.Count))]


def show_collection(label: str, collection: Any) -> list[Any]:
    print(f"\n===== {label} =====")
    items = collection_items(collection)
    print("Count:", len(items))
    for index, item in enumerate(items):
        print(f"[{index}] {describe(item)}")
    return items


def member_maps(obj: Any) -> tuple[set[str], set[str]]:
    members = {name for name in dir(obj) if not name.startswith("_")}
    writable: set[str] = set()
    ole = getattr(obj, "_olerepr_", None)
    if ole is not None:
        members.update(getattr(ole, "mapFuncs", {}).keys())
        members.update(getattr(ole, "propMap", {}).keys())
        writable.update(getattr(ole, "propMapPut", {}).keys())
    for owner in (obj, type(obj)):
        members.update(getattr(owner, "_prop_map_get_", {}).keys())
        writable.update(getattr(owner, "_prop_map_put_", {}).keys())
    return members, writable


def matching(names: Iterable[str], keywords: Iterable[str]) -> list[str]:
    lowered = tuple(keyword.lower() for keyword in keywords)
    return sorted(
        name for name in names if any(keyword in name.lower() for keyword in lowered)
    )


def show_metadata(label: str, obj: Any, keywords: tuple[str, ...]) -> None:
    members, writable = member_maps(obj)
    print(f"\n===== {label} RELEVANT MEMBERS =====")
    for name in matching(members, keywords):
        print(name)
    print(f"\n===== {label} WRITABLE PROPERTIES (METADATA ONLY) =====")
    for name in matching(writable, keywords):
        print(name)


def show_nested(label: str, obj: Any, property_name: str) -> None:
    print(f"\n===== {label}.{property_name} =====")
    ok, value = safe_get(obj, property_name)
    if not ok:
        print(value)
        return
    count_ok, count = safe_get(value, "Count")
    if count_ok:
        print("Count:", count)
        for index in range(int(count)):
            print(f"[{index}] {describe(value.Item(index))}")
    elif isinstance(value, (tuple, list)):
        for index, item in enumerate(value):
            print(f"[{index}] {describe(item)}")
    else:
        print(describe(value))


def read_scalar(stream: Any, property_name: str, unit: str) -> Any:
    ok, variable = safe_get(stream, property_name)
    if not ok:
        return variable
    try:
        return float(variable.GetValue(unit))
    except Exception as exc:
        return f"<{type(exc).__name__}: {exc}>"


def read_flex(stream: Any, property_name: str, unit: str | None = None) -> Any:
    ok, variable = safe_get(stream, property_name)
    if not ok:
        return variable
    if unit is not None:
        try:
            return tuple(float(value) for value in variable.GetValues(unit))
        except Exception:
            pass
    try:
        return tuple(float(value) for value in variable.Values)
    except Exception as exc:
        return f"<{type(exc).__name__}: {exc}>"


def show_stream(stream: Any) -> None:
    print(
        {
            "name": str(stream.name),
            "temperature_c": read_scalar(stream, "Temperature", "C"),
            "pressure_bar": read_scalar(stream, "Pressure", "bar"),
            "mass_flow_kg_h": read_scalar(stream, "MassFlow", "kg/h"),
            "molar_flow_kgmole_h": read_scalar(stream, "MolarFlow", "kgmole/h"),
            "molar_fraction": read_flex(stream, "ComponentMolarFraction"),
            "component_molar_flow_kgmole_h": read_flex(
                stream, "ComponentMolarFlow", "kgmole/h"
            ),
            "component_mass_flow_kg_h": read_flex(
                stream, "ComponentMassFlow", "kg/h"
            ),
        }
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--active",
        action="store_true",
        help="Inspect the already-open active case without opening any file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not SOURCE_CASE_PATH.is_file():
        raise FileNotFoundError(f"煤气化 baseline 不存在：{SOURCE_CASE_PATH}")
    original_hash = sha256(SOURCE_CASE_PATH)
    print("BASELINE_PATH:", SOURCE_CASE_PATH)
    print("BASELINE_SHA256_BEFORE:", original_hash)

    app = win32.Dispatch("HYSYS.Application")
    if args.active:
        case = app.ActiveDocument
        if case is None:
            raise RuntimeError("HYSYS 当前没有活动案例")
        print("USING_ACTIVE_CASE:", case.name)
    else:
        PROBE_CASE_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SOURCE_CASE_PATH, PROBE_CASE_PATH)
        if sha256(PROBE_CASE_PATH) != original_hash:
            raise RuntimeError("probe 与 baseline 的 SHA-256 不一致")
        print("PROBE_COPY_OK:", PROBE_CASE_PATH)
        app.Visible = True
        case = app.SimulationCases.Open(str(PROBE_CASE_PATH))
        print("OPEN_PROBE_COPY_OK:", case.name)

    basis = case.BasisManager
    flowsheet = case.Flowsheet
    reaction_manager = basis.ReactionPackageManager

    component_lists = show_collection("COMPONENT LISTS", basis.ComponentLists)
    for index, component_list in enumerate(component_lists):
        show_collection(f"COMPONENT LIST [{index}].COMPONENTS", component_list.Components)

    fluid_packages = show_collection("FLUID PACKAGES", basis.FluidPackages)
    for index, fluid_package in enumerate(fluid_packages):
        for name in ("ComponentList", "PropertyPackageName"):
            ok, value = safe_get(fluid_package, name)
            print(f"FLUID PACKAGE [{index}].{name}: {describe(value) if ok else value}")

    operations = show_collection("OPERATIONS", flowsheet.Operations)
    material_streams = show_collection("MATERIAL STREAMS", flowsheet.MaterialStreams)
    try:
        energy_streams = show_collection("ENERGY STREAMS", flowsheet.EnergyStreams)
    except Exception as exc:
        energy_streams = []
        print("ENERGY STREAMS unavailable:", exc)
    try:
        reactions = show_collection("REACTIONS", reaction_manager.Reactions)
        reaction_sets = show_collection("REACTION SETS", reaction_manager.ReactionSets)
    except Exception as exc:
        reactions = []
        reaction_sets = []
        print("REACTION COLLECTIONS unavailable:", exc)

    operation_keywords = (
        "feed",
        "product",
        "vapour",
        "vapor",
        "liquid",
        "solid",
        "energy",
        "heat",
        "gibbs",
        "equilibrium",
        "component",
        "temperature",
        "pressure",
        "solve",
        "status",
    )
    for index, operation in enumerate(operations):
        label = f"OPERATION [{index}] {operation.name} ({operation.TypeName})"
        show_metadata(label, operation, operation_keywords)
        for property_name in ("Feeds", "AttachedFeeds", "AttachedProducts"):
            show_nested(label, operation, property_name)
        for property_name in (
            "VapourProduct",
            "VaporProduct",
            "LiquidProduct",
            "SolidProduct",
            "EnergyStream",
            "ReactionSet",
            "HeatFlowValue",
            "PressureDropValue",
        ):
            ok, value = safe_get(operation, property_name)
            if ok:
                print(f"{label}.{property_name}: {describe(value)}")

    for index, reaction in enumerate(reactions):
        label = f"REACTION [{index}] {reaction.name} ({reaction.TypeName})"
        show_metadata(
            label,
            reaction,
            ("reactant", "component", "stoich", "coefficient", "conversion"),
        )
    for index, reaction_set in enumerate(reaction_sets):
        label = f"REACTION SET [{index}] {reaction_set.name}"
        show_nested(label, reaction_set, "ActiveReactions")
        show_nested(label, reaction_set, "InactiveReactions")

    print("\n===== SOLVER =====")
    print("Solver.CanSolve:", bool(case.Solver.CanSolve))

    print("\n===== MATERIAL STREAM RESULTS =====")
    for stream in material_streams:
        show_stream(stream)

    print("\n===== ENERGY STREAM RESULTS =====")
    for stream in energy_streams:
        print(
            {
                "name": str(stream.name),
                "heat_flow_kw": read_scalar(stream, "HeatFlow", "kW"),
                "heat_flow_kj_h": read_scalar(stream, "HeatFlow", "kJ/h"),
                "power_kw": read_scalar(stream, "Power", "kW"),
            }
        )

    final_hash = sha256(SOURCE_CASE_PATH)
    print("BASELINE_SHA256_AFTER:", final_hash)
    if final_hash != original_hash:
        raise RuntimeError("探查期间原始 coal baseline 发生变化")
    print("READ_ONLY_COAL_INSPECTION_OK")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"READ_ONLY_COAL_INSPECTION_FAILED: {type(exc).__name__}: {exc}")
        raise
