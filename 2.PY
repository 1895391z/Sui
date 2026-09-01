import win32com.client as win32

app = win32.gencache.EnsureDispatch("HYSYS.Application")
app.Visible = True

case = app.SimulationCases.Open(
    r"C:\Users\Administrator\Desktop\procagent\project\bentest\bentest.hsc"
)

fp = case.BasisManager.FluidPackages.Item(0)
print("准确名字是:", fp.PropertyPackageName)
print("TypeName:", fp.TypeName)
print("VisibleTypeName:", fp.VisibleTypeName)