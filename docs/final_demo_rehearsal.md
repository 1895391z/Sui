# 最终演示彩排方案与验收清单

## 范围与顺序

彩排固定为严格串行的四条自然语言命令：先展示一条安全澄清，再展示三个场景的代表性成功
结果。每条成功命令开始前必须确认没有 AspenHysys 进程；禁止并发运行。

1. Coal 原题 `80000 Nm3/h`：预期澄清、退出码2、绝不启动 HYSYS；
2. Toluene 原题：`2.5 MPa` 换算为25 bar并成功求解；
3. Methane 原题：710/600°C按顺序使用两个独立 HYSYS 会话；
4. Coal 修正版：把流量明确为1000 kg/h并成功求解，同时保留高温外推警告。

## 统一前置检查

在 `Sui` 目录执行：

```powershell
git status --short
& '..\.venv\Scripts\python.exe' '.\verify_seeds.py' --pretty
Get-Process -Name AspenHysys -ErrorAction SilentlyContinue
& '..\.venv\Scripts\python.exe' -m unittest discover -s tests
```

要求工作区状态符合预期、68项离线测试通过、三个 seed 均为 `verified`，并且进程检查没有
输出。若任一条件不满足，停止彩排。

## 一条预期失败命令

```powershell
$CoalOriginal = '我要模拟水煤浆的气化过程。进料为煤炭和水，流量80000Nm3/h,压力40bar，水煤浆进料浓度62wt%,进料温度40摄氏度，主要反应：C+H2O → CO+H2。 请帮我计算一下气化炉出口温度为1400度时出口组成及CO的收率。反应器灰分不做考虑。CO收率就是煤炭有多少转化成CO，这一点很重要。同时希望考虑到里面有副反应的情况'
& '..\.venv\Scripts\python.exe' '.\capture_cli_evidence.py' --evidence-dir '.\cases\runtime\final_demo\01_coal_clarification' -- --text $CoalOriginal --output-format pretty
```

验收：退出码2、`status=clarification_required`、问题同时包含 `Nm3/h` 和 `kg/h`、stderr
为空，前后 PID 为空、seed 不变且没有模型 runtime 变化。采证器目前把任何非零退出码的
`evidence_status` 记为 `failed`；本命令应以 `cli_exit_code=2` 和澄清 JSON 判断为预期通过。

## 三条代表性成功命令

### Toluene 原题

```powershell
$TolueneOriginal = '请帮我完成甲苯歧化反应的模拟，甲苯原料进入转化率反应器，发生歧化反应：2C₇H₈ → C₆H₆ + C₈H₁₀。甲苯进料流量10000kg/h，进料温度为380℃，操作压力2.5MPa，甲苯转化率为50%，反应产物为苯和二甲苯（邻、间、对三种异构体），请配置反应并模拟产物分布和流股组成。用户明确提出不对反应动力学进行深入探讨，只需要知道在该转化率下反应器出口的浓度分布，不考虑其他副反应'
& '..\.venv\Scripts\python.exe' '.\capture_cli_evidence.py' --evidence-dir '.\cases\runtime\final_demo\02_toluene_original' -- --text $TolueneOriginal --output-format pretty
```

验收：退出码0、25 bar、50%转化率、Solver收敛、质量误差小于0.1%；o/m/p默认等比例，
三项和等于总二甲苯，并标记 `derived_from_assumed_selectivity=true`。

### Methane 原题双工况

```powershell
$MethaneOriginal = '我需要模拟甲烷蒸汽重整。进料是甲烷和水蒸气（摩尔比 1:2.7）有两个反应，主反应甲烷和水反应生成一氧化碳和氢气；副反应一样化碳和水蒸汽反应生成二氧化碳和氢气，请分析以下两种情况下反应炉的组分分布：1、重整炉出口气温度为 710°C，压力 13.5 bar，进料温度520℃；2、重整炉出口气温度为600℃，压力13.5bar，进料温度520℃。进料流量可以自定，要求符合一个工厂一年正常的处理量'
& '..\.venv\Scripts\python.exe' '.\capture_cli_evidence.py' --evidence-dir '.\cases\runtime\final_demo\03_methane_comparison' -- --text $MethaneOriginal --output-format pretty
```

验收：退出码0、`execution_mode=sequential`、两个结果均收敛且质量/元素误差小于0.1%；710°C
的CH4转化率和热负荷高于600°C；stderr显示两次独立启动与关闭，结束后无残留进程。

### Coal 修正版

```powershell
$CoalCorrected = '我要模拟水煤浆的气化过程。进料为煤炭和水，水煤浆质量流量1000kg/h,压力40bar，水煤浆进料浓度62wt%,进料温度40摄氏度，主要反应：C+H2O → CO+H2。 请帮我计算一下气化炉出口温度为1400度时出口组成及CO的收率。反应器灰分不做考虑。CO收率就是煤炭有多少转化成CO，这一点很重要。同时希望考虑到里面有副反应的情况'
& '..\.venv\Scripts\python.exe' '.\capture_cli_evidence.py' --evidence-dir '.\cases\runtime\final_demo\04_coal_corrected' -- --text $CoalCorrected --output-format pretty
```

验收：退出码0、Solver收敛、质量/元素误差小于0.1%，输出CO收率、碳转化率和热负荷；
CaseResult 与 stderr 均包含973.15°C外推警告，且
`engineering_validation_status=limited`。

## 每轮证据与失败处理

每个证据目录必须包含：

- `stdout.json`：唯一结构化结果；
- `stderr.log`：未经 shell 改写的阶段日志和警告；
- `exit_code.txt`：采证退出码；
- `metadata.json`：完整参数、CLI退出码、前后HYSYS PID、前后seed哈希和JSON有效性。

每条成功命令结束后再次执行进程和 seed 检查。任何意外退出码、无效 JSON、seed 变化、
残留进程、衡算超限或缺少必要警告，都应立即停止，不继续下一场景。不得手工编辑证据 JSON。

终端展示建议同时保留：前置检查、命令、最终退出码和关键结果。HYSYS 页面如需截图，应在
彩排之外只读打开已经保存的 runtime 副本；截图须明确标注它是结果展示，不属于无人触碰执行
过程，也不得保存回 seed。

## 彩排完成判定

四条命令按顺序达到各自预期、三个成功案例均清理自有进程、所有 seed 哈希保持不变，才可将
“最终演示彩排”标记为完成。彩排前已有的历史验收不能替代本目录下新生成的一整套连续证据。

## 2026-09-03 彩排执行记录

本清单已从无 AspenHysys 进程状态完整执行一次。前置检查中68项离线测试全部通过，三个 seed
均为 `verified`，随后四条命令严格串行完成：

| 顺序 | 案例 | 退出码 | 关键结果 | 进程清理 |
|---:|---|---:|---|---|
| 1 | Coal 原题 | 2（预期） | `clarification_required`，要求提供 kg/h 或换算基准 | 未启动 HYSYS |
| 2 | Toluene 原题 | 0 | 25 bar、50%转化率、质量误差0，o/m/p等比例推导 | PID 580 已关闭 |
| 3 | Methane 原题 | 0 | 710/600°C均收敛，转化率54.034754%/30.352330% | PID 8084、10332 已关闭 |
| 4 | Coal 修正版 | 0 | CO收率40.862710%，碳转化率61.294058%，保留外推警告 | PID 10208 已关闭 |

四份 stdout 均为合法 UTF-8 JSON，stderr 均无 PowerShell 包装；三个成功案例的采证状态均为
`verified`。Coal 原题的采证状态因预期退出码2显示 `failed`，应结合
`status=clarification_required` 判断为验收通过。最终进程检查为空，三份 seed 前后哈希一致。

本地证据目录：

```text
cases/runtime/final_demo/01_coal_clarification/
cases/runtime/final_demo/02_toluene_original/
cases/runtime/final_demo/03_methane_comparison/
cases/runtime/final_demo/04_coal_corrected/
```

该目录由 Git 忽略，不随本验证文档提交。
