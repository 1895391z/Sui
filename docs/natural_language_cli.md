# 自然语言 CLI 离线验证记录

验证日期：2026-09-02

## 范围

统一入口新增以下调用链：

```text
--text -> 确定性场景分类 -> 参数与单位提取 -> CaseSpec -> Router
```

本阶段只验证到 `CaseSpec`，没有启动 HYSYS，也没有修改三个原生适配器。规则同时支持中英文
场景别名，并提取温度、压力、流量、转化率、蒸汽碳比和煤质量分数。
Toluene 还支持 `o/m/p 20/30/50` 或 `邻/间/对二甲苯比例 20/30/50`，比例会归一化后写入
CaseSpec；未指定时采用等比例假设。

原题兼容性加固进一步支持：

- `2.5 MPa` 自动归一化为 `25 bar`；
- `甲烷和水蒸气（摩尔比 1:2.7）` 按 CH4:H2O 解释为蒸汽碳比2.7；
- `出口气温度`、中文 `1400度` 和 `水煤浆进料浓度62wt%`；
- Methane 多出口温度生成只读、顺序执行的 `ComparisonPlan`；
- `Nm3/h`/`Nm³/h` 作为浆料流量时明确要求澄清；
- 对带工程单位但未被解析器消费的显式数值执行失败关闭检查，禁止默认值掩盖输入。

`ComparisonPlan` 当前仅支持 `--dry-run`。不带 `--dry-run` 提交比较计划时返回退出码2，并在
连接管理器之前停止，不会启动 HYSYS。计划中的原题默认100 kgmol/h仅是可线性放大的计算基准，
不宣称已经证明符合特定工厂的年处理量。

统一 CLI 后续增加了延迟加载的 HYSYS 连接管理器。live run 使用“普通启动可执行文件、等待
活动 COM 对象、执行案例、仅清理自有进程”的路径。该内置路径已完成 Toluene 实机冷启动，
Methane 600°C 和 Coal 1400°C 工况也已完成实机冷启动。

## 内置连接管理器 Toluene 验收

验收日期：2026-09-02

- 冷启动前无 HYSYS 进程；
- 正常启动 PID 12168，第27次轮询取得活动 COM 对象；
- CLI 退出码0，`status=success`，Solver 收敛；
- 甲苯转化率50%，质量衡算误差0%；
- o/m/p 默认各占三分之一，各为 `960.2297045502476 kg/h`；
- 三个异构体推导流量之和为 `2880.68911365074 kg/h`，与 HYSYS 总二甲苯一致；
- `derived_from_assumed_selectivity=true`；
- seed 运行前后 SHA-256 一致；
- stdout 仅含 CaseResult JSON，stderr 仅含连接和适配器阶段日志；
- 内置管理器关闭 PID 12168，结束后无 HYSYS 或 Python 残留进程。

## 内置连接管理器 Methane 验收

验收日期：2026-09-02

- 冷启动前无 HYSYS 进程；
- 正常启动 PID 284，第27次轮询取得活动 COM 对象；
- CLI 退出码0，`status=success`，出口温度600°C，Solver 收敛；
- 甲烷转化率 `30.35233006152327%`，热负荷 `544.8514532264899 kW`；
- 质量衡算误差 `0.00032009697680455366%`；
- C/H/O 元素衡算误差分别为 `5.70312643787929e-05%`、
  `2.35560466875241e-05%`、`1.75904247980809e-06%`；
- seed 运行前后 SHA-256 一致；
- stdout 仅含 CaseResult JSON，stderr 仅含连接和适配器阶段日志；
- 内置管理器关闭 PID 284，结束后无 HYSYS 或 Python 残留进程。

## 内置连接管理器 Coal 验收

验收日期：2026-09-02

- 冷启动前无 HYSYS 进程；
- 正常启动 PID 8776，第27次轮询取得活动 COM 对象；
- CLI 退出码0，`status=success`，出口温度1400°C，Solver 收敛；
- CO 收率 `40.862710065896245%`，碳转化率 `61.29405753575404%`；
- 热负荷 `1487.5808363950364 kW`，质量衡算误差 `0.002213745127096445%`；
- C/H/O 元素衡算误差分别为 `9.63537236021988e-14%`、
  `1.26295733823743e-07%`、`1.26295784352028e-07%`；
- `engineering_validation_status=limited`，组件 Gibbs 数据上限426.85°C，外推973.15°C；
- CaseResult warnings 和 stderr 均保留高温外推警告；
- seed 运行前后 SHA-256 一致；
- stdout 仅含 CaseResult JSON，stderr 仅含连接、警告和适配器阶段日志；
- 内置管理器关闭 PID 8776，结束后无 HYSYS 或 Python 残留进程。

## 安全行为

- 未给出的参数使用 `CaseSpec` 中公开的场景默认值；
- 已写出的温度、压力和流量必须带单位；
- 压力支持 bar 和 MPa，并统一保存为 bar；
- 百分数大于1时必须带 `%` 或 `wt%`；
- 同一字段包含不同数值时要求澄清；
- Methane 的多个出口温度是显式比较请求，在 dry-run 中生成顺序计划；
- 无法作为浆料质量流量解释的 Nm3/h/Nm³/h 必须要求澄清；
- 任何带工程单位但未被消费的显式数值都不能被默认值掩盖；
- 同时匹配多个场景或无法识别场景时要求澄清；
- 澄清响应为 JSON，`status=clarification_required`、退出码为2；
- 澄清发生在 `execute_case()` 之前，因此不会导入 COM 适配器或启动 HYSYS。

## 离线验收命令

```powershell
& '..\.venv\Scripts\python.exe' -m unittest discover -s tests -v
& '..\.venv\Scripts\python.exe' '.\run_case.py' --text '甲苯歧化，进料流量 12000 kg/h，压力 26 bar，转化率 60%' --dry-run --output-format pretty
& '..\.venv\Scripts\python.exe' '.\run_case.py' --text '甲烷蒸汽重整，出口温度 600°C 和 710°C' --dry-run --output-format pretty
```

第二条应返回标准 `dry_run` CaseSpec；第三条应返回包含两个 CaseSpec 的顺序
`ComparisonPlan`，且不启动 HYSYS。

## 尚未执行

- 可选 LLM 解析器。
