# 水煤浆气化 Gibbs Reactor 验证记录

验证日期：2026-09-02

HYSYS：Aspen HYSYS V15

物性包：Peng-Robinson

进料：1000 kg/h，40°C，40 bar；其中纯碳近似煤620 kg/h，水380 kg/h

出口指定温度：1400°C

## 模型结构

| 对象 | 实际名称 | TypeName | 说明 |
|---|---|---|---|
| Gibbs Reactor | `GBR-100` | `gibbsreactorop` | `ReactorType=3`，即 `gr_GibbsRxnsOnly` |
| 进料 | `Feed` | `materialstream` | 62 wt% Carbon，38 wt% H2O |
| 蒸气出口 | `Syngas_Out` | `materialstream` | 蒸气分率1.0 |
| 非蒸气出口 | `Bottom_Out` | `materialstream` | 蒸气分率0.0，纯 Carbon |
| 能量流 | `Q_Heat` | `energystream` | 维持指定出口温度 |

组分顺序为 `Hydrogen / H2O / CO / CO2 / Methane / Carbon`。Carbon 的数据库记录为有效纯组分，
`IsSolid=True`，CAS 为7440-44-0。反应器所有惰性组分标志均为0，没有固定产率或固定组分分率。

HYSYS COM 将非蒸气出口暴露为 `LiquidProduct`，但出口本身蒸气分率为0且只含标记为固体的 Carbon。
因此不能只根据 COM 端口名称判断 Carbon 被作为液体处理。

## 默认工况结果

| 指标 | 结果 |
|---|---:|
| CO 摩尔流量 | 21.093415 kgmol/h |
| CH4 摩尔流量 | 10.546704 kgmol/h |
| H2 摩尔流量 | 0.00000781 kgmol/h |
| 残余 Carbon | 19.980088 kgmol/h |
| CO 收率 | 40.862710% |
| 碳转化率 | 61.294058% |
| 热负荷 | 1487.580836 kW |
| 总质量衡算误差 | 0.002214% |
| C 元素衡算误差 | 约9.64e-14% |
| H 元素衡算误差 | 约1.26e-7% |
| O 元素衡算误差 | 约1.26e-7% |

## 冷启动与重复性

默认工况先完成一次无人触碰冷启动，随后完成三次具有完整日志和退出码的正式连续重复测试。

| 正式轮次 | 求解尝试次数 | 执行时间 | CO 收率 | 碳转化率 | 热负荷 |
|---:|---:|---:|---:|---:|---:|
| 1/3 | 1 | 3.71 s | 40.862710% | 61.294058% | 1487.580836 kW |
| 2/3 | 1 | 3.73 s | 40.862710% | 61.294058% | 1487.580836 kW |
| 3/3 | 1 | 4.06 s | 40.862710% | 61.294058% | 1487.580836 kW |

三轮关键数值逐位一致，数值重复性偏差为0。每轮均完成以下状态：

```text
RUNTIME_COPY_OK
OPEN_CASE_OK
VALIDATE_MODEL_OK
WRITE_INPUT_OK
SOLVED_OK
RESULT_READ_OK: attempt=1
RUNTIME_CASE_SAVED_OK
CLOSE_CASE_OK
RUN_COAL_GASIFICATION_CASE_OK
```

正式三轮开始前，编排层曾启动一轮但没有返回完整日志；该轮正常结束但不计入上述可审计结果。

## 高温 Gibbs 数据限制

只读 COM 深度探查显示，六个组分报告的 `GibbsTmaxValue` 均为426.85°C，而反应器出口指定为
1400°C，超出该上限973.15°C。HYSYS仍然返回收敛结果，但属于超出组件 Gibbs 数据标记范围的
高温外推。

1400°C下 CH4 仍占合成气约33.33 mol%，H2摩尔分数却仅约2.47e-7；该趋势不应在没有独立
热力学验证的情况下作为真实煤气化预测使用。因此结果状态必须区分为：

- HYSYS/COM 数学求解：通过；
- 自动化、输入回读和衡算：通过；
- 重复性：通过；
- 高温热力学工程有效性：尚未独立验证。

适配器会动态读取每个组分的 `GibbsTmaxValue`，比较出口温度，并在超限时输出
`THERMODYNAMIC_VALIDITY_WARNING`。JSON 结果同时包含 `thermodynamic_validity`、
`engineering_validated=false` 和 `warnings`，避免将数学收敛误报为物理可信。

新增警告后又执行了一次真实 COM 默认工况回归。该次运行首次求解成功，终端输出973.15°C
超限警告，JSON 返回六个组分的上限均为426.85°C、
`within_reported_component_gibbs_range=false` 和 `engineering_validated=false`，随后正常保存
runtime 并关闭案例。

## 本地 seed

```text
cases/constant/coal_gasification_seed.hsc
SHA-256: F88D2CD59DA5156C8A2D324691C0AC7D6DBB7A4BD852604EEC3BDCD88D9448AB
```

`Sui/cases` 整体由 `.gitignore` 排除。每次运行仅修改 runtime 副本，并在结束前再次检查 seed
哈希。本记录不表示1400°C平衡组成已经获得独立实验或高温数据库验证。
