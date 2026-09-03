# 项目进度与后续计划

更新日期：2026-09-02

## 当前结论

项目的三条 HYSYS 固定场景执行链、统一数据契约和统一 CLI 已经建立。当前工作重点按新的
项目指引调整为“自然语言端到端优先”，JSON 文件输入后置。现有适配器保持冻结，新增能力通过
`CaseSpec -> Router -> CaseResult` 边界接入。

整体完成度估计为 75%–85%。这个比例表示工程链路已经成形，不表示所有物理假设均已完成验证。

## 已完成

- Toluene Conversion Reactor 适配器：seed 副本运行、输入写入、30秒重试、严格校验和结果读取；
- Methane Equilibrium Reactor 适配器：600°C 与710°C工况验证、质量及 C/H/O 衡算；
- Coal Gibbs Reactor 适配器：默认工况冷启动、连续3次重复性测试和只读深度探查；
- Coal 1400°C Gibbs 数据外推警告及 `engineering_validation_status=limited`；
- 统一 `CaseSpec`、`CaseResult`、延迟 Router、结果 normalizer 和 CLI；
- 三个场景通过统一 CLI 的独立冷启动验收；
- UTF-8 JSON、stdout/stderr 分离和退出码分类；
- 本地 `/cases/` 全目录 Git 排除，运行副本不覆盖不可变 seed；
- 统一 CLI 验证文档和 README 入口；
- 确定性自然语言分类、参数提取、单位检查、澄清响应和 dry-run 离线测试。
- Toluene 可选 `xylene_split`，默认等比例；输出明确标记为选择性假设推导。
- seed manifest 与只读校验器，能够区分 verified、missing 和 hash mismatch。
- 已证明普通启动 HYSYS 后可取得活动 COM 对象，并以外层流程完成 Toluene 端到端验收；
- 统一 CLI 已内置延迟加载的 HYSYS 连接管理器，离线覆盖复用、启动、超时与清理路径。
- 内置连接管理器已独立完成 Toluene 自然语言默认工况冷启动和自有进程清理验收。
- 内置连接管理器已独立完成 Methane 自然语言600°C工况冷启动、衡算和进程清理验收。
- 内置连接管理器已独立完成 Coal 自然语言1400°C工况冷启动、外推警告和进程清理验收。
- Toluene 自然语言40%与60%参数矩阵已串行通过，两次均独立启动、清理且 seed 不变。
- Methane 自然语言710°C参数工况已通过，并与600°C结果完成趋势和衡算对比。
- Methane 自然语言550°C低温边界已通过，形成550/600/710°C一致趋势矩阵。
- Coal 自然语言1200°C边界已通过；外推幅度降低200°C，但组成几乎不变，继续标记为受限。
- 严格 JSON CaseSpec 文件输入已完成离线实现，复用现有契约并与其他输入源互斥。
- JSON CaseSpec 已通过 Toluene dry-run 与 live run，确认复用同一执行链且 seed 不变。
- 原题自然语言兼容层已离线支持 MPa 换算、CH4:H2O 比例、扩展温度/浓度措辞和未消费参数保护。
- Methane 双出口温度可生成顺序 ComparisonPlan，并已离线实现逐工况独立会话执行和统一 ComparisonResult；尚未授权真实批量 live run。
- 原题 Coal 的 80000 Nm3/h 会在启动 HYSYS 前明确澄清，不再由默认浆料流量掩盖。

## 当前边界

- Toluene 的 HYSYS 模型仍以 p-Xylene 表示总二甲苯；o/m/p 已能显式输出，但属于假设推导；
- Coal 1400°C 结果数学收敛但处于热力学数据外推区，不能宣称已完成工程验证；
- `.hsc` seed 不进入 Git，全新 clone 仍需要单独交付和校验；
- 自然语言入口目前采用确定性规则，三个场景均已完成实机运行验收；
- 三场景默认工况、参数矩阵和 JSON live run 均已完成；最终演示彩排尚未完成；
- 可选 LLM 解析尚未实现。
- ComparisonPlan live 执行器与 ComparisonResult 已完成模拟会话回归，尚未进行真实 HYSYS 验收。

## 后续任务规划

### P0：自然语言主链验收

1. 用户确认 HYSYS 已完全关闭后，分别执行三个自然语言默认工况冷启动；
2. 检查解析后的 CaseSpec、stdout、stderr、CaseResult、seed 哈希和进程退出；
3. 对边界表达、缺单位和冲突参数做离线回归，确认澄清时绝不启动 HYSYS。

Toluene、Methane 与 Coal 均已通过 CLI 内置连接管理器。下一步进入参数矩阵，继续逐次串行
访问 HYSYS COM。

### P0：二甲苯异构体实机回归

`xylene_split`、默认等比例、自然语言/CLI 覆盖和推导标志均已完成实机验收。三个推导流量之和
与 HYSYS 中作为总二甲苯使用的 p-Xylene 流量完全一致，并明确标记为假设推导。

### P1：seed 可交付性

manifest、只读校验脚本和 clone 后恢复说明已经完成。交付前仍需把三个 seed 放入受控发布包，
做独立备份，并在目标机器运行一次 `verify_seeds.py --pretty`。

### P1：接口与回归矩阵

1. JSON CaseSpec 文件输入已完成离线实现和 Toluene live run 验收；
2. Toluene 40%、50%、60%转化率已完成；
3. Methane 550°C、600°C、710°C矩阵已完成；
4. Coal 1400°C默认工况与1200°C边界工况已完成；
5. 统一检查 JSON schema、退出码、衡算阈值、警告、seed 不变性与无残留进程。

### P2：最终演示

准备三条代表性自然语言命令及一条澄清式失败命令，完成一次全新环境彩排，并保留终端、
HYSYS 页面和结果 JSON 的证据。可选 LLM 只作为后续增强，不能替代确定性安全校验。
