import win32com.client as win32

app = win32.gencache.EnsureDispatch("HYSYS.Application")
app.Visible = True

case = app.SimulationCases.Add()
basis = case.BasisManager

cl = basis.ComponentLists.Add("CL", "hysyscomplist")
for n in ("Toluene", "Benzene", "p-Xylene"):
    cl.Components.Add(n)

# 候选名称列表，逐个试
candidates = [
    "pengrob",            # TypeName（内部名）
    "Peng-Robinson",      # 显示名（之前失败）
    "PengRob",
    "Peng Robinson",
    "Peng-Robinson (VLE)",
]

for name in candidates:
    # 每次新建一个干净物性包来试
    fp = basis.FluidPackages.Add("FP-" + name.replace(" ", "_"), "complist")
    fp.ComponentList = cl
    try:
        fp.PropertyPackageName = name
        print(f"[成功] PropertyPackageName = {name!r} -> 读回 = {fp.PropertyPackageName!r}")
    except Exception as e:
        print(f"[失败] {name!r} -> {e}")