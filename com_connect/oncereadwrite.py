import win32com.client as win32

app = win32.Dispatch("HYSYS.Application")
case = app.ActiveDocument

feed = case.Flowsheet.MaterialStreams.Item("Feed")

solver = case.Solver
solver.CanSolve = False

feed.Temperature.SetValue(520.0, "C")
feed.Pressure.SetValue(13.5, "bar")
feed.MolarFlow.SetValue(100.0, "kgmole/h")

solver.CanSolve = True

temperature = feed.Temperature.GetValue("C")
pressure = feed.Pressure.GetValue("bar")
flow = feed.MolarFlow.GetValue("kgmole/h")

print("Temperature:", temperature)
print("Pressure:", pressure)
print("Molar flow:", flow)

assert abs(temperature - 520.0) < 0.01
assert abs(pressure - 13.5) < 0.01
assert abs(flow - 100.0) < 0.01

print("WRITE_READBACK_OK")