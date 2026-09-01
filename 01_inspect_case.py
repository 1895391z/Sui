import win32com.client as win32

app = win32.Dispatch("HYSYS.Application")
app.Visible = True

case = app.ActiveDocument
if case is None:
    raise RuntimeError("没有活动的 HYSYS 案例")

print("Case:", case.Name)

flowsheet = case.Flowsheet
streams = flowsheet.MaterialStreams

print("Material stream count:", streams.Count)

for i in range(streams.Count):
    stream = streams.Item(i)

    print(
        stream.Name,
        "T =", stream.Temperature.GetValue("C"), "C",
        "P =", stream.Pressure.GetValue("bar"), "bar",
        "Mass flow =", stream.MassFlow.GetValue("kg/h"), "kg/h",
    )

# import win32com.client as win32

# app = win32.Dispatch("HYSYS.Application")
# app.Visible = True

# case = app.SimulationCases.Open(r"C:\Users\Administrator\Desktop\procagent\project\simple\test.hsc")

# print("Case:", case.Name)
# print("Flowsheet name:", case.Flowsheet.Name)

# # 检查主流程中的各种对象
# for name, coll in [
#     ("MaterialStreams", case.Flowsheet.MaterialStreams),
#     ("EnergyStreams", case.Flowsheet.EnergyStreams),
#     ("UnitOps", case.Flowsheet.Operations),
# ]:
#     print(f"{name}: {coll.Count}")

# # 列出所有打开的案例
# print("Open cases:", [app.SimulationCases.Item(i).Name for i in range(app.SimulationCases.Count)])