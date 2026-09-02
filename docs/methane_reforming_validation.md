# 甲烷蒸汽重整 Equilibrium Reactor 验证记录

验证日期：2026-09-02

HYSYS：Aspen HYSYS V15

物性包：Peng-Robinson

进料：总计100 kgmol/h，520°C，13.5 bar，H2O/CH4 摩尔比2.7

## 模型真值探查

| 对象 | 实际名称 | TypeName | 说明 |
|---|---|---|---|
| Equilibrium Reactor | `ERV-100` | `equilibriumreactorop` | 绑定 `Set-1` |
| Equilibrium Reaction | `Rxn-1` | `equilibriumrxn` | CH4 + H2O ⇌ CO + 3H2 |
| Equilibrium Reaction | `Rxn-2` | `equilibriumrxn` | CO + H2O ⇌ CO2 + H2 |
| Reaction Set | `Set-1` | `rxnset` | 两个反应均为活动反应 |

物流为 `Feed`、`Vap_Prod`、`liq_Prod`，能量流为 `Q_Reformer`。COM 探查
只打开 runtime probe，原始手工 baseline 在探查前后 SHA-256 保持不变。

## 双温度工况

| 出口温度 | CH4 kgmol/h | CO kgmol/h | CO2 kgmol/h | H2 kgmol/h | CH4转化率 | 热负荷 kW |
|---:|---:|---:|---:|---:|---:|---:|
| 600°C | 18.823695 | 1.362880 | 6.840468 | 31.450510 | 30.3523% | 544.851 |
| 710°C | 12.423039 | 5.908500 | 8.695489 | 52.507457 | 54.0348% | 1080.757 |

710°C 下甲烷转化率从30.35%提高至54.03%，符合提高温度促进吸热蒸汽重整的
预期趋势；同时维持指定出口温度所需热负荷增加。

## 衡算结果

| 出口温度 | 总质量衡算误差 | C元素误差 | H元素误差 | O元素误差 |
|---:|---:|---:|---:|---:|
| 600°C | 0.0003201% | 0.0000570% | 0.0000236% | 0.0000018% |
| 710°C | 0.0006053% | 0.0000076% | 0.0000025% | 0.0000014% |

两个工况的质量及 C/H/O 元素衡算误差均小于0.1%，且均输出：

```text
VALIDATE_MODEL_OK
WRITE_INPUT_OK
SOLVED_OK
RESULT_READ_OK
RUNTIME_CASE_SAVED_OK
CLOSE_CASE_OK
RUN_METHANE_REFORMING_CASE_OK
```

600°C 工况从完全退出的 HYSYS 冷启动；710°C 工况使用全新 runtime 副本验证
参数响应。

## 统一自然语言 CLI 710°C 回归

2026-09-03 使用内置连接管理器，从无 HYSYS 进程状态执行自然语言710°C工况：

- CLI 退出码0，`status=success`，Solver 收敛；
- 甲烷转化率 `54.03475446159527%`，相对600°C提高 `23.682424400072` 个百分点；
- 热负荷 `1080.756872938247 kW`，相对600°C增加 `535.905419711757 kW`；
- 质量衡算误差 `0.0006052591908900439%`；
- C/H/O 元素衡算误差分别为 `7.55055879402278e-06%`、
  `2.54267008597979e-06%`、`1.39177345309454e-06%`；
- stdout 只包含 CaseResult JSON，stderr 包含11个连接与适配器阶段标志；
- 内置管理器关闭本次启动的 PID 1016，结束后无 HYSYS 或 Python 残留进程；
- seed 运行前后 SHA-256 保持不变。

## 统一自然语言 CLI 550°C低温边界

2026-09-03 使用内置连接管理器，从无 HYSYS 进程状态执行自然语言550°C工况：

- CLI 退出码0，`status=success`，Solver 收敛；
- 甲烷转化率 `22.434856530738646%`，相对600°C降低 `7.91747353078462` 个百分点；
- 热负荷 `358.0885831454352 kW`，相对600°C降低 `186.762870081055 kW`；
- 低温下转化率和吸热负荷同步降低，趋势与600°C、710°C结果一致；
- 质量衡算误差 `0.00023901641166606806%`；
- C/H/O 元素衡算误差分别为 `5.21906136370376e-05%`、
  `2.49584671631786e-05%`、`1.17087596673097e-05%`；
- stdout 只包含 CaseResult JSON，stderr 包含11个连接与适配器阶段标志；
- 内置管理器关闭本次启动的 PID 8612，结束后无 HYSYS 或 Python 残留进程；
- seed 运行前后 SHA-256 保持不变。

## 本地 seed

```text
cases/constant/methane_reforming_seed.hsc
SHA-256: F1E3B482DF0B1E0F8525BD33932253B00A82428D11425559790FDADE82B47C72
```

整个 `Sui/cases` 目录由 `.gitignore` 排除。每次运行只修改 runtime 副本，
运行结束后再次检查 seed 哈希。
