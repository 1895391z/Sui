"""探测 HYSYS 15 中 Conversion Reactor 和 Reaction 的真实 COM API。

目的：在写正式反应器脚本前，先摸清这个版本里：
  1. BasisManager.ReactionManager 是否存在，ReactionSets 怎么加
  2. ConversionReaction 有哪些成员（Stoichiometry / Conversion / BaseComponent 等）
  3. Flowsheet.ConversionReactors 怎么加，反应器有哪些成员
探测结果用于指导正式脚本的写法，避免像 LeaveBasisEnvironment 一样踩空。
"""

import win32com.client as win32


TEMPLATE_PATH = r"C:\Users\Administrator\Desktop\procagent\project\simple\autosave\toluene_basis_verified.hsc"


def show_members(obj, label):
    """打印对象的可见成员（排除下划线开头的）。"""
    try:
        members = [m for m in dir(obj) if not m.startswith("_")]
        print(f"  {label} members ({len(members)}):")
        print("   ", members)
    except Exception as exc:
        print(f"  {label} dir() failed:", exc)


app = win32.gencache.EnsureDispatch("HYSYS.Application")
app.Visible = True

print("Opening template case...")
case = app.SimulationCases.Open(TEMPLATE_PATH)
print("Opened case:", case.name)

basis = case.BasisManager

# 1. 探测 ReactionManager
print("\n=== 1. ReactionManager ===")
try:
    rm = basis.ReactionManager
    print("  ReactionManager accessible")
    show_members(rm, "ReactionManager")
except Exception as exc:
    print("  ReactionManager failed:", exc)
    rm = None

# 2. 探测 ReactionSets 集合
print("\n=== 2. ReactionSets ===")
if rm is not None:
    try:
        rsets = rm.ReactionSets
        print("  ReactionSets accessible, Count:", rsets.Count)
        show_members(rsets, "ReactionSets")
        rset = rsets.Add("RxnSet-1")
        print("  Added ReactionSet:", rset.name)
        show_members(rset, "ReactionSet")
    except Exception as exc:
        print("  ReactionSets failed:", exc)
        rset = None
else:
    rset = None

# 3. 探测 ConversionReactions 集合和 ConversionReaction 对象
print("\n=== 3. ConversionReactions ===")
if rset is not None:
    try:
        creactions = rset.ConversionReactions
        print("  ConversionReactions accessible, Count:", creactions.Count)
        show_members(creactions, "ConversionReactions")
        rxn = creactions.Add("Cnv-1")
        print("  Added conversion reaction:", rxn.name)
        show_members(rxn, "ConversionReaction")
    except Exception as exc:
        print("  ConversionReactions failed:", exc)

# 4. 探测 Flowsheet 里的 ConversionReactors 集合和反应器对象
print("\n=== 4. ConversionReactors ===")
try:
    flowsheet = case.Flowsheet
    reactors = flowsheet.ConversionReactors
    print("  ConversionReactors accessible, Count:", reactors.Count)
    show_members(reactors, "ConversionReactors")
    reactor = reactors.Add("R-100")
    print("  Added reactor:", reactor.name)
    show_members(reactor, "ConversionReactor")
except Exception as exc:
    print("  ConversionReactors failed:", exc)

# 探测完关闭，不保存
print("\nClosing case without saving...")
try:
    case.Close()
    print("Case closed")
except Exception as exc:
    print("Close warning:", exc)

print("\nPROBE_DONE")
