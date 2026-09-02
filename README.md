# Sui

AI 驱动的 Aspen HYSYS V15 反应器建模考核项目。当前已完成甲苯歧化
`Conversion Reactor` 的第一个端到端闭环。

## 已完成的甲苯场景

- 进料：纯甲苯，默认 `10000 kg/h`、`380°C`、`25 bar`；
- 反应：`2 Toluene -> Benzene + p-Xylene`；
- 反应器：HYSYS `Conversion Reactor`；
- 转化率：接口使用 `0~1` 的比例，适配器写入 HYSYS 时转换为百分数；
- 输出：进料、气液产品物流、合并组分质量流量、收敛状态和质量衡算误差；
- 假设：首个闭环以 `p-Xylene` 代表总二甲苯。

## 环境

- Windows；
- Aspen HYSYS V15；
- Python 3.12；
- `pywin32`；
- COM ProgID：`HYSYS.Application`。

## 运行

在仓库目录执行默认50%转化率工况：

```powershell
& '..\.venv\Scripts\python.exe' '.\toluene_adapter.py'
```

测试40%或60%转化率：

```powershell
& '..\.venv\Scripts\python.exe' '.\toluene_adapter.py' --conversion 0.40
& '..\.venv\Scripts\python.exe' '.\toluene_adapter.py' --conversion 0.60
```

也可以从 Python 调用：

```python
from toluene_adapter import run_toluene_case

result = run_toluene_case(
    feed_mass_flow_kg_h=10000.0,
    feed_temperature_c=380.0,
    pressure_bar=25.0,
    conversion=0.50,
)
```

只有在复制种子、打开案例、模型校验、输入写入、求解、结果读取、质量衡算、
运行副本保存和关闭案例全部成功后，脚本才输出：

```text
RUN_TOLUENE_CASE_OK
```

任一关键步骤失败时进程以非零状态退出，不会打印成功标志。

## 案例文件策略

```text
cases/constant/toluene_reactor_seed.hsc  # 已验证、不可覆盖的反应器种子
cases/runtime/toluene_reactor_run.hsc    # 每次运行重新生成，不提交 Git
```

适配器只将种子复制到 `runtime` 后运行，并在结束时再次校验种子 SHA-256。
种子包含 HYSYS V15 中实际确认的对象：

- `CRV-100`：`conversionreactorop`；
- `Rxn-1`：`conversionrxn`；
- `RS-1`：`rxnset`；
- `Feed`、`Vap_Prod`、`Liq_Prod` 和 `Q-100`。

## 验证记录

40%、50%、60%转化率均已通过实际 HYSYS 求解和质量衡算检查，详见
[甲苯场景验证记录](docs/toluene_validation.md)。

## 当前边界

- 当前仅完成固定甲苯歧化场景；
- 二甲苯异构体选择性未由题目给出，因此暂不拆分为三种异构体；
- 尚未实现甲烷蒸汽重整和平衡反应器场景；
- 尚未实现水煤浆气化和 Gibbs Reactor 场景；
- Live Demo 前仍需进行完整彩排并保留终端与 HYSYS 结果截图。
