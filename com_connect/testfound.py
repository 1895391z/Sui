import win32com.client as win32

app = win32.Dispatch("HYSYS.Application")
app.Visible = True

new_case = app.SimulationCases.Add()

print("Created case:", new_case.Name)
print("CREATE_CASE_OK")