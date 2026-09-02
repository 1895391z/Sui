"""Deep read-only COM inspection of the coal Gibbs-reactor probe copy."""

from __future__ import annotations

import hashlib
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


SUI_ROOT = Path(__file__).resolve().parents[1]
SOURCE_CASE_PATH = SUI_ROOT / "cases" / "constant" / "coal_gasification_seed.hsc"
PROBE_CASE_PATH = SUI_ROOT / "cases" / "runtime" / "coal_gibbs_deep_probe.hsc"

COMPONENT_LIST_NAME = "Component List - 1"
FLUID_PACKAGE_NAME = "Basis-1"
REACTOR_NAME = "GBR-100"
STREAM_NAMES = ("Feed", "Syngas_Out", "Bottom_Out")
CARBON_NAME = "Carbon"

FORBIDDEN_PREFIXES = (
    "add",
    "close",
    "create",
    "delete",
    "insert",
    "open",
    "quit",
    "remove",
    "save",
    "set",
)


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


def is_forbidden(name: str) -> bool:
    lowered = name.lower()
    return any(lowered.startswith(prefix) for prefix in FORBIDDEN_PREFIXES)


def com_maps(obj: Any) -> tuple[set[str], set[str], set[str]]:
    getters: set[str] = set()
    putters: set[str] = set()
    functions: set[str] = set()
    ole = getattr(obj, "_olerepr_", None)
    if ole is not None:
        getters.update(getattr(ole, "propMap", {}).keys())
        putters.update(getattr(ole, "propMapPut", {}).keys())
        functions.update(getattr(ole, "mapFuncs", {}).keys())
    for owner in (obj, type(obj)):
        getters.update(getattr(owner, "_prop_map_get_", {}).keys())
        putters.update(getattr(owner, "_prop_map_put_", {}).keys())
    return getters, putters, functions


def matches(name: str, keywords: Iterable[str]) -> bool:
    lowered = name.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def describe_object(value: Any) -> str:
    fields = [f"python_type={type(value).__name__}"]
    for name in ("name", "TypeName", "VisibleTypeName"):
        ok, item = safe_get(value, name)
        if ok and isinstance(item, (str, int, float, bool)):
            fields.append(f"{name}={item!r}")
    return "<" + ", ".join(fields) + ">"


def readable_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (tuple, list)):
        return tuple(value)

    ok, count = safe_get(value, "Count")
    if ok and isinstance(count, int) and 0 <= count <= 100:
        items = []
        for index in range(count):
            try:
                items.append(describe_object(value.Item(index)))
            except Exception as exc:
                items.append(f"<{type(exc).__name__}: {exc}>")
        return tuple(items)

    ok, values = safe_get(value, "Values")
    if ok:
        try:
            return tuple(float(item) for item in values)
        except Exception:
            return repr(values)
    return describe_object(value)


def show_inventory(label: str, obj: Any, keywords: tuple[str, ...]) -> None:
    getters, putters, functions = com_maps(obj)
    fallback = {name for name in dir(obj) if not name.startswith("_")}
    print(f"\n===== {label} COM INVENTORY =====")
    for category, names in (
        ("GETTER", getters),
        ("WRITABLE_METADATA", putters),
        ("FUNCTION", functions),
        ("DIR_FALLBACK", fallback - getters - putters - functions),
    ):
        selected = sorted(
            name for name in names if matches(name, keywords) and not is_forbidden(name)
        )
        print(f"{category}:", selected)


def show_properties(label: str, obj: Any, names: Iterable[str]) -> None:
    print(f"\n===== {label} PROPERTY VALUES =====")
    for name in names:
        if is_forbidden(name):
            print(f"{name}: <SKIPPED_FORBIDDEN_NAME>")
            continue
        ok, value = safe_get(obj, name)
        if ok:
            print(f"{name}: {readable_value(value)!r}")
        else:
            print(f"{name}: {value}")


def get_named(collection: Any, name: str) -> Any:
    item = collection.Item(name)
    if str(item.name) != name:
        raise RuntimeError(f"Named lookup mismatch: requested={name!r}, actual={item.name!r}")
    return item


def read_variable(obj: Any, name: str, units: tuple[str, ...]) -> Any:
    ok, variable = safe_get(obj, name)
    if not ok:
        return variable
    for unit in units:
        try:
            value = float(variable.GetValue(unit))
            if math.isfinite(value):
                return {"value": value, "unit": unit}
        except Exception:
            pass
    return readable_value(variable)


def show_stream_phase(stream: Any) -> None:
    label = f"STREAM {stream.name}"
    phase_keywords = (
        "phase",
        "vapour",
        "vapor",
        "liquid",
        "solid",
        "fraction",
        "temperature",
        "pressure",
        "flow",
    )
    show_inventory(label, stream, phase_keywords)
    show_properties(
        label,
        stream,
        (
            "name",
            "TypeName",
            "VisibleTypeName",
            "Phase",
            "Phases",
            "VapourFraction",
            "VaporFraction",
            "LiquidFraction",
            "SolidFraction",
            "ComponentMolarFraction",
            "ComponentMassFraction",
            "ComponentMolarFlow",
            "ComponentMassFlow",
        ),
    )
    print(
        "SCALARS:",
        {
            "temperature_c": read_variable(stream, "Temperature", ("C",)),
            "pressure_bar": read_variable(stream, "Pressure", ("bar",)),
            "mass_flow_kg_h": read_variable(stream, "MassFlow", ("kg/h",)),
            "molar_flow_kgmole_h": read_variable(
                stream, "MolarFlow", ("kgmole/h",)
            ),
            "vapour_fraction": read_variable(
                stream, "VapourFraction", ("", "fraction")
            ),
        },
    )


def main() -> None:
    if not SOURCE_CASE_PATH.is_file():
        raise FileNotFoundError(f"Coal gasification seed does not exist: {SOURCE_CASE_PATH}")
    original_hash = sha256(SOURCE_CASE_PATH)
    print("SEED_PATH:", SOURCE_CASE_PATH)
    print("SEED_SHA256_BEFORE:", original_hash)

    PROBE_CASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE_CASE_PATH, PROBE_CASE_PATH)
    if sha256(PROBE_CASE_PATH) != original_hash:
        raise RuntimeError("Deep-probe copy SHA-256 does not match the seed")
    print("PROBE_COPY_OK:", PROBE_CASE_PATH)

    app = win32.Dispatch("HYSYS.Application")
    app.Visible = True
    case = app.SimulationCases.Open(str(PROBE_CASE_PATH))
    print("OPEN_PROBE_COPY_OK:", case.name)

    basis = case.BasisManager
    component_list = get_named(basis.ComponentLists, COMPONENT_LIST_NAME)
    fluid_package = get_named(basis.FluidPackages, FLUID_PACKAGE_NAME)
    reactor = get_named(case.Flowsheet.Operations, REACTOR_NAME)
    streams = {
        name: get_named(case.Flowsheet.MaterialStreams, name) for name in STREAM_NAMES
    }
    carbon = get_named(component_list.Components, CARBON_NAME)

    show_inventory(
        "CARBON COMPONENT",
        carbon,
        (
            "name",
            "formula",
            "id",
            "cas",
            "class",
            "family",
            "molecular",
            "boil",
            "freeze",
            "melt",
            "critical",
            "solid",
            "phase",
            "formation",
            "gibbs",
            "enthalpy",
            "database",
        ),
    )
    show_properties(
        "CARBON COMPONENT",
        carbon,
        (
            "name",
            "TypeName",
            "VisibleTypeName",
            "Formula",
            "CAS_Number",
            "CAS_Number2",
            "IDNumber",
            "Class",
            "IsValid",
            "CASNumber",
            "ComponentID",
            "ComponentClass",
            "Family",
            "DatabaseName",
            "MolecularWeight",
            "MolecularWeightValue",
            "NormalBoilingPoint",
            "NormalBoilingPointValue",
            "FreezingPoint",
            "MeltingPoint",
            "CriticalTemperature",
            "CriticalTemperatureValue",
            "CriticalPressure",
            "CriticalPressureValue",
            "HeatOfFormationValue",
            "GibbsCoeffsValue",
            "GibbsTminValue",
            "GibbsTmaxValue",
            "IdealHCoeffsValue",
            "IdealHTminValue",
            "IdealHTmaxValue",
            "IdealGasEnthalpyOfFormation",
            "IdealGasGibbsFreeEnergyOfFormation",
            "StandardEnthalpyOfFormation",
            "StandardGibbsFreeEnergyOfFormation",
            "SolidDensity",
            "SolidDensityValue",
            "SolidCpCoeffsValue",
            "SolidCpTminValue",
            "SolidCpTmaxValue",
            "SolidDiameterValue",
            "SolidSphericityValue",
            "SolidHeatCapacity",
            "IsSolid",
            "Phase",
        ),
    )

    print("\n===== ALL COMPONENT EQUILIBRIUM DATA =====")
    for index in range(int(component_list.Components.Count)):
        component = component_list.Components.Item(index)
        row = {"name": str(component.name)}
        for property_name in (
            "Formula",
            "IsSolid",
            "IsValid",
            "MolecularWeightValue",
            "HeatOfFormationValue",
            "GibbsCoeffsValue",
            "GibbsTminValue",
            "GibbsTmaxValue",
        ):
            ok, value = safe_get(component, property_name)
            row[property_name] = readable_value(value) if ok else value
        print(row)

    show_inventory(
        "FLUID PACKAGE",
        fluid_package,
        ("component", "property", "phase", "solid", "vapour", "vapor", "liquid"),
    )
    show_properties(
        "FLUID PACKAGE",
        fluid_package,
        (
            "name",
            "TypeName",
            "VisibleTypeName",
            "PropertyPackageName",
            "ComponentList",
            "Phases",
            "AllowedPhases",
            "SolidComponents",
        ),
    )

    reactor_keywords = (
        "component",
        "feed",
        "product",
        "phase",
        "solid",
        "vapour",
        "vapor",
        "liquid",
        "gibbs",
        "equilibrium",
        "heater",
        "heat",
        "temperature",
        "pressure",
        "solve",
        "status",
    )
    show_inventory("GIBBS REACTOR", reactor, reactor_keywords)
    show_properties(
        "GIBBS REACTOR",
        reactor,
        (
            "name",
            "TypeName",
            "VisibleTypeName",
            "Feeds",
            "AttachedFeeds",
            "AttachedProducts",
            "VapourProduct",
            "VaporProduct",
            "LiquidProduct",
            "SolidProduct",
            "EnergyStream",
            "ReactorType",
            "ReactionSet",
            "InertSpeciesValue",
            "FractionSpecifiedValue",
            "FixedSpecificationValue",
            "SeparationStage",
            "VesselType",
            "HoldupInitType",
            "IsValid",
            "IsIgnored",
            "TypeOfHeater",
            "TopOfHeater",
            "BottomOfHeater",
            "HeatFlowValue",
            "PressureDropValue",
            "ComponentName",
            "ComponentTotalFeed",
            "ComponentTotalFeedValue",
            "ComponentTotalProduct",
            "ComponentTotalProductValue",
            "Phases",
            "AllowedPhases",
            "EquilibriumPhases",
            "GibbsComponents",
            "Status",
            "Solved",
        ),
    )

    for stream in streams.values():
        show_stream_phase(stream)

    print("\n===== SOLVER =====")
    print("Solver.CanSolve:", bool(case.Solver.CanSolve))

    final_hash = sha256(SOURCE_CASE_PATH)
    print("SEED_SHA256_AFTER:", final_hash)
    if final_hash != original_hash:
        raise RuntimeError("Coal seed changed during the deep read-only probe")
    print("READ_ONLY_COAL_GIBBS_DEEP_PROBE_OK")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"READ_ONLY_COAL_GIBBS_DEEP_PROBE_FAILED: {type(exc).__name__}: {exc}")
        raise
