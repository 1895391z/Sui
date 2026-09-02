"""Read-only inspection of the manually verified toluene reactor case.

The script deliberately contains no property assignments and no Save/SaveAs calls.
It reports COM metadata and selected property values without changing the case.
"""

from __future__ import annotations

import hashlib
import inspect
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
    / "toluene_reactor_baseline"
    / "toluene_reactor_baseline.hsc"
)
PROBE_CASE_PATH = PROJECT_ROOT / "cases" / "runtime" / "toluene_reactor_probe.hsc"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def member_maps(obj: Any) -> tuple[set[str], set[str], set[str]]:
    """Return method, readable-property, and writable-property metadata names."""
    methods: set[str] = set()
    readable: set[str] = set()
    writable: set[str] = set()

    methods.update(name for name in dir(obj) if not name.startswith("_"))
    ole = getattr(obj, "_olerepr_", None)
    if ole is not None:
        methods.update(getattr(ole, "mapFuncs", {}).keys())
        readable.update(getattr(ole, "propMap", {}).keys())
        writable.update(getattr(ole, "propMapPut", {}).keys())

    # EnsureDispatch-generated classes expose these maps directly rather than
    # through _olerepr_. Reading their keys does not invoke any COM property.
    for owner in (obj, type(obj)):
        readable.update(getattr(owner, "_prop_map_get_", {}).keys())
        writable.update(getattr(owner, "_prop_map_put_", {}).keys())

    return methods, readable, writable


def matching(names: Iterable[str], keywords: Iterable[str]) -> list[str]:
    lowered = tuple(keyword.lower() for keyword in keywords)
    return sorted(
        name for name in names if any(keyword in name.lower() for keyword in lowered)
    )


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

    details = [f"python_type={type(value).__name__}"]
    for attribute in ("name", "Name", "TypeName", "VisibleTypeName"):
        ok, item = safe_get(value, attribute)
        if ok and isinstance(item, (str, int, float, bool)):
            details.append(f"{attribute}={item!r}")
    return "<" + ", ".join(details) + ">"


def show_nested_value(label: str, obj: Any, name: str) -> None:
    ok, value = safe_get(obj, name)
    print(f"\n===== {label}.{name} =====")
    if not ok:
        print(value)
        return

    if isinstance(value, (tuple, list)):
        print("Sequence length:", len(value))
        for index, item in enumerate(value):
            print(f"[{index}] {describe(item)}")
        return

    count_ok, count = safe_get(value, "Count")
    item_ok, _ = safe_get(value, "Item")
    if count_ok and item_ok:
        print("Count:", count)
        for index in range(int(count)):
            item = value.Item(index)
            print(f"[{index}] {describe(item)}")
            show_selected_values(
                f"{label}.{name}[{index}]",
                item,
                (
                    "Component",
                    "ComponentName",
                    "Coefficient",
                    "StoichCoef",
                    "StoichiometricCoefficient",
                    "IsReactant",
                    "Phase",
                ),
            )
        return

    print(describe(value))


def show_identity(label: str, obj: Any) -> None:
    print(f"\n===== {label} IDENTITY =====")
    for name in ("name", "Name", "TypeName", "VisibleTypeName"):
        ok, value = safe_get(obj, name)
        print(f"{name}: {describe(value) if ok else value}")


def show_metadata(label: str, obj: Any, keywords: tuple[str, ...]) -> None:
    methods, readable, writable = member_maps(obj)
    print(f"\n===== {label} RELEVANT METHODS/MEMBERS =====")
    for name in matching(methods, keywords):
        print(name)
    print(f"\n===== {label} READABLE PROPERTIES =====")
    for name in matching(readable, keywords):
        print(name)
    print(f"\n===== {label} WRITABLE PROPERTIES (METADATA ONLY) =====")
    for name in matching(writable, keywords):
        print(name)


def show_method(label: str, obj: Any, method_name: str) -> None:
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


def show_selected_values(label: str, obj: Any, candidates: tuple[str, ...]) -> None:
    print(f"\n===== {label} SELECTED READ-ONLY VALUES =====")
    methods, readable, writable = member_maps(obj)
    known = methods | readable | writable
    for name in candidates:
        if name not in known:
            continue
        ok, value = safe_get(obj, name)
        print(f"{name}: {describe(value) if ok else value}")


def show_collection(label: str, collection: Any) -> None:
    print(f"\n===== {label} ITEMS =====")
    count = int(collection.Count)
    print("Count:", count)
    for index in range(count):
        item = collection.Item(index)
        fields = []
        for attribute in ("name", "Name", "TypeName", "VisibleTypeName"):
            ok, value = safe_get(item, attribute)
            if ok and isinstance(value, (str, int, float, bool)):
                fields.append(f"{attribute}={value!r}")
        print(f"[{index}] " + ", ".join(fields))


def read_scalar(variable: Any, unit: str) -> float:
    return float(variable.GetValue(unit))


def read_flex(variable: Any, unit: str | None = None) -> tuple[float, ...]:
    if unit is not None:
        try:
            return tuple(float(value) for value in variable.GetValues(unit))
        except Exception:
            pass
    return tuple(float(value) for value in variable.Values)


def read_stream_result(stream: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"name": str(stream.name)}
    scalar_specs = (
        ("temperature_c", "Temperature", "C"),
        ("pressure_bar", "Pressure", "bar"),
        ("mass_flow_kg_h", "MassFlow", "kg/h"),
        ("molar_flow_kgmole_h", "MolarFlow", "kgmole/h"),
    )
    for output_name, property_name, unit in scalar_specs:
        ok, variable = safe_get(stream, property_name)
        if not ok:
            result[output_name] = variable
            continue
        try:
            result[output_name] = read_scalar(variable, unit)
        except Exception as exc:
            result[output_name] = f"<{type(exc).__name__}: {exc}>"

    for output_name, property_name, unit in (
        ("molar_fraction", "ComponentMolarFraction", None),
        ("component_mass_flow_kg_h", "ComponentMassFlow", "kg/h"),
    ):
        ok, variable = safe_get(stream, property_name)
        if not ok:
            result[output_name] = variable
            continue
        try:
            result[output_name] = read_flex(variable, unit)
        except Exception as exc:
            result[output_name] = f"<{type(exc).__name__}: {exc}>"
    return result


def find_item(
    collection: Any,
    preferred_names: tuple[str, ...],
    expected_type_name: str,
) -> Any:
    """Find an existing item without calling Add or changing its name."""
    items = [collection.Item(index) for index in range(int(collection.Count))]
    preferred_lower = {name.lower() for name in preferred_names}

    for item in items:
        if str(item.name).lower() in preferred_lower:
            return item

    matching_type = [
        item
        for item in items
        if str(item.TypeName).lower() == expected_type_name.lower()
    ]
    if len(matching_type) == 1:
        return matching_type[0]

    available = tuple(
        (str(item.name), str(item.TypeName))
        for item in items
    )
    raise RuntimeError(
        f"找不到对象：names={preferred_names}, type={expected_type_name}, "
        f"available={available}"
    )


def main() -> None:
    if not SOURCE_CASE_PATH.is_file():
        raise FileNotFoundError(f"手工反应器基准不存在：{SOURCE_CASE_PATH}")

    original_hash = sha256(SOURCE_CASE_PATH)
    print("BASELINE_PATH:", SOURCE_CASE_PATH)
    print("BASELINE_SHA256_BEFORE:", original_hash)

    app = win32.Dispatch("HYSYS.Application")
    if "--active" in sys.argv[1:]:
        case = app.ActiveDocument
        if case is None:
            raise RuntimeError("HYSYS 当前没有活动案例")
        print("USING_ACTIVE_PROBE_CASE:", case.name)
    else:
        PROBE_CASE_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SOURCE_CASE_PATH, PROBE_CASE_PATH)
        if sha256(PROBE_CASE_PATH) != original_hash:
            raise RuntimeError("探查副本与手工基准的 SHA-256 不一致")
        print("PROBE_COPY_OK:", PROBE_CASE_PATH)
        case = app.SimulationCases.Open(str(PROBE_CASE_PATH))
        print("OPEN_PROBE_COPY_OK:", case.name)

    basis = case.BasisManager
    flowsheet = case.Flowsheet
    operations = flowsheet.Operations
    reaction_manager = basis.ReactionPackageManager
    reactions = reaction_manager.Reactions
    reaction_sets = reaction_manager.ReactionSets

    show_collection("OPERATIONS", operations)
    show_collection("REACTIONS", reactions)
    show_collection("REACTION SETS", reaction_sets)
    show_collection("MATERIAL STREAMS", flowsheet.MaterialStreams)
    try:
        show_collection("ENERGY STREAMS", flowsheet.EnergyStreams)
    except Exception as exc:
        print("\n===== ENERGY STREAMS ITEMS =====")
        print("Unavailable:", exc)

    reactor = find_item(
        operations,
        preferred_names=("R-100", "CRV-100"),
        expected_type_name="conversionreactorop",
    )
    reaction = find_item(
        reactions,
        preferred_names=("RXN-1",),
        expected_type_name="conversionrxn",
    )
    reaction_set = find_item(
        reaction_sets,
        preferred_names=("RS-1",),
        expected_type_name="rxnset",
    )

    show_identity("R-100", reactor)
    show_identity("RXN-1", reaction)
    show_identity("RS-1", reaction_set)

    show_method("Operations", operations, "Add")
    show_method("Reactions", reactions, "Add")
    show_method("ReactionSets", reaction_sets, "Add")

    show_metadata(
        "R-100",
        reactor,
        (
            "reaction",
            "feed",
            "inlet",
            "outlet",
            "product",
            "vapour",
            "vapor",
            "liquid",
            "energy",
            "solve",
            "status",
        ),
    )
    show_selected_values(
        "R-100",
        reactor,
        (
            "ReactionSet",
            "ReactionSetName",
            "Feed",
            "FeedStream",
            "Inlet",
            "InletStream",
            "Product",
            "ProductStream",
            "VapourProduct",
            "VaporProduct",
            "LiquidProduct",
            "EnergyStream",
            "Energy",
            "CanSolve",
            "Solved",
            "Status",
        ),
    )
    for name in ("Feeds", "AttachedFeeds", "AttachedProducts"):
        show_nested_value("R-100", reactor, name)

    show_metadata(
        "RXN-1",
        reaction,
        (
            "component",
            "stoich",
            "coefficient",
            "conversion",
            "basis",
            "reactant",
            "product",
        ),
    )
    show_selected_values(
        "RXN-1",
        reaction,
        (
            "Components",
            "Stoichiometry",
            "StoichiometricCoefficients",
            "Coefficients",
            "Conversion",
            "ConversionBasis",
            "Basis",
            "BaseComponent",
            "ConversionCoefficients",
            "ConversionCoefficientsValue",
            "ReactantName",
            "ReactantStoichCoef",
            "ReactantStoichCoefValue",
            "ReactantMoleWeight",
            "ReactantMoleWeightValue",
        ),
    )
    show_nested_value("RXN-1", reaction, "Reactants")

    show_metadata(
        "RS-1",
        reaction_set,
        ("reaction", "add", "remove", "count", "item", "set"),
    )
    show_selected_values(
        "RS-1",
        reaction_set,
        ("Reactions", "ReactionSet", "Count", "ReactionPackage"),
    )
    for name in ("ActiveReactions", "InactiveReactions"):
        show_nested_value("RS-1", reaction_set, name)

    print("\n===== SOLVER AND STREAM RESULTS =====")
    print("Solver.CanSolve:", bool(case.Solver.CanSolve))
    stream_results = {
        name: read_stream_result(flowsheet.MaterialStreams.Item(name))
        for name in ("Feed", "Vap_Prod", "Liq_Prod")
    }
    for name, result in stream_results.items():
        print(f"{name}:", result)

    feed_mass = stream_results["Feed"].get("mass_flow_kg_h")
    product_masses = [
        stream_results[name].get("mass_flow_kg_h")
        for name in ("Vap_Prod", "Liq_Prod")
    ]
    if isinstance(feed_mass, float) and all(
        isinstance(value, float) for value in product_masses
    ):
        total_product_mass = sum(product_masses)
        mass_balance_error_percent = (
            abs(total_product_mass - feed_mass) / feed_mass * 100.0
            if feed_mass != 0.0
            else float("inf")
        )
        print("Total product mass flow (kg/h):", total_product_mass)
        print("Mass balance error (%):", mass_balance_error_percent)
    else:
        print("Mass balance unavailable: one or more mass flows could not be read")

    final_hash = sha256(SOURCE_CASE_PATH)
    print("\nBASELINE_SHA256_AFTER:", final_hash)
    if final_hash != original_hash:
        raise RuntimeError("只读探查期间基准文件发生变化")
    print("READ_ONLY_INSPECTION_OK")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"READ_ONLY_INSPECTION_FAILED: {type(exc).__name__}: {exc}")
        raise
