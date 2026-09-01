import win32com.client as win32


def show_members(label, obj, keywords=()):
    print(f"\n===== {label} =====")

    names = {
        name
        for name in dir(obj)
        if not name.startswith("_")
    }

    ole = getattr(obj, "_olerepr_", None)
    if ole is not None:
        names.update(getattr(ole, "mapFuncs", {}).keys())
        names.update(getattr(ole, "propMap", {}).keys())
        names.update(getattr(ole, "propMapPut", {}).keys())

    for name in sorted(names):
        if not keywords or any(k.lower() in name.lower() for k in keywords):
            print(name)


app = win32.gencache.EnsureDispatch("HYSYS.Application")
case = app.ActiveDocument

if case is None:
    raise RuntimeError("请先在 HYSYS 中打开刚创建的空白案例")

show_members(
    "CASE",
    case
)
print("\n===== CASE direct probe =====")
for name in ["Name", "BasisManager", "Flowsheet", "Solver"]:
    try:
        value = getattr(case, name)
        print(f"case.{name} -> OK, type: {type(value).__name__}")
    except Exception as e:
        print(f"case.{name} -> FAIL: {e}")

basis = case.BasisManager
show_members(
    "BASIS MANAGER",
    basis,
    ("component", "fluid", "package", "reaction"),
)

flowsheet = case.Flowsheet
show_members(
    "FLOWSHEET",
    flowsheet,
    ("stream", "operation"),
)

show_members(
    "MATERIAL STREAMS",
    flowsheet.MaterialStreams,
    ("add", "item", "count", "remove"),
)

show_members(
    "OPERATIONS",
    flowsheet.Operations,
    ("add", "item", "count", "remove"),
)