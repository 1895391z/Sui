import win32com.client

app = win32com.client.Dispatch("HYSYS.Application")
app.Visible = True

print("Connected to HYSYS")
print("Open cases:", app.SimulationCases.Count)