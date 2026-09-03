"""Deterministic natural-language parsing for the three supported scenarios."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, replace

from .models import (
    CaseSpec,
    CoalInputs,
    ComparisonPlan,
    MethaneInputs,
    Scenario,
    TolueneInputs,
    XyleneSplit,
)


NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)"
TEMPERATURE_UNIT = r"°?c(?![a-z0-9])|摄氏度|度"


@dataclass(frozen=True)
class ClarificationRequired(ValueError):
    """The request is safe to clarify but not safe to execute."""

    message: str
    questions: tuple[str, ...]

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class ExtractedValue:
    value: float
    unit: str | None
    span: tuple[int, int]


@dataclass
class ExtractionAudit:
    """Track consumed engineering values so explicit inputs cannot be ignored."""

    text: str
    consumed_spans: list[tuple[int, int]]

    @classmethod
    def for_text(cls, text: str) -> ExtractionAudit:
        return cls(text=text, consumed_spans=[])

    def consume(self, matches: list[ExtractedValue]) -> None:
        self.consumed_spans.extend(item.span for item in matches)

    def questions_for_unconsumed_values(self) -> list[str]:
        unit_pattern = (
            r"nm(?:3|³)\s*/\s*(?:h|hr)|sm(?:3|³)\s*/\s*(?:h|hr)|"
            r"m(?:3|³)\s*/\s*(?:s|min|h|hr)|l\s*/\s*(?:s|min|h|hr)|"
            r"kgmole\s*/\s*(?:s|h)|kgmol\s*/\s*(?:s|h)|"
            r"kmol\s*/\s*(?:s|h)|mol\s*/\s*(?:s|h)|"
            r"kg\s*/\s*(?:s|min|h|hr)|g\s*/\s*(?:s|min|h|hr)|"
            r"t\s*/\s*(?:h|hr|d)|mpa|kpa|bara|barg|bar|atm|pa|巴|"
            r"wt%|mol%|vol%|%|°c|摄氏度|度|c(?![a-z0-9])|"
            r"kelvin|k(?![a-z0-9])|°f|f(?![a-z0-9])"
        )
        pattern = rf"(?<![a-z0-9_.])(?P<value>{NUMBER})\s*(?P<unit>{unit_pattern})"
        questions: list[str] = []
        for match in re.finditer(pattern, self.text, flags=re.IGNORECASE):
            if any(
                start <= match.start() and match.end() <= end
                for start, end in self.consumed_spans
            ):
                continue
            value = match.group("value")
            unit = re.sub(r"\s+", "", match.group("unit")).lower()
            if unit.startswith("nm3/") or unit.startswith("nm³/"):
                questions.append(
                    f"检测到 {value} Nm3/h；标准气体体积流量不能直接作为水煤浆质量流量，"
                    "请提供水煤浆质量流量（kg/h）或明确换算基准。"
                )
            else:
                questions.append(
                    f"检测到未被当前场景识别的工程参数“{match.group(0)}”；"
                    "请明确参数含义并使用支持的单位。"
                )
        return questions


SCENARIO_ALIASES: dict[Scenario, tuple[str, ...]] = {
    Scenario.TOLUENE: ("toluene", "甲苯", "歧化", "disproportionation"),
    Scenario.METHANE: (
        "methane",
        "甲烷",
        "蒸汽重整",
        "steam reforming",
        "steam-reforming",
    ),
    Scenario.COAL: (
        "coal gasification",
        "coal slurry",
        "水煤浆",
        "煤气化",
        "气化炉",
    ),
}


def _normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).lower().split())


def _scenario_from_text(text: str) -> Scenario:
    matches = {
        scenario
        for scenario, aliases in SCENARIO_ALIASES.items()
        if any(alias in text for alias in aliases)
    }
    if len(matches) == 1:
        return next(iter(matches))
    if not matches:
        raise ClarificationRequired(
            "无法确定要运行的场景。",
            ("请明确指定甲苯歧化、甲烷蒸汽重整或水煤浆气化。",),
        )
    names = "、".join(sorted(item.value for item in matches))
    raise ClarificationRequired(
        f"请求同时匹配多个场景：{names}。",
        ("一次请求只能运行一个场景，请明确选择其中一个。",),
    )


def _matches(text: str, pattern: str) -> list[ExtractedValue]:
    return [
        ExtractedValue(
            value=float(match.group("value")),
            unit=match.groupdict().get("unit"),
            span=match.span(),
        )
        for match in re.finditer(pattern, text, flags=re.IGNORECASE)
    ]


def _unit_key(unit: str | None) -> str:
    if unit is None:
        return ""
    compact = re.sub(r"\s+", "", unit).lower()
    if compact in {"°c", "c", "摄氏度", "度"}:
        return "c"
    if compact in {"bar", "巴"}:
        return "bar"
    return compact


def _one_value(
    field: str,
    matches: list[ExtractedValue],
    questions: list[str],
) -> ExtractedValue | None:
    if not matches:
        return None
    distinct = {(item.value, _unit_key(item.unit)) for item in matches}
    if len(distinct) > 1:
        questions.append(f"{field} 出现多个不同数值，请只保留一个。")
        return None
    return matches[0]


def _required_value(
    field: str,
    item: ExtractedValue | None,
    matches: list[ExtractedValue],
    questions: list[str],
    audit: ExtractionAudit,
    expected: str,
) -> float | None:
    if item is None:
        return None
    if not item.unit:
        questions.append(f"请为 {field} 补充单位（{expected}）。")
        return None
    audit.consume(matches)
    return item.value


def _fraction(
    field: str,
    item: ExtractedValue | None,
    matches: list[ExtractedValue],
    questions: list[str],
    audit: ExtractionAudit,
) -> float | None:
    if item is None:
        return None
    if item.unit:
        audit.consume(matches)
        return item.value / 100.0
    if 0.0 <= item.value <= 1.0:
        return item.value
    questions.append(f"{field} 大于1时必须使用 % 或 wt% 标明百分数。")
    return None


def _unique_values(matches: list[ExtractedValue]) -> list[float]:
    values: list[float] = []
    for item in matches:
        if item.value not in values:
            values.append(item.value)
    return values


def _extract_common(
    text: str,
    scenario: Scenario,
    questions: list[str],
    audit: ExtractionAudit,
) -> tuple[dict[str, float], tuple[float, ...]]:
    values: dict[str, float] = {}

    pressure_matches = _matches(
        text,
        rf"(?:压力|pressure)\s*(?:为|是|=|:)?\s*(?P<value>{NUMBER})\s*"
        rf"(?P<unit>mpa|bar|巴)?",
    )
    pressure = _one_value("压力", pressure_matches, questions)
    pressure_value = _required_value(
        "压力", pressure, pressure_matches, questions, audit, "bar 或 MPa"
    )
    if pressure_value is not None and pressure is not None:
        values["pressure_bar"] = (
            pressure_value * 10.0
            if _unit_key(pressure.unit) == "mpa"
            else pressure_value
        )

    feed_matches = _matches(
        text,
        rf"(?:进料|入口|feed|inlet)\s*(?:气)?\s*"
        rf"(?:温度|temperature|temp)?\s*(?:为|是|=|:)?\s*"
        rf"(?P<value>{NUMBER})\s*(?P<unit>{TEMPERATURE_UNIT})?",
    )
    feed_temperature = _one_value("进料温度", feed_matches, questions)
    feed_value = _required_value(
        "进料温度", feed_temperature, feed_matches, questions, audit, "°C"
    )
    if feed_value is not None:
        values["feed_temperature_c"] = feed_value

    outlet_matches = _matches(
        text,
        rf"(?:(?:反应器|重整炉|气化炉)?出口|outlet)\s*(?:气)?\s*"
        rf"(?:温度|temperature|temp)?\s*(?:为|是|=|:)?\s*"
        rf"(?P<value>{NUMBER})\s*(?P<unit>{TEMPERATURE_UNIT})?",
    )
    outlet_values = _unique_values(outlet_matches)
    comparison_temperatures: tuple[float, ...] = ()
    if scenario is Scenario.METHANE and len(outlet_values) > 1:
        if any(not item.unit for item in outlet_matches):
            questions.append("请为每个出口温度补充单位（°C）。")
        else:
            audit.consume(outlet_matches)
            comparison_temperatures = tuple(outlet_values)
    else:
        outlet_temperature = _one_value("出口温度", outlet_matches, questions)
        outlet_value = _required_value(
            "出口温度",
            outlet_temperature,
            outlet_matches,
            questions,
            audit,
            "°C",
        )
        if outlet_value is not None:
            values["outlet_temperature_c"] = outlet_value

    all_temperature_matches = _matches(
        text, rf"(?<![a-z0-9_.])(?P<value>{NUMBER})\s*(?P<unit>{TEMPERATURE_UNIT})"
    )
    all_temperature_values = {item.value for item in all_temperature_matches}
    labelled_temperature_values = {
        item.value for item in (*feed_matches, *outlet_matches)
    }
    if labelled_temperature_values and (
        all_temperature_values - labelled_temperature_values
    ):
        questions.append("存在未说明用途的额外温度，请明确它是进料温度还是出口温度。")

    if not feed_matches and not outlet_matches:
        generic = _one_value("温度", all_temperature_matches, questions)
        generic_value = _required_value(
            "温度", generic, all_temperature_matches, questions, audit, "°C"
        )
        if generic_value is not None:
            key = (
                "feed_temperature_c"
                if scenario is Scenario.TOLUENE
                else "outlet_temperature_c"
            )
            values[key] = generic_value
    return values, comparison_temperatures


def _toluene_inputs(
    text: str,
    questions: list[str],
    common: dict[str, float],
    audit: ExtractionAudit,
) -> TolueneInputs:
    values = dict(common)
    flow_matches = _matches(
        text,
        rf"(?:进料(?:质量)?流量|质量流量|feed(?: mass)? flow)\s*"
        rf"(?:为|是|=|:)?\s*(?P<value>{NUMBER})\s*"
        rf"(?P<unit>kg\s*/\s*h|kg\s*/\s*hr)?",
    )
    flow = _one_value("甲苯进料质量流量", flow_matches, questions)
    flow_value = _required_value(
        "甲苯进料质量流量", flow, flow_matches, questions, audit, "kg/h"
    )
    if flow_value is not None:
        values["feed_mass_flow_kg_h"] = flow_value

    conversion_matches = _matches(
        text,
        rf"(?:(?:甲苯)?转化率|conversion)\s*(?:为|是|=|:)?\s*"
        rf"(?P<value>{NUMBER})\s*(?P<unit>%|percent)?",
    )
    conversion = _one_value("甲苯转化率", conversion_matches, questions)
    conversion_value = _fraction(
        "甲苯转化率", conversion, conversion_matches, questions, audit
    )
    if conversion_value is not None:
        values["conversion"] = conversion_value

    split_match = re.search(
        rf"(?:o\s*/\s*m\s*/\s*p|邻\s*/\s*间\s*/\s*对(?:二甲苯)?(?:比例)?)"
        rf"\s*(?:为|是|=|:)?\s*(?P<o>{NUMBER})\s*%?\s*/\s*"
        rf"(?P<m>{NUMBER})\s*%?\s*/\s*(?P<p>{NUMBER})\s*%?",
        text,
        flags=re.IGNORECASE,
    )
    if split_match:
        audit.consumed_spans.append(split_match.span())
        parts = [float(split_match.group(name)) for name in ("o", "m", "p")]
        total = sum(parts)
        if total <= 0.0:
            questions.append("o/m/p 二甲苯比例之和必须大于0。")
        else:
            values["xylene_split"] = XyleneSplit(
                o_xylene=parts[0] / total,
                m_xylene=parts[1] / total,
                p_xylene=parts[2] / total,
            )
    return TolueneInputs(**values)


def _methane_ratio(text: str, questions: list[str]) -> float | None:
    direct_matches = _matches(
        text,
        rf"(?:s\s*/\s*c|h2o\s*/\s*ch4|蒸汽碳比|水碳比)\s*"
        rf"(?:为|是|=|:)?\s*(?P<value>{NUMBER})(?P<unit>)",
    )
    candidates = [item.value for item in direct_matches]
    ordered = re.search(
        rf"甲烷\s*(?:和|与|/)\s*水蒸气[^。；;]{{0,20}}?摩尔比\s*"
        rf"(?:为|是|=|:)?\s*(?P<methane>{NUMBER})\s*[:/]\s*"
        rf"(?P<steam>{NUMBER})",
        text,
        flags=re.IGNORECASE,
    )
    if ordered:
        methane = float(ordered.group("methane"))
        steam = float(ordered.group("steam"))
        if methane <= 0.0:
            questions.append("CH4:H2O 摩尔比中的 CH4 数值必须大于0。")
        else:
            candidates.append(steam / methane)
    distinct = list(dict.fromkeys(candidates))
    if len(distinct) > 1:
        questions.append("蒸汽碳比出现多个不同数值，请只保留一个。")
        return None
    return distinct[0] if distinct else None


def _methane_inputs(
    text: str,
    questions: list[str],
    common: dict[str, float],
    audit: ExtractionAudit,
) -> MethaneInputs:
    values = dict(common)
    flow_matches = _matches(
        text,
        rf"(?:总进料(?:摩尔)?流量|摩尔流量|total feed(?: molar)? flow)\s*"
        rf"(?:为|是|=|:)?\s*(?P<value>{NUMBER})\s*"
        rf"(?P<unit>kgmol\s*/\s*h|kmol\s*/\s*h|kgmole\s*/\s*h)?",
    )
    flow = _one_value("总进料摩尔流量", flow_matches, questions)
    flow_value = _required_value(
        "总进料摩尔流量", flow, flow_matches, questions, audit, "kgmol/h"
    )
    if flow_value is not None:
        values["total_feed_molar_flow_kgmole_h"] = flow_value
    ratio = _methane_ratio(text, questions)
    if ratio is not None:
        values["steam_to_carbon_ratio"] = ratio
    return MethaneInputs(**values)


def _coal_inputs(
    text: str,
    questions: list[str],
    common: dict[str, float],
    audit: ExtractionAudit,
) -> CoalInputs:
    values = dict(common)
    flow_matches = _matches(
        text,
        rf"(?:水煤浆|煤浆|slurry)\s*(?:进料)?(?:质量)?流量\s*"
        rf"(?:为|是|=|:)?\s*(?P<value>{NUMBER})\s*"
        rf"(?P<unit>kg\s*/\s*h|kg\s*/\s*hr)?",
    )
    flow = _one_value("水煤浆质量流量", flow_matches, questions)
    flow_value = _required_value(
        "水煤浆质量流量", flow, flow_matches, questions, audit, "kg/h"
    )
    if flow_value is not None:
        values["slurry_mass_flow_kg_h"] = flow_value

    fraction_matches = _matches(
        text,
        rf"(?:水?煤浆(?:进料)?浓度|煤质量分数|coal mass fraction|"
        rf"slurry concentration)\s*(?:为|是|=|:)?\s*"
        rf"(?P<value>{NUMBER})\s*(?P<unit>wt%|%)?",
    )
    fraction = _one_value("煤质量分数", fraction_matches, questions)
    fraction_value = _fraction(
        "煤质量分数", fraction, fraction_matches, questions, audit
    )
    if fraction_value is not None:
        values["coal_mass_fraction"] = fraction_value
    return CoalInputs(**values)


def parse_text_request(raw_text: str) -> CaseSpec | ComparisonPlan:
    """Parse one natural-language request into a case or dry-run comparison plan."""

    text = _normalize(raw_text)
    if not text:
        raise ClarificationRequired("自然语言请求不能为空。", ("请描述要运行的场景和工况。",))
    scenario = _scenario_from_text(text)
    questions: list[str] = []
    audit = ExtractionAudit.for_text(text)
    common, comparison_temperatures = _extract_common(
        text, scenario, questions, audit
    )
    try:
        if scenario is Scenario.TOLUENE:
            inputs = _toluene_inputs(text, questions, common, audit)
        elif scenario is Scenario.METHANE:
            inputs = _methane_inputs(text, questions, common, audit)
        else:
            inputs = _coal_inputs(text, questions, common, audit)
    except ValueError as exc:
        questions.append(str(exc))
        inputs = None

    questions.extend(audit.questions_for_unconsumed_values())
    if questions:
        raise ClarificationRequired(
            "自然语言请求存在歧义、未支持的工程参数或缺少必要单位，未启动 HYSYS。",
            tuple(dict.fromkeys(questions)),
        )
    assert inputs is not None
    if comparison_temperatures:
        assert isinstance(inputs, MethaneInputs)
        case_specs = tuple(
            CaseSpec(
                scenario=Scenario.METHANE,
                inputs=replace(inputs, outlet_temperature_c=temperature),
            )
            for temperature in comparison_temperatures
        )
        return ComparisonPlan(
            scenario=Scenario.METHANE,
            case_specs=case_specs,
            comparison_field="outlet_temperature_c",
            assumptions=(
                "各工况使用相同进料，仅顺序比较出口温度影响。",
                "原题未给定数值流量时，采用100 kgmol/h归一化计算基准；实际工厂规模需另行确认。",
            ),
        )
    return CaseSpec(scenario=scenario, inputs=inputs)


def parse_text_to_spec(raw_text: str) -> CaseSpec:
    """Parse one request through the backward-compatible single-case API."""

    request = parse_text_request(raw_text)
    if isinstance(request, ComparisonPlan):
        raise ClarificationRequired(
            "自然语言请求包含多个比较工况，单工况接口未执行。",
            ("检测到多个比较工况，请使用统一 CLI --dry-run 查看顺序 ComparisonPlan。",),
        )
    return request
