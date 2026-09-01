import inspect
import win32com.client as win32


def inspect_method(label, obj, method_name="Add"):
    print(f"\n===== {label}.{method_name} =====")

    try:
        method = getattr(obj, method_name)
    except Exception as exc:
        print("GET METHOD FAILED:", exc)
        return

    try:
        print("Signature:", inspect.signature(method))
    except Exception as exc:
        print("Signature unavailable:", exc)

    print("Doc:", getattr(method, "__doc__", None))

    try:
        print("Generated source:")
        print(inspect.getsource(method))
    except Exception as exc:
        print("Source unavailable:", exc)


def inspect_members(label, obj, keywords):
    print(f"\n===== {label} MEMBERS =====")

    names = set(name for name in dir(obj) if not name.startswith("_"))

    ole = getattr(obj, "_olerepr_", None)
    if ole:
        names.update(getattr(ole, "mapFuncs", {}).keys())
        names.update(getattr(ole, "propMap", {}).keys())
        names.update(getattr(ole, "propMapPut", {}).keys())

    for name in sorted(names):
        if any(word.lower() in name.lower() for word in keywords):
            print(name)


app = win32.gencache.EnsureDispatch("HYSYS.Application")
case = app.ActiveDocument
basis = case.BasisManager

component_lists = basis.ComponentLists
fluid_packages = basis.FluidPackages
operations = case.Flowsheet.Operations

inspect_method("ComponentLists", component_lists)
inspect_method("FluidPackages", fluid_packages)
inspect_method("Operations", operations)

inspect_members(
    "ReactionPackageManager",
    basis.ReactionPackageManager,
    ("add", "reaction", "package", "set"),
)

# 如果当前手工对照案例已经有组分列表，检查组分列表对象
try:
    print("\nComponent list count:", component_lists.Count)

    if component_lists.Count > 0:
        component_list = component_lists.Item(0)

        inspect_members(
            "ComponentList item",
            component_list,
            ("add", "component", "name", "remove"),
        )

        inspect_method("ComponentList item", component_list)

except Exception as exc:
    print("Component list item inspection failed:", exc)

# 检查已有物性包对象
try:
    print("\nFluid package count:", fluid_packages.Count)

    if fluid_packages.Count > 0:
        fluid_package = fluid_packages.Item(0)

        inspect_members(
            "FluidPackage item",
            fluid_package,
            ("name", "component", "property", "package"),
        )

except Exception as exc:
    print("Fluid package item inspection failed:", exc)