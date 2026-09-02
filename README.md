# Sui

AI 驱动的 Aspen HYSYS V15 反应器建模考核项目。当前已完成三个固定场景的
端到端 HYSYS 适配器：甲苯歧化、甲烷蒸汽重整和水煤浆蒸汽气化。

[查看项目进度、已完成任务和后续规划](PROJECT_PROGRESS.md)

## 已完成场景

### 甲苯歧化

- 反应器：Conversion Reactor；
- 进料：纯甲苯，默认10000 kg/h、380°C、25 bar；
- 反应：`2 Toluene -> Benzene + p-Xylene`；
- 转化率接口使用0到1的比例；
- 首个闭环以 p-Xylene 代表总二甲苯。

### 甲烷蒸汽重整

- 反应器：Equilibrium Reactor；
- 进料：默认总计100 kgmol/h、520°C、13.5 bar；
- H2O/CH4 摩尔比：2.7；
- 对比出口600°C和710°C；
- 输出甲烷转化率、热负荷、质量衡算及 C/H/O 元素衡算。

### 水煤浆蒸汽气化

- 反应器：Gibbs Reactor；
- 进料质量基准：默认1000 kg/h，其中煤按纯碳近似，占62 wt%；
- 入口：40°C、40 bar；出口：1400°C；
- 无氧进料，以外部热负荷维持指定出口温度；
- 输出 CO 收率、碳转化率、热负荷、质量衡算及 C/H/O 元素衡算。
- 1400°C超过当前组件 Gibbs 数据标记上限，数学收敛结果尚未通过工程热力学验证。

## 环境

- Windows；
- Aspen HYSYS V15；
- Python 3.12；
- `pywin32`；
- COM ProgID：`HYSYS.Application`。

## 运行

在 `Sui` 仓库目录执行。

推荐使用统一入口：

```powershell
& '..\.venv\Scripts\python.exe' '.\run_case.py' toluene --conversion 0.50
& '..\.venv\Scripts\python.exe' '.\run_case.py' methane --outlet-temperature-c 710
& '..\.venv\Scripts\python.exe' '.\run_case.py' coal
```

自然语言入口采用本地确定性规则，不依赖网络或大模型：

```powershell
& '..\.venv\Scripts\python.exe' '.\run_case.py' --text '甲苯歧化，进料流量 10000 kg/h，进料温度 380°C，压力 25 bar，转化率 50%' --dry-run --output-format pretty
& '..\.venv\Scripts\python.exe' '.\run_case.py' --text '甲烷蒸汽重整，S/C 2.7，出口温度 710°C' --dry-run --output-format pretty
& '..\.venv\Scripts\python.exe' '.\run_case.py' --text '水煤浆气化，煤浆浓度 62 wt%，出口温度 1400°C' --dry-run --output-format pretty
```

`--text` 会先完成场景分类、单位检查和参数提取，再构造与子命令相同的 `CaseSpec`。
未明确写出的参数采用场景默认值；已经写出但缺少单位、数值冲突或同时出现多个场景时，CLI
返回 `clarification_required` 和具体问题，退出码为2，并且不会进入 Router 或启动 HYSYS。

只解析并校验参数、不导入适配器且不启动 HYSYS：

```powershell
& '..\.venv\Scripts\python.exe' '.\run_case.py' toluene --dry-run --output-format pretty
& '..\.venv\Scripts\python.exe' '.\run_case.py' methane --outlet-temperature-c 710 --dry-run
& '..\.venv\Scripts\python.exe' '.\run_case.py' coal --dry-run
```

统一入口的 stdout 只包含一份 CaseResult JSON；适配器过程日志和警告转发到 stderr。退出码约定为：

- `0`：成功；
- `2`：CLI 或 CaseSpec 输入无效；
- `3`：本地 seed 缺失；
- `4`：原生适配器或 HYSYS/COM 执行失败；
- `5`：原生结果无法标准化为 CaseResult；
- `1`：其他未分类异常。

也可以直接运行单个适配器：

甲苯默认50%转化率：

```powershell
& '..\.venv\Scripts\python.exe' '.\toluene\toluene_adapter.py'
```

甲苯40%或60%转化率：

```powershell
& '..\.venv\Scripts\python.exe' '.\toluene\toluene_adapter.py' --conversion 0.40
& '..\.venv\Scripts\python.exe' '.\toluene\toluene_adapter.py' --conversion 0.60
```

甲烷重整600°C和710°C：

```powershell
& '..\.venv\Scripts\python.exe' '.\methane\methane_reforming_adapter.py' --outlet-temperature-c 600
& '..\.venv\Scripts\python.exe' '.\methane\methane_reforming_adapter.py' --outlet-temperature-c 710
```

水煤浆气化默认工况：

```powershell
& '..\.venv\Scripts\python.exe' '.\coal\coal_gasification_adapter.py'
```

Python 调用示例：

```python
from methane.methane_reforming_adapter import run_methane_reforming_case

result = run_methane_reforming_case(
    total_feed_molar_flow_kgmole_h=100.0,
    steam_to_carbon_ratio=2.7,
    feed_temperature_c=520.0,
    pressure_bar=13.5,
    outlet_temperature_c=600.0,
)
```

## 本地案例策略

所有 `.hsc` 案例均保存在 `Sui/cases`，整个目录由 `.gitignore` 排除，不上传
GitHub：

```text
cases/constant/toluene_reactor_seed.hsc
cases/constant/methane_reforming_seed.hsc
cases/constant/coal_gasification_seed.hsc
cases/runtime/...
```

适配器每次将相应 seed 复制到 runtime 后运行，并在结束时重新校验 seed 的
SHA-256。运行副本不会覆盖 seed。

如果从全新的 Git clone 运行，需要从本地备份或发布包另行放入三个 seed；
Git 仓库本身不包含 HYSYS 案例文件。

## 成功与失败

适配器只有在模型结构检查、输入写入、求解、结果读取、衡算、runtime 保存和
案例关闭全部成功后，才输出相应的 `*_OK` 最终标志。任一关键步骤失败时以
非零状态退出，不会继续宣称成功。

## 验证记录

- [甲苯场景验证记录](docs/toluene_validation.md)
- [甲烷重整验证记录](docs/methane_reforming_validation.md)
- [水煤浆气化验证记录](docs/coal_gasification_validation.md)
- [统一 CaseSpec / CaseResult CLI 验证记录](docs/unified_cli_validation.md)
- [自然语言 CLI 离线验证记录](docs/natural_language_cli.md)

## 当前边界

- 二甲苯异构体选择性未由题目给出，当前以 p-Xylene 表示总二甲苯；
- 水煤浆气化已通过冷启动和连续3次重复性验证；1400°C Gibbs 外推结果仍需工程复核；
- 统一 CLI 已完成三个场景的独立冷启动、UTF-8 JSON 和 stdout/stderr 分离验收；
- 自然语言分类与参数提取已完成离线实现，尚待授权进行三场景实机验收；
- JSON CaseSpec 文件输入尚未整合，并按当前计划排在自然语言入口之后；
- Live Demo 前仍需完整彩排并保留终端与 HYSYS 结果截图。
