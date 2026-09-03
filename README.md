# HYSYS AI 反应器仿真助手

这是一个面向 Aspen HYSYS V15 的本地自然语言仿真系统。用户在浏览器中描述工况，系统将请求映射到经过验证的反应器模板，校验参数与工程单位，调用 HYSYS COM 完成求解，并以中文返回结果和完整 JSON。

## 当前能力

| 场景 | HYSYS反应器 | 主要输出 |
|---|---|---|
| 甲苯歧化 | Conversion Reactor | 甲苯转化率、苯及二甲苯产量、流股组成、质量衡算 |
| 甲烷蒸汽重整 | Equilibrium Reactor | CH4转化率、CO/CO2/H2组成、热负荷、元素衡算；支持温度比较 |
| 水煤浆气化 | Gibbs Reactor | CO收率、碳转化率、合成气组成、热负荷、元素衡算 |

系统支持：

- 中文或英文自然语言输入；
- bar/MPa压力换算、百分数和必要单位检查；
- OpenAI-compatible国内模型生成中文结果说明；
- 同一浏览器页面内的多轮追问和工况修改；
- 参数预检，不启动HYSYS；
- HYSYS启动失败清理、有限重试，以及单工况之间复用已启动实例；
- 标准化`CaseSpec`、`CaseResult`和`ComparisonResult` JSON；
- seed完整性校验和运行证据采集。

当前版本使用三个已经配置并验证的HYSYS seed案例。每次运行复制seed到`cases/runtime`，在副本中写入工况、求解并读取结果；目前尚未从空白Case动态创建完整流程图。

## 目录结构

```text
Sui/
├─ app/                    Web服务、对话编排和前端资源
│  ├─ chat_app.py
│  ├─ chat_service.py
│  └─ web/
├─ core/                   数据契约、自然语言解析、路由和结果标准化
├─ adapters/               三个经过验证的HYSYS场景适配器
│  ├─ toluene/
│  ├─ methane/
│  └─ coal/
├─ cases/
│  ├─ constant/            只读HYSYS seed
│  ├─ runtime/             可再生成的运行副本
│  └─ seed_manifest.json
├─ tools/                  seed校验和验收证据工具
├─ tests/                  离线自动化测试
├─ run_case.py             统一CLI入口
├─ start_chat.ps1          Web界面启动入口
├─ README.md
├─ PROJECT_PROGRESS.md
└─ 项目报告.md
```

## 环境要求

- Windows 10/11；
- Aspen HYSYS V15；
- Python 3.12；
- `pywin32`；
- COM ProgID：`HYSYS.Application`。

仓库当前使用上级目录中的`.venv`：

```powershell
& '..\.venv\Scripts\python.exe' -m pip install pywin32
```

## 启动Web界面

```powershell
Set-Location C:\Users\Administrator\Desktop\procagent\project\Sui
.\start_chat.ps1
```

浏览器访问`http://127.0.0.1:8765`。输入完整工况后默认执行真实仿真；勾选“仅校验参数”时只生成并显示CaseSpec，不启动HYSYS。

聊天模式第一次成功启动HYSYS后会保留程序实例，后续单工况复用COM服务，避免连续冷启动导致Aspen V15的`IFace.dll`故障。每轮打开的Simulation Case仍会关闭。结束使用后，可从HYSYS界面正常退出程序。

## 配置国内大模型

```powershell
Copy-Item .env.example .env
notepad .env
```

DeepSeek示例：

```dotenv
HYSYS_LLM_API_KEY=你的API密钥
HYSYS_LLM_BASE_URL=https://api.deepseek.com
HYSYS_LLM_MODEL=deepseek-v4-flash
HYSYS_LLM_TIMEOUT=60
```

阿里云百炼示例：

```dotenv
HYSYS_LLM_API_KEY=你的API密钥
HYSYS_LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
HYSYS_LLM_MODEL=qwen-plus
HYSYS_LLM_TIMEOUT=60
```

API Key只由本地服务读取，不会返回浏览器，`.env`也被Git忽略。大模型负责结果说明和多轮意图判断；场景白名单、单位检查、参数边界和HYSYS执行仍由本地代码控制。模型调用失败时自动降级为本地摘要。

## 示例问题

```text
运行甲苯歧化：进料流量10000 kg/h，进料温度380°C，压力2.5 MPa，转化率50%。
```

```text
运行甲烷蒸汽重整：总进料100 kgmol/h，S/C 2.7，进料温度520°C，压力13.5 bar，出口温度710°C。
```

```text
运行水煤浆气化：水煤浆质量流量1000 kg/h，煤浆浓度62 wt%，进料温度40°C，压力40 bar，出口温度1400°C。
```

完成一次仿真后，可以继续输入“改成600°C再算”或“为什么转化率提高”。修改工况会再次执行仿真；结果解释不会重复启动HYSYS。

## CLI

在`Sui`目录执行：

```powershell
& '..\.venv\Scripts\python.exe' '.\run_case.py' --text '甲苯歧化，进料流量10000 kg/h，进料温度380°C，压力25 bar，转化率50%'
& '..\.venv\Scripts\python.exe' '.\run_case.py' methane --outlet-temperature-c 710
& '..\.venv\Scripts\python.exe' '.\run_case.py' coal --dry-run --output-format pretty
```

CLI退出码：`0`成功、`2`输入需澄清、`3`seed缺失、`4`HYSYS/COM或适配器失败、`5`结果标准化失败、`1`其他异常。

## 校验与测试

```powershell
# 验证三个seed
& '..\.venv\Scripts\python.exe' -m tools.verify_seeds --pretty

# 运行全部离线测试
& '..\.venv\Scripts\python.exe' -m unittest discover -s tests -v

# 采集一次CLI运行证据
& '..\.venv\Scripts\python.exe' -m tools.capture_cli_evidence `
  --evidence-dir '.\cases\runtime\acceptance' -- `
  --text '甲苯歧化，转化率50%' --output-format pretty
```

## 工程边界

- 目前只执行三个固定场景，不会执行大模型生成的任意代码或COM操作。
- 甲苯模型以HYSYS中的p-Xylene代表总二甲苯；邻/间/对分布是显式选择性假设，默认等比例，并非HYSYS原生预测。
- 甲烷未给定实际工厂流量时采用100 kgmol/h归一化基准。
- 水煤浆中的煤按纯碳近似，不含灰、硫、氮；原题`80000 Nm3/h`不能直接作为浆体质量流量。
- 水煤浆1400°C超过当前组分报告的Gibbs数据上限426.85°C。数学收敛不代表结果已经获得工程热力学验证。
- 正式演示前应先验证许可证、seed哈希及HYSYS正常启动，并关闭无关案例。
