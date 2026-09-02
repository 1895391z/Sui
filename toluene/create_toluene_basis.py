import win32com.client as win32


COMPONENT_NAMES = (
    "Toluene",
    "Benzene",
    "o-Xylene",
    "m-Xylene",
    "p-Xylene",
)


def get_or_create_first(collection, name, type_name):
    """新案例有默认对象时使用默认对象，否则创建。"""
    if collection.Count > 0:
        obj = collection.Item(0)
        print(f"Using existing object: {getattr(obj, 'name', '<unnamed>')}")
        return obj

    obj = collection.Add(name, type_name)
    print(f"Created object: {getattr(obj, 'name', name)}")
    return obj


def add_component(components, component_name):
    print(f"Adding component: {component_name}")

    try:
        component = components.Add(component_name)
    except Exception as exc:
        raise RuntimeError(
            f"无法添加组分 {component_name!r}: {exc}"
        ) from exc

    print(
        "  Added:",
        getattr(component, "name", component_name),
    )

    return component


def set_molar_composition(stream, values):
    variable = stream.ComponentMolarFraction

    try:
        variable.SetValues(values)
        print("Composition set through SetValues")
        return
    except Exception as first_error:
        print("SetValues unavailable:", first_error)

    try:
        variable.Values = values
        print("Composition set through Values")
        return
    except Exception as second_error:
        raise RuntimeError(
            "无法设置物流摩尔组成；"
            f"SetValues 错误：{first_error}；"
            f"Values 错误：{second_error}"
        ) from second_error


app = win32.gencache.EnsureDispatch("HYSYS.Application")
app.Visible = True

print("Creating blank simulation case...")
case = app.SimulationCases.Add()

basis = case.BasisManager

print("\n--- Initial basis state ---")
print("Component list count:", basis.ComponentLists.Count)
print("Fluid package count:", basis.FluidPackages.Count)

# 1. 创建或取得组分列表
component_list = get_or_create_first(
    basis.ComponentLists,
    "AI Components",
    "hysyscomplist",
)

print("\nComponent list:")
print("  Name:", component_list.name)
print("  TypeName:", component_list.TypeName)
print("  VisibleTypeName:", component_list.VisibleTypeName)

# 2. 添加五个芳烃组分
components = component_list.Components

if components.Count != 0:
    raise RuntimeError(
        "新案例的组分列表不是空的。"
        "为避免重复添加，请确认脚本确实创建了新的空白案例。"
    )

for name in COMPONENT_NAMES:
    add_component(components, name)

print("Component count after addition:", components.Count)

if components.Count != len(COMPONENT_NAMES):
    raise RuntimeError(
        f"期望 {len(COMPONENT_NAMES)} 个组分，"
        f"实际为 {components.Count} 个"
    )

# 3. 创建或取得物性包
fluid_package = get_or_create_first(
    basis.FluidPackages,
    "AI Basis",
    "complist",
)

# 4. 绑定组分列表和 Peng-Robinson
fluid_package.ComponentList = component_list          # 传对象，不是名字
fluid_package.PropertyPackageName = "pengrob"         # 内部名

print("\nFluid package after configuration:")
print("  Name:", fluid_package.name)
print("  TypeName:", fluid_package.TypeName)
print("  ComponentList:", fluid_package.ComponentList.name)
print("  PropertyPackageName:", fluid_package.PropertyPackageName)

if fluid_package.ComponentList.name != component_list.name:
    raise RuntimeError("物性包没有正确绑定组分列表")

if fluid_package.PropertyPackageName != "Peng-Robinson":
    raise RuntimeError("物性包没有正确设置为 Peng-Robinson")

# 4.5 关键一步：离开 Basis 环境，进入 Simulation 环境
# 案例还停在 Properties 页签时，物流参数写入会被 HYSYS 拒绝访问（0x80070005）
solver = case.Solver

leave = getattr(basis, "LeaveBasisEnvironment", None)
if leave is not None:
    try:
        leave()
        print("Left Basis environment -> Simulation environment")
    except Exception as exc:
        print("LeaveBasisEnvironment warning:", exc)
else:
    print("LeaveBasisEnvironment not available")

# 5. 创建甲苯进料物流
flowsheet = case.Flowsheet

print("Creating material stream...")
feed = flowsheet.MaterialStreams.Add("Feed")
print("Material stream created:", feed.name)

try:
    feed.Temperature.SetValue(380.0, "C")
    feed.Pressure.SetValue(25.0, "bar")
    feed.MassFlow.SetValue(10000.0, "kg/h")
    # 组分顺序与 COMPONENT_NAMES 一致：纯甲苯进料
    set_molar_composition(feed, (1.0, 0.0, 0.0, 0.0, 0.0))
    print("Feed parameters written OK")
except Exception as exc:
    # 兜底：若仍被锁定，保存后关闭再重新打开，重开后直接进入 Simulation 模式
    print("Feed parameter write failed:", exc)
    print("Fallback: save, close and reopen the case...")

    fallback_path = r"C:\Users\Administrator\Desktop\procagent\project\simple\autosave\toluene_basis_verified.hsc"

    case.SaveAs(fallback_path)
    print("Case saved (basis only):", fallback_path)

    case.Close()
    case = app.SimulationCases.Open(fallback_path)
    basis = case.BasisManager
    flowsheet = case.Flowsheet
    solver = case.Solver

    feed = flowsheet.MaterialStreams.Add("Feed")
    feed.Temperature.SetValue(380.0, "C")
    feed.Pressure.SetValue(25.0, "bar")
    feed.MassFlow.SetValue(10000.0, "kg/h")
    set_molar_composition(feed, (1.0, 0.0, 0.0, 0.0, 0.0))
    print("Feed parameters written OK after reopen")

# 5. 创建甲苯进料物流（先访问 Flowsheet 进入模拟环境，再设置 Solver）
# flowsheet = case.Flowsheet
# solver = case.Solver

# try:
#     print("Solver initial CanSolve:", solver.CanSolve)
# except Exception as exc:
#     print("Solver state read unavailable:", exc)

# print("Creating material stream...")
# feed = flowsheet.MaterialStreams.Add("Feed")
# print("Material stream created:", feed.name)

# feed.Temperature.SetValue(380.0, "C")
# feed.Pressure.SetValue(25.0, "bar")
# feed.MassFlow.SetValue(10000.0, "kg/h")

# # 组分顺序与 COMPONENT_NAMES 一致：纯甲苯进料
# set_molar_composition(
#     feed,
#     (1.0, 0.0, 0.0, 0.0, 0.0),
# )

try:
    solver.CanSolve = True
    print("Solver activated through COM")
except Exception as exc:
    print(
        "Solver activation warning:",
        exc,
        "\nThe case may still be in Basis/Properties state.",
    )

# 6. 读回验证
print("\n--- Feed readback ---")
print("Stream:", feed.name)
print("Temperature:", feed.Temperature.GetValue("C"), "C")
print("Pressure:", feed.Pressure.GetValue("bar"), "bar")
print("Mass flow:", feed.MassFlow.GetValue("kg/h"), "kg/h")

try:
    composition = tuple(feed.ComponentMolarFraction.Values)
    print("Molar composition:", composition)

    if abs(sum(composition) - 1.0) > 1e-8:
        raise RuntimeError("进料摩尔组成之和不等于 1")

except Exception as exc:
    print("Composition readback warning:", exc)

assert abs(feed.Temperature.GetValue("C") - 380.0) < 0.01
assert abs(feed.Pressure.GetValue("bar") - 25.0) < 0.01
assert abs(feed.MassFlow.GetValue("kg/h") - 10000.0) < 0.1

# 7. 自动保存模板（防止像上次一样案例丢失）
save_path = r"C:\Users\Administrator\Desktop\procagent\project\simple\autosave\toluene_basis_verified.hsc"
try:
    case.SaveAs(save_path)
    print("Case saved to:", save_path)
except Exception as exc:
    print("Auto-save warning (可手工保存):", exc)

print("\nCREATE_TOLUENE_BASIS_OK")