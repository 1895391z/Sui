"""Read-only COM inspection of the methane reforming HYSYS baseline copy."""

from __future__ import annotations

import hashlib
import inspect
import math
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
    / "methane_reforming_baseline"
    / "methane_reforming_baseline.hsc"
)
PROBE_CASE_PATH = PROJECT_ROOT / "cases" / "runtime" / "methane_reforming_probe.hsc"


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


def member_maps(obj: Any) -> tuple[set[str], set[str], set[str]]:
    members = {name for name in dir(obj) if not name.startswith("_")}
    readable: set[str] = set()
    writable: set[str] = set()

    ole = getattr(obj, "_olerepr_", None)
    if ole is not None:
        members.update(getattr(ole, "mapFuncs", {}).keys())
        readable.update(getattr(ole, "propMap", {}).keys())
        writable.update(getattr(ole, "propMapPut", {}).keys())
    for owner in (obj, type(obj)):
        readable.update(getattr(owner, "_prop_map_get_", {}).keys())
        writable.update(getattr(owner, "_prop_map_put_", {}).keys())
    return members, readable, writable


def matching(names: Iterable[str], keywords: Iterable[str]) -> list[str]:
    keywords_lower = tuple(keyword.lower() for keyword in keywords)
    return sorted(
        name
        for name in names
        if any(keyword in name.lower() for keyword in keywords_lower)
    )


def show_identity(label: str, obj: Any) -> None:
    print(f"\n===== {label} IDENTITY =====")
    for name in ("name", "TypeName", "VisibleTypeName"):
        ok, value = safe_get(obj, name)
        print(f"{name}: {describe(value) if ok else value}")


def show_collection(label: str, collection: Any) -> list[Any]:
    print(f"\n===== {label} ITEMS =====")
    items = [collection.Item(index) for index in range(int(collection.Count))]
    print("Count:", len(items))
    for index, item in enumerate(items):
        print(f"[{index}] {describe(item)}")
    return items


def show_method(label: str, obj: Any, method_name: str = "Add") -> None:
    print(f"\n===== {label}.{method_name} SIGNATURE =====")
    ok, method = safe_get(obj, method_name)
    if not ok:
        print(method)
        return
    try:
        print("Signature:", inspect.signature(method))
    except Exception as exc:
        print("Signature unavailable:", exc)
    print("Doc:", getattr(method, "__doc__", None))


def show_metadata(label: str, obj: Any, keywords: tuple[str, ...]) -> None:
    members, readable, writable = member_maps(obj)
    print(f"\n===== {label} RELEVANT MEMBERS =====")
    for name in matching(members, keywords):
        print(name)
    print(f"\n===== {label} WRITABLE PROPERTIES (METADATA ONLY) =====")
    for name in matching(writable, keywords):
        print(name)
    print(f"\n===== {label} SELECTED READ-ONLY VALUES =====")
    for name in matching(readable | members, keywords):
        ok, value = safe_get(obj, name)
        if ok and not callable(value):
            print(f"{name}: {describe(value)}")


def show_nested_collection(label: str, obj: Any, property_name: str) -> None:
    ok, value = safe_get(obj, property_name)
    print(f"\n===== {label}.{property_name} =====")
    if not ok:
        print(value)
        return
    count_ok, count = safe_get(value, "Count")
    if count_ok:
        print("Count:", count)
        for index in range(int(count)):
            item = value.Item(index)
            details = [describe(item)]
            component_ok, component = safe_get(item, "Component")
            if component_ok:
                details.append(f"Component={describe(component)}")
            coefficient_ok, coefficient = safe_get(item, "StoichiometricCoefficient")
            if coefficient_ok:
                try:
                    coefficient_value = float(coefficient.GetValue(""))
                except Exception:
                    coefficient_value = getattr(coefficient, "Value", "<unavailable>")
                details.append(f"StoichiometricCoefficient={coefficient_value!r}")
            print(f"[{index}] " + ", ".join(details))
    elif isinstance(value, (tuple, list)):
        for index, item in enumerate(value):
            print(f"[{index}] {describe(item)}")
    else:
        print(describe(value))


def read_scalar(obj: Any, property_name: str, unit: str) -> Any:
    ok, variable = safe_get(obj, property_name)
    if not ok:
        return variable
    try:
        return float(variable.GetValue(unit))
    except Exception as exc:
        return f"<{type(exc).__name__}: {exc}>"


def read_flex(obj: Any, property_name: str, unit: str | None = None) -> Any:
    ok, variable = safe_get(obj, property_name)
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


def show_stream_result(stream: Any) -> None:
    result = {
        "name": str(stream.name),
        "temperature_c": read_scalar(stream, "Temperature", "C"),
        "pressure_bar": read_scalar(stream, "Pressure", "bar"),
        "mass_flow_kg_h": read_scalar(stream, "MassFlow", "kg/h"),
        "molar_flow_kgmole_h": read_scalar(stream, "MolarFlow", "kgmole/h"),
        "molar_fraction": read_flex(stream, "ComponentMolarFraction"),
        "component_molar_flow_kgmole_h": read_flex(
            stream, "ComponentMolarFlow", "kgmole/h"
        ),
        "component_mass_flow_kg_h": read_flex(stream, "ComponentMassFlow", "kg/h"),
    }
    print(result)


def main() -> None:
    if not SOURCE_CASE_PATH.is_file():
        raise FileNotFoundError(f"甲烷重整手工基准不存在：{SOURCE_CASE_PATH}")

    source_hash = sha256(SOURCE_CASE_PATH)
    print("BASELINE_PATH:", SOURCE_CASE_PATH)
    print("BASELINE_SHA256_BEFORE:", source_hash)

    PROBE_CASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE_CASE_PATH, PROBE_CASE_PATH)
    if sha256(PROBE_CASE_PATH) != source_hash:
        raise RuntimeError("probe 副本与 baseline 的 SHA-256 不一致")
    print("PROBE_COPY_OK:", PROBE_CASE_PATH)

    app = win32.Dispatch("HYSYS.Application")
    app.Visible = True
    case = app.SimulationCases.Open(str(PROBE_CASE_PATH))
    print("OPEN_PROBE_COPY_OK:", case.name)

    basis = case.BasisManager
    flowsheet = case.Flowsheet
    reaction_manager = basis.ReactionPackageManager

    component_lists = show_collection("COMPONENT LISTS", basis.ComponentLists)
    for index, component_list in enumerate(component_lists):
        show_identity(f"COMPONENT LIST [{index}]", component_list)
        show_collection(f"COMPONENT LIST [{index}].COMPONENTS", component_list.Components)

    fluid_packages = show_collection("FLUID PACKAGES", basis.FluidPackages)
    for index, fluid_package in enumerate(fluid_packages):
        show_identity(f"FLUID PACKAGE [{index}]", fluid_package)
        for name in ("ComponentList", "PropertyPackageName"):
            ok, value = safe_get(fluid_package, name)
            print(f"{name}: {describe(value) if ok else value}")

    operations = show_collection("OPERATIONS", flowsheet.Operations)
    reactions = show_collection("REACTIONS", reaction_manager.Reactions)
    reaction_sets = show_collection("REACTION SETS", reaction_manager.ReactionSets)
    material_streams = show_collection("MATERIAL STREAMS", flowsheet.MaterialStreams)
    try:
        energy_streams = show_collection("ENERGY STREAMS", flowsheet.EnergyStreams)
    except Exception as exc:
        energy_streams = []
        print("ENERGY STREAMS unavailable:", exc)

    show_method("Operations", flowsheet.Operations)
    show_method("Reactions", reaction_manager.Reactions)
    show_method("ReactionSets", reaction_manager.ReactionSets)

    reactor_keywords = (
        "reaction",
        "feed",
        "product",
        "inlet",
        "outlet",
        "energy",
        "heat",
        "temperature",
        "pressure",
        "solve",
        "status",
    )
    for index, operation in enumerate(operations):
        label = f"OPERATION [{index}] {operation.name}"
        show_identity(label, operation)
        show_metadata(label, operation, reactor_keywords)
        for property_name in ("Feeds", "AttachedFeeds", "AttachedProducts"):
            show_nested_collection(label, operation, property_name)

    reaction_keywords = (
        "component",
        "reactant",
        "product",
        "stoich",
        "coefficient",
        "equilibrium",
        "constant",
        "basis",
        "temperature",
    )
    for index, reaction in enumerate(reactions):
        label = f"REACTION [{index}] {reaction.name}"
        show_identity(label, reaction)
        show_metadata(label, reaction, reaction_keywords)
        show_nested_collection(label, reaction, "Reactants")

    for index, reaction_set in enumerate(reaction_sets):
        label = f"REACTION SET [{index}] {reaction_set.name}"
        show_identity(label, reaction_set)
        show_metadata(label, reaction_set, ("reaction", "active", "inactive"))
        show_nested_collection(label, reaction_set, "ActiveReactions")
        show_nested_collection(label, reaction_set, "InactiveReactions")

    print("\n===== SOLVER =====")
    print("Solver.CanSolve:", bool(case.Solver.CanSolve))

    print("\n===== MATERIAL STREAM RESULTS =====")
    for stream in material_streams:
        show_stream_result(stream)

    print("\n===== ENERGY STREAM METADATA =====")
    for index, stream in enumerate(energy_streams):
        label = f"ENERGY STREAM [{index}] {stream.name}"
        show_identity(label, stream)
        show_metadata(label, stream, ("energy", "heat", "duty", "flow", "power"))
        print("HeatFlow (kW):", read_scalar(stream, "HeatFlow", "kW"))
        print("HeatFlow (kJ/h):", read_scalar(stream, "HeatFlow", "kJ/h"))
        print("Power (kW):", read_scalar(stream, "Power", "kW"))

    final_hash = sha256(SOURCE_CASE_PATH)
    print("\nBASELINE_SHA256_AFTER:", final_hash)
    if final_hash != source_hash:
        raise RuntimeError("探查期间原始 methane baseline 发生变化")
    print("READ_ONLY_METHANE_INSPECTION_OK")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"READ_ONLY_METHANE_INSPECTION_FAILED: {type(exc).__name__}: {exc}")
        raise
