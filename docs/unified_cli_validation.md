# 统一 CaseSpec / CaseResult CLI 验证记录

验证日期：2026-09-02

环境：Windows、Python 3.12、Aspen HYSYS V15、`pywin32`

验证版本：

```text
3e9f7b4 feat: 统一三个入口
75673a7 fix: 修复 UTF-8 输出问题
```

## 验证目标

统一入口 `run_case.py` 将三个已经独立验证的 HYSYS 适配器包装为同一调用流程：

```text
CLI -> CaseSpec -> lazy Router -> native adapter -> normalizer -> CaseResult JSON
```

本次实机验收检查：

- 三个场景均能从完全关闭的 HYSYS 状态冷启动；
- stdout 只包含一份合法 UTF-8 CaseResult JSON；
- stderr 只包含适配器过程日志和工程警告；
- CaseSpec 工况完整传递到原生适配器；
- 原生结果正确映射为统一指标、物流和衡算结构；
- seed 在运行前后保持不变；
- runtime 保存后案例和 HYSYS 进程正常退出。

## 验收命令

在 `Sui` 仓库目录分别执行：

```powershell
& '..\.venv\Scripts\python.exe' '.\run_case.py' toluene --output-format pretty
& '..\.venv\Scripts\python.exe' '.\run_case.py' methane --output-format pretty
& '..\.venv\Scripts\python.exe' '.\run_case.py' coal --output-format pretty
```

三个场景按顺序独立冷启动，没有并发访问 HYSYS COM。

## 三场景结果

| CLI 子命令 | Scenario | Reactor | 退出码 | status | solver_converged | 工程状态 |
|---|---|---|---:|---|---|---|
| `toluene` | `toluene_disproportionation` | `CRV-100` | 0 | success | true | not_assessed |
| `methane` | `methane_steam_reforming` | `ERV-100` | 0 | success | true | not_assessed |
| `coal` | `coal_slurry_gasification` | `GBR-100` | 0 | success | true | limited |

主要指标：

| 场景 | 指标 | 结果 | 质量衡算误差 |
|---|---|---:|---:|
| Toluene | 转化率 | 50.000000% | 0.0% |
| Methane | CH4转化率 | 30.352330% | 0.0003201% |
| Methane | 热负荷 | 544.851453 kW | 0.0003201% |
| Coal | CO收率 | 40.862710% | 0.0022137% |
| Coal | 碳转化率 | 61.294058% | 0.0022137% |
| Coal | 热负荷 | 1487.580836 kW | 0.0022137% |

Methane 的 C/H/O 元素衡算误差分别约为 `5.70e-5% / 2.36e-5% / 1.76e-6%`，均低于
0.1%。Coal 的 C/H/O 元素衡算误差也均远低于0.1%。

## stdout / stderr 契约

每次验收均使用操作系统进程级重定向，将两个通道分别保存到本地 runtime：

```text
cases/runtime/unified_<scenario>_stdout.json
cases/runtime/unified_<scenario>_stderr.log
```

这些文件受 `/cases/` 规则保护，不提交 Git。检查结果：

- 三份 stdout 均能独立通过 JSON 解析；
- stdout 均不包含 `RUNTIME_COPY_OK`、`SOLVED_OK` 或 `CLOSE_CASE_OK`；
- stderr 均不包含 CaseResult JSON；
- Toluene 和 Methane stderr 均包含8个完整过程标志；
- Coal stderr 还包含 `THERMODYNAMIC_VALIDITY_WARNING`；
- 所有场景均为 `RESULT_READ_OK: attempt=1`。

## UTF-8 回归

Toluene 首次统一入口验收时，原生 HYSYS 执行、保存和关闭全部成功，但最终中文 CaseResult 在
Windows 重定向环境中触发 `UnicodeEncodeError`。该次结果不计为统一 CLI 通过。

修复后，CLI 在进入 `main()` 时显式将 stdout/stderr 配置为 UTF-8，并仅将专用
`CliInputError` 归类为退出码2。随后重新执行 Toluene 冷启动，中文
`selection_reason` 和 `assumptions` 均成功写入合法 JSON，退出码为0。

离线回归共18项，覆盖：

- 三场景 dry-run；
- dry-run 不导入 `win32com` 或原生适配器；
- CaseSpec 场景/参数错配；
- 三个结果 normalizer；
- stdout 文件输出；
- argparse 和语义输入错误的 JSON/退出码2；
- `cp1252` 初始流下的中文成功 CaseResult；
- `UnicodeEncodeError` 不被误判为用户输入错误；
- 原生适配器异常和结果标准化异常的边界包装。

## Coal 工程警告

Coal 数学求解成功，因此 CLI 退出码保持0；工程有效性通过 CaseResult 单独表达：

```text
engineering_validation_status: limited
within_reported_component_gibbs_range: false
limiting_gibbs_tmax_c: 426.85
temperature_extrapolation_c: 973.15
```

CaseResult `warnings` 含1条高温外推警告，stderr 同时打印相同类别的
`THERMODYNAMIC_VALIDITY_WARNING`。这验证了“执行成功”和“工程热力学受限”可以同时准确表达。

## Seed 完整性

| 场景 | Seed SHA-256 |
|---|---|
| Toluene | `6272C78215B3369CA62642C3E8C8DE383C13AFAEE3C4C9314572DA23F5141C21` |
| Methane | `F1E3B482DF0B1E0F8525BD33932253B00A82428D11425559790FDADE82B47C72` |
| Coal | `F88D2CD59DA5156C8A2D324691C0AC7D6DBB7A4BD852604EEC3BDCD88D9448AB` |

三次正式统一入口验收中，各自 seed 的运行前后哈希均一致。每次运行只覆盖对应 runtime 副本，
结束时案例关闭，收尾检查未发现残留 HYSYS 或 Python 进程。

## 结论与边界

统一 CaseSpec、延迟 Router、CaseResult normalizer 和 CLI 已完成三场景实机验收，可以作为后续
JSON CaseSpec 文件输入和自然语言分类的稳定执行底座。

本记录证明接口、自动化、衡算和输出契约稳定，不改变各场景原有工程边界。特别是 Coal 的
1400°C Gibbs 高温外推结果仍标记为 `limited`，不得因 CLI 返回成功而解释为已完成物理验证。
