import win32com.client as win32


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
            "无法设置物流组成；"
            f"SetValues={first_error}; Values={second_error}"
        ) from second_error


TEMPLATE_PATH = r"C:\Users\Administrator\Desktop\procagent\project\simple\autosave\toluene_basis_verified.hsc"


def try_leave_basis(case, basis):
    """尝试几种方式离开 Basis 环境，进入 Simulation 环境。"""
    attempts = [
        ("basis.LeaveBasisEnvironment", lambda: basis.LeaveBasisEnvironment()),
        ("case.LeaveBasisEnvironment", lambda: case.LeaveBasisEnvironment()),
    ]
    for name, fn in attempts:
        try:
            fn()
            print(f"Left basis via: {name}")
            return True
        except Exception as exc:
            print(f"{name} failed:", exc)
    print("All automatic leave-basis attempts failed")
    return False


app = win32.Dispatch("HYSYS.Application")
app.Visible = True

print("Opening template case...")
case = app.SimulationCases.Open(TEMPLATE_PATH)
print("Opened case:", case.name)

basis = case.BasisManager

print("Component list count:", basis.ComponentLists.Count)
print("Fluid package count:", basis.FluidPackages.Count)

component_list = basis.ComponentLists.Item(0)
fluid_package = basis.FluidPackages.Item(0)

print("Components:", component_list.Components.Count)
print("Component list:", component_list.name)
print("Fluid package:", fluid_package.PropertyPackageName)

assert component_list.Components.Count == 5
assert fluid_package.PropertyPackageName == "Peng-Robinson"

try_leave_basis(case, basis)

flowsheet = case.Flowsheet
streams = flowsheet.MaterialStreams

try:
    feed = streams.Item("Feed")
    print("Using existing Feed")
except Exception:
    print("Creating Feed")
    feed = streams.Add("Feed")

for attempt in range(1, 4):
    try:
        feed.Temperature.SetValue(380.0, "C")
        feed.Pressure.SetValue(25.0, "bar")
        feed.MassFlow.SetValue(10000.0, "kg/h")
        set_molar_composition(feed, (1.0, 0.0, 0.0, 0.0, 0.0))
        print("Feed parameters written OK")
        break
    except Exception as exc:
        print(f"第{attempt}次写入失败:", exc)
        if attempt < 3:
            input(
                "请到 HYSYS 窗口：1) 点掉所有弹窗；"
                "2) 点击左下角 'Simulation' 页签进入模拟环境"
                "（能看到 PFD 流程图）；"
                "然后回到终端按回车重试..."
            )
        else:
            raise

print("\n--- Feed readback ---")
print("Temperature:", feed.Temperature.GetValue("C"))
print("Pressure:", feed.Pressure.GetValue("bar"))
print("Mass flow:", feed.MassFlow.GetValue("kg/h"))

try:
    composition = tuple(feed.ComponentMolarFraction.Values)
    print("Composition:", composition)
except Exception as exc:
    print("Composition readback unavailable:", exc)

try:
    case.Solver.CanSolve = True
    print("Solver activated")
except Exception as exc:
    print("Solver activation skipped:", exc)

try:
    case.SaveAs(TEMPLATE_PATH)
    print("Case saved (with feed):", TEMPLATE_PATH)
except Exception as exc:
    print("Save warning:", exc)

print("\nCREATE_TOLUENE_FEED_OK")