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

## 安全行为

- 未给出的参数使用 `CaseSpec` 中公开的场景默认值；
- 已写出的温度、压力和流量必须带单位；
- 百分数大于1时必须带 `%` 或 `wt%`；
- 同一字段包含不同数值时要求澄清；
- 同时匹配多个场景或无法识别场景时要求澄清；
- 澄清响应为 JSON，`status=clarification_required`、退出码为2；
- 澄清发生在 `execute_case()` 之前，因此不会导入 COM 适配器或启动 HYSYS。

## 离线验收命令

```powershell
& '..\.venv\Scripts\python.exe' -m unittest discover -s tests -v
& '..\.venv\Scripts\python.exe' '.\run_case.py' --text '甲苯歧化，进料流量 12000 kg/h，压力 26 bar，转化率 60%' --dry-run --output-format pretty
& '..\.venv\Scripts\python.exe' '.\run_case.py' --text '甲烷蒸汽重整，出口温度 600°C 和 710°C' --dry-run --output-format pretty
```

第二条应返回标准 `dry_run` CaseSpec；第三条应返回 `clarification_required`，且不启动 HYSYS。

## 尚未执行

- 三个自然语言默认工况的 HYSYS 冷启动验收；
- 自然语言参数矩阵的实机回归；
- JSON CaseSpec 文件输入；
- 可选 LLM 解析器。
