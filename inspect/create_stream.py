# import win32com.client as win32

# app = win32.Dispatch("HYSYS.Application")
# case = app.ActiveDocument

# solver = case.Solver
# solver.CanSolve = False

# # 创建物流
# streams = case.Flowsheet.MaterialStreams
# feed = streams.Add("Feed")
# feed.Temperature.SetValue(520.0, "C")
# feed.Pressure.SetValue(13.5, "bar")
# feed.MolarFlow.SetValue(100.0, "kgmole/h")

# # 测试 Operations.Add —— 先用 dir() 看 Add 的签名
# print("Operations members:", [m for m in dir(case.Flowsheet.Operations) if not m.startswith("_")])

# # 尝试添加一个反应器（名称/类型以后修正）
# # reactor = case.Flowsheet.Operations.Add("Reactor")





import win32com.client as win32

app = win32.Dispatch("HYSYS.Application")
case = app.ActiveDocument

if case is None:
    raise RuntimeError("没有活动案例")

solver = case.Solver
solver.CanSolve = False

streams = case.Flowsheet.MaterialStreams
feed = streams.Add("Feed")

feed.Temperature.SetValue(520.0, "C")
feed.Pressure.SetValue(13.5, "bar")
feed.MolarFlow.SetValue(100.0, "kgmole/h")

print("Stream:", feed.name)
print("Temperature:", feed.Temperature.GetValue("C"))
print("Pressure:", feed.Pressure.GetValue("bar"))
print("Molar flow:", feed.MolarFlow.GetValue("kgmole/h"))

assert feed.name == "Feed"
assert abs(feed.Temperature.GetValue("C") - 520.0) < 0.01
assert abs(feed.Pressure.GetValue("bar") - 13.5) < 0.01

print("CREATE_STREAM_OK")