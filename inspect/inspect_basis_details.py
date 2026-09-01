import inspect
import win32com.client as win32


def show_method(label, obj, method_name):
    print(f"\n===== {label}.{method_name} =====")

    try:
        method = getattr(obj, method_name)
        print("Signature:", inspect.signature(method))
        print("Doc:", getattr(method, "__doc__", None))

        try:
            print(inspect.getsource(method))
        except Exception as exc:
            print("Source unavailable:", exc)

    except Exception as exc:
        print("FAILED:", exc)


def show_value(label, obj, property_name):
    try:
        print(f"{label}.{property_name} =", getattr(obj, property_name))
    except Exception as exc:
        print(f"{label}.{property_name} FAILED:", exc)


def show_settable(label, obj):
    names = set()

    for source in (obj, type(obj)):
        names.update(
            getattr(source, "_prop_map_put_", {}).keys()
        )

    ole = getattr(obj, "_olerepr_", None)
    if ole:
        names.update(getattr(ole, "propMapPut", {}).keys())

    print(f"\n===== {label} SETTABLE PROPERTIES =====")
    for name in sorted(names):
        print(name)


app = win32.gencache.EnsureDispatch("HYSYS.Application")
case = app.ActiveDocument
basis = case.BasisManager

component_list = basis.ComponentLists.Item(0)
components = component_list.Components

fluid_package = basis.FluidPackages.Item(0)

show_method("Components", components, "Add")

show_value("ComponentList", component_list, "name")
show_value("ComponentList", component_list, "TaggedName")
show_value("ComponentList", component_list, "TypeName")
show_value("ComponentList", component_list, "VisibleTypeName")

show_value("FluidPackage", fluid_package, "name")
show_value("FluidPackage", fluid_package, "TaggedName")
show_value("FluidPackage", fluid_package, "TypeName")
show_value("FluidPackage", fluid_package, "VisibleTypeName")
show_value("FluidPackage", fluid_package, "PropertyPackageName")
show_value("FluidPackage", fluid_package, "ComponentList")

show_settable("FluidPackage", fluid_package)