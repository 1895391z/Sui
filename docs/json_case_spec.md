# JSON CaseSpec 输入与离线验证

实现日期：2026-09-03

## 调用方式

```powershell
& '..\.venv\Scripts\python.exe' '.\run_case.py' --case-spec '.\my_case.json' --dry-run --output-format pretty
```

去掉 `--dry-run` 后会进入与自然语言和子命令相同的 Router、HYSYS 连接管理器及 CaseResult
输出流程。JSON 文件必须使用 UTF-8。

## 完整示例

```json
{
  "schema_version": "1.0",
  "scenario": "toluene_disproportionation",
  "inputs": {
    "feed_mass_flow_kg_h": 10000.0,
    "feed_temperature_c": 380.0,
    "pressure_bar": 25.0,
    "conversion": 0.5,
    "xylene_split": {
      "o_xylene": 0.3333333333333333,
      "m_xylene": 0.3333333333333333,
      "p_xylene": 0.3333333333333333
    }
  }
}
```

## 严格校验

- `--case-spec`、`--text` 和场景子命令只能选择一个；
- 根对象必须且只能包含 `schema_version`、`scenario` 和 `inputs`；
- inputs 必须完整匹配所选场景，不能省略字段或包含未知字段；
- Toluene 的 `xylene_split` 必须且只能包含 o/m/p 三项，均为非负有限数值且总和为1；
- schema 版本必须为 `1.0`，场景必须是三个已注册值之一；
- 数值继续复用 `CaseSpec` 的温度、压力、流量、组成和转化率校验；
- 文件缺失、无法读取、JSON 语法错误或语义错误均输出失败 JSON 并返回退出码2。

## 离线验收

完整测试覆盖三个场景的 JSON 往返、未知/缺失字段、嵌套 xylene split、schema/场景错误、
畸形或缺失文件、输入源互斥，以及 JSON dry-run 不进入 HYSYS 管理器。离线实现阶段没有启动
HYSYS；后续 live run 验收记录如下。

## Toluene live run 验收

验收日期：2026-09-03

使用 `cases/runtime` 中的临时完整 CaseSpec 先执行 dry-run，再执行一次 live run：

- dry-run 退出码0，输出 CaseSpec 与源 JSON 完全一致；
- dry-run stderr 为空，不含 HYSYS 标志，运行前后无 HYSYS 进程；
- live run 退出码0，`status=success`，Solver 收敛，甲苯转化率50%；
- 质量衡算误差0%；
- o/m/p 默认比例和为1，三个推导流量之和为 `2880.68911365074 kg/h`，与 HYSYS
  总二甲苯完全一致；
- `derived_from_assumed_selectivity=true`；
- stdout 只包含 CaseResult JSON，stderr 包含11个连接与适配器阶段标志；
- seed 运行前后 SHA-256 保持不变，runtime 正常保存；
- 内置管理器关闭本次启动的 PID 3768，结束后无 HYSYS 或 Python 残留进程。

该验收证明 JSON 文件输入与自然语言、子命令共用同一 Router、适配器和 CaseResult 执行链。
