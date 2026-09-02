import win32com.client as win32

app = win32.gencache.EnsureDispatch("HYSYS.Application")
app.Visible = True
app.ChangePreferencesToMinimizePopupWindows(True)
case = app.SimulationCases.Add()
basis = case.BasisManager

cl = basis.ComponentLists.Add("CL", "hysyscomplist")
for n in ("Toluene", "Benzene", "p-Xylene"):
    cl.Components.Add(n)

fp = basis.FluidPackages.Add("FP", "complist")
fp.ComponentList = cl
fp.PropertyPackageName = "pengrob"

print("Basis 配置完成")

flowsheet = case.Flowsheet
feed = flowsheet.MaterialStreams.Add("Feed")
print("创建物流成功:", feed.name)

# 尝试设置 CanSolve，失败也不中断
try:
    case.Solver.CanSolve = False
    print("CanSolve 设为 False 成功")
except Exception as e:
    print("CanSolve 设为 False 失败（忽略，继续）:", e)

# 直接设置物流值
feed.Temperature.SetValue(380.0, "C")
print("温度已设置")
feed.Pressure.SetValue(25.0, "bar")
print("压力已设置")
feed.MassFlow.SetValue(10000.0, "kg/h")
print("流量已设置")

# 读回
print("读回温度:", feed.Temperature.GetValue("C"), "C")
print("读回压力:", feed.Pressure.GetValue("bar"), "bar")
print("读回流量:", feed.MassFlow.GetValue("kg/h"), "kg/h")