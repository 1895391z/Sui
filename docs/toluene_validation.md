# 甲苯 Conversion Reactor 验证记录

验证日期：2026-09-02

HYSYS：Aspen HYSYS V15

物性包：Peng-Robinson

进料：纯甲苯，10000 kg/h，380°C，25 bar

## 模型真值探查

| 对象 | 实际名称 | TypeName | 关键读取结果 |
|---|---|---|---|
| Conversion Reactor | `CRV-100` | `conversionreactorop` | 绑定 `RS-1` |
| Conversion Reaction | `Rxn-1` | `conversionrxn` | 基准组分 Toluene |
| Reaction Set | `RS-1` | `rxnset` | `Rxn-1` 为活动反应 |

连接物流为 `Feed`、`Vap_Prod`、`Liq_Prod` 和能量流 `Q-100`。探查使用
运行副本，原始手工基准在探查前后 SHA-256 保持不变。

反应计量系数读回为：

```text
Toluene    -2.0
Benzene     1.0
p-Xylene    1.0000527473538292
```

HYSYS 根据数据库分子量进行了很小的质量配平修正。

## 参数响应结果

| 转化率 | 未反应甲苯 kg/h | 苯 kg/h | p-Xylene kg/h | 总出口 kg/h | 质量衡算误差 |
|---:|---:|---:|---:|---:|---:|
| 40% | 6000.000 | 1695.449 | 2304.551 | 10000.000 | 0.0% |
| 50% | 5000.000 | 2119.311 | 2880.689 | 10000.000 | 0.0% |
| 60% | 4000.000 | 2543.173 | 3456.827 | 10000.000 | 约 1.82e-14% |

三个工况均满足：

- `Solver.CanSolve = True`；
- 输入温度、压力、质量流量、组成和转化率回读正确；
- 转化率提高时，未反应甲苯下降，苯和 p-Xylene 增加；
- 总质量衡算误差小于0.1%；
- 只有完成全部校验后才输出 `RUN_TOLUENE_CASE_OK`。

50%和40%工况从完全关闭的 HYSYS 冷启动。60%工况在 HYSYS 进程存在、但
`SimulationCases.Count = 0` 的状态下使用全新的运行副本执行，用于验证参数响应。

## 统一自然语言 CLI 参数矩阵

2026-09-03 使用内置连接管理器重新串行验收40%和60%工况。两次运行均从无 HYSYS 进程状态
独立正常启动，取得活动 COM 对象后才进入适配器，结束时关闭各自启动的进程。

| 自然语言转化率 | status | Solver | 总二甲苯 kg/h | o/m/p 推导 | 质量衡算误差 |
|---:|---|---|---:|---|---:|
| 40% | success | 收敛 | 2304.55129092059 | 默认等比例，三项和与总量一致 | 0.0% |
| 60% | success | 收敛 | 3456.82693638089 | 默认等比例，三项和与总量一致 | 约 1.82e-14% |

两个 CaseResult 均标记 `derived_from_assumed_selectivity=true`。stdout 只包含 JSON，stderr
包含11个连接与适配器阶段标志；40%运行关闭 PID 4512，60%运行关闭 PID 8432，结束后无
HYSYS 或 Python 残留进程。两次运行前后 seed SHA-256 均保持不变。

## 原题全文 2.5 MPa 实机验收

2026-09-03 从无 HYSYS 进程状态，把考核原题全文直接传入统一 CLI。解析得到的 CaseSpec
将 `2.5 MPa` 换算为 `25.0 bar`，并保留 `10000 kg/h`、`380°C`、50%转化率和默认
o/m/p 等比例假设。随后连接管理器正常启动 HYSYS PID 2940，第28次轮询取得活动 COM
对象，只打开 runtime 副本并完成求解。

- CLI 原始退出码和采证退出码均为0，`status=success`、`solver_converged=true`；
- 未反应甲苯 `5000.0 kg/h`，苯 `2119.310886349257 kg/h`，总二甲苯
  `2880.689113650743 kg/h`；
- 推导的 o/m/p-Xylene 各为 `960.2297045502476 kg/h`，三项和在浮点精度内等于总二甲苯；
- `derived_from_assumed_selectivity=true`，没有把推导分布误报成 HYSYS 原生组分；
- 总出口 `10000.0 kg/h`，质量衡算误差0%；
- stdout 为单一、可解析的 UTF-8 CaseResult JSON；stderr 是未经 PowerShell 包装的11行
  连接与适配器日志，不含 `NativeCommandError`；
- runtime 副本成功保存，管理器只关闭本次启动的 PID 2940，结束后无 HYSYS 残留进程；
- seed 前后 SHA-256 均为
  `6272C78215B3369CA62642C3E8C8DE383C13AFAEE3C4C9314572DA23F5141C21`。

本地原始证据位于
`cases/runtime/toluene_original_2_5mpa_acceptance/`，其中包含 `stdout.json`、
`stderr.log`、`exit_code.txt` 和带前后 PID/seed 校验的 `metadata.json`。该目录由 Git 忽略。

## 种子完整性

本地反应器种子（由 `/cases/` 规则排除，不提交 Git）：

```text
cases/constant/toluene_reactor_seed.hsc
SHA-256: 6272C78215B3369CA62642C3E8C8DE383C13AFAEE3C4C9314572DA23F5141C21
```

每次运行前复制为 `cases/runtime/toluene_reactor_run.hsc`，运行结束后再次检查
种子哈希，运行副本和 HYSYS 自动备份不提交 Git。
