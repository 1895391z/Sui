import win32com.client as win32
import time

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

# 问题1：这个变量现在能不能改？
try:
    print("Temperature.CanModify =", feed.Temperature.CanModify)
except Exception as e:
    print("读 CanModify 失败:", e)

try:
    print("Temperature.IsKnown =", feed.Temperature.IsKnown)
except Exception as e:
    print("读 IsKnown 失败:", e)

# 问题2：让 HYSYS 处理事件，等 2 秒，再试
for i in range(5):
    app.DoEvents()
    time.sleep(0.5)

print("\n等待 2.5 秒后重试...")

# 问题3：再试 SetValue
try:
    feed.Temperature.SetValue(380.0, "C")
    print("SetValue 成功")
except Exception as e:
    print("SetValue 仍失败:", e)

# 问题4：改用 .Value 直接赋值（不带单位）
try:
    feed.Temperature.Value = 380.0
    print(".Value 赋值成功, 读回 =", feed.Temperature.Value)
except Exception as e:
    print(".Value 赋值失败:", e)