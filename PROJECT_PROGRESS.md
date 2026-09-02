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

## 当前边界

- Toluene 的 HYSYS 模型仍以 p-Xylene 表示总二甲苯；o/m/p 已能显式输出，但属于假设推导；
- Coal 1400°C 结果数学收敛但处于热力学数据外推区，不能宣称已完成工程验证；
- `.hsc` seed 不进入 Git，全新 clone 仍需要单独交付和校验；
- 自然语言入口目前为确定性规则，尚未获得三场景实机运行授权；
- JSON CaseSpec 文件输入和可选 LLM 解析尚未实现。

## 后续任务规划

### P0：自然语言主链验收

1. 用户确认 HYSYS 已完全关闭后，分别执行三个自然语言默认工况冷启动；
2. 检查解析后的 CaseSpec、stdout、stderr、CaseResult、seed 哈希和进程退出；
3. 对边界表达、缺单位和冲突参数做离线回归，确认澄清时绝不启动 HYSYS。

### P0：二甲苯异构体实机回归

`xylene_split`、默认等比例、自然语言/CLI 覆盖和推导标志已完成离线实现。下一步在用户确认
HYSYS 完全关闭后执行一次 Toluene 回归，核对总二甲苯质量流量与三个推导流量之和一致。

### P1：seed 可交付性

manifest、只读校验脚本和 clone 后恢复说明已经完成。交付前仍需把三个 seed 放入受控发布包，
做独立备份，并在目标机器运行一次 `verify_seeds.py --pretty`。

### P1：接口与回归矩阵

1. 自然语言链稳定后再实现 JSON CaseSpec 文件输入；
2. Toluene 验证40%、50%、60%转化率；
3. Methane 验证600°C、710°C及至少一个边界工况；
4. Coal 验证默认工况及一个边界工况；
5. 统一检查 JSON schema、退出码、衡算阈值、警告、seed 不变性与无残留进程。

### P2：最终演示

准备三条代表性自然语言命令及一条澄清式失败命令，完成一次全新环境彩排，并保留终端、
HYSYS 页面和结果 JSON 的证据。可选 LLM 只作为后续增强，不能替代确定性安全校验。
