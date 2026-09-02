"""Deterministic natural-language parsing for the three supported scenarios."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .models import CaseSpec, CoalInputs, MethaneInputs, Scenario, TolueneInputs


NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)"


@dataclass(frozen=True)
class ClarificationRequired(ValueError):
    """The request is safe to clarify but not safe to execute."""

    message: str
    questions: tuple[str, ...]

    def __str__(self) -> str:
        return self.message


SCENARIO_ALIASES: dict[Scenario, tuple[str, ...]] = {
    Scenario.TOLUENE: (
        "toluene",
        "甲苯",
        "歧化",
        "disproportionation",
    ),
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


def _matches(text: str, pattern: str) -> list[tuple[float, str | None]]:
    return [
        (float(match.group("value")), match.groupdict().get("unit"))
        for match in re.finditer(pattern, text, flags=re.IGNORECASE)
    ]


def _one_value(
    field: str,
    matches: list[tuple[float, str | None]],
    questions: list[str],
) -> tuple[float, str | None] | None:
    if not matches:
        return None
    distinct = {(value, unit or "") for value, unit in matches}
    if len(distinct) > 1:
        questions.append(f"{field} 出现多个不同数值，请只保留一个。")
        return None
    return matches[0]


def _require_unit(
    field: str,
    item: tuple[float, str | None] | None,
    questions: list[str],
    expected: str,
) -> float | None:
    if item is None:
        return None
    value, unit = item
    if not unit:
        questions.append(f"请为 {field} 补充单位（{expected}）。")
        return None
    return value


def _fraction(
    field: str,
    item: tuple[float, str | None] | None,
    questions: list[str],
) -> float | None:
    if item is None:
        return None
    value, unit = item
    if unit:
        return value / 100.0
    if 0.0 <= value <= 1.0:
        return value
    questions.append(f"{field} 大于1时必须使用 % 或 wt% 标明百分数。")
    return None


def _extract_common(text: str, scenario: Scenario, questions: list[str]) -> dict[str, float]:
    values: dict[str, float] = {}
    pressure = _one_value(
        "压力",
        _matches(
            text,
            rf"(?:压力|pressure)\s*(?:为|是|=|:)?\s*(?P<value>{NUMBER})\s*(?P<unit>bar|巴)?",
        ),
        questions,
    )
    pressure_value = _require_unit("压力", pressure, questions, "bar")
    if pressure_value is not None:
        values["pressure_bar"] = pressure_value

    feed_temperature = _one_value(
        "进料温度",
        _matches(
            text,
            rf"(?:进料|入口|feed|inlet)\s*(?:温度|temperature|temp)?\s*(?:为|是|=|:)?\s*(?P<value>{NUMBER})\s*(?P<unit>°?c|摄氏度)?",
        ),
        questions,
    )
    feed_value = _require_unit("进料温度", feed_temperature, questions, "°C")
    if feed_value is not None:
        values["feed_temperature_c"] = feed_value

    outlet_temperature = _one_value(
        "出口温度",
        _matches(
            text,
            rf"(?:出口|反应器出口|outlet)\s*(?:温度|temperature|temp)?\s*(?:为|是|=|:)?\s*(?P<value>{NUMBER})\s*(?P<unit>°?c|摄氏度)?",
        ),
        questions,
    )
    outlet_value = _require_unit("出口温度", outlet_temperature, questions, "°C")
    if outlet_value is not None:
        values["outlet_temperature_c"] = outlet_value

    all_temperature_values = {
        value
        for value, _unit in _matches(
            text, rf"(?P<value>{NUMBER})\s*(?P<unit>°c|c|摄氏度)"
        )
    }
    labelled_temperature_values = {
        item[0]
        for item in (feed_temperature, outlet_temperature)
        if item is not None
    }
    if labelled_temperature_values and (
        all_temperature_values - labelled_temperature_values
    ):
        questions.append("存在未说明用途的额外温度，请明确它是进料温度还是出口温度。")

    if feed_temperature is None and outlet_temperature is None:
        generic_temperatures = _matches(
            text, rf"(?P<value>{NUMBER})\s*(?P<unit>°c|c|摄氏度)"
        )
        generic = _one_value("温度", generic_temperatures, questions)
        generic_value = _require_unit("温度", generic, questions, "°C")
        if generic_value is not None:
            key = (
                "feed_temperature_c"
                if scenario is Scenario.TOLUENE
                else "outlet_temperature_c"
            )
            values[key] = generic_value
    return values


def _toluene_inputs(text: str, questions: list[str], common: dict[str, float]) -> TolueneInputs:
    values = dict(common)
    flow = _one_value(
        "甲苯进料质量流量",
        _matches(
            text,
            rf"(?:进料(?:质量)?流量|质量流量|feed(?: mass)? flow)\s*(?:为|是|=|:)?\s*(?P<value>{NUMBER})\s*(?P<unit>kg\s*/\s*h|kg\s*/\s*hr)?",
        ),
        questions,
    )
    flow_value = _require_unit("甲苯进料质量流量", flow, questions, "kg/h")
    if flow_value is not None:
        values["feed_mass_flow_kg_h"] = flow_value
    conversion = _one_value(
        "甲苯转化率",
        _matches(
            text,
            rf"(?:(?:甲苯)?转化率|conversion)\s*(?:为|是|=|:)?\s*(?P<value>{NUMBER})\s*(?P<unit>%|percent)?",
        ),
        questions,
    )
    conversion_value = _fraction("甲苯转化率", conversion, questions)
    if conversion_value is not None:
        values["conversion"] = conversion_value
    return TolueneInputs(**values)


def _methane_inputs(text: str, questions: list[str], common: dict[str, float]) -> MethaneInputs:
    values = dict(common)
    flow = _one_value(
        "总进料摩尔流量",
        _matches(
            text,
            rf"(?:总进料(?:摩尔)?流量|摩尔流量|total feed(?: molar)? flow)\s*(?:为|是|=|:)?\s*(?P<value>{NUMBER})\s*(?P<unit>kgmol\s*/\s*h|kmol\s*/\s*h|kgmole\s*/\s*h)?",
        ),
        questions,
    )
    flow_value = _require_unit("总进料摩尔流量", flow, questions, "kgmol/h")
    if flow_value is not None:
        values["total_feed_molar_flow_kgmole_h"] = flow_value
    ratio = _one_value(
        "蒸汽碳比",
        _matches(
            text,
            rf"(?:s\s*/\s*c|h2o\s*/\s*ch4|蒸汽碳比|水碳比)\s*(?:为|是|=|:)?\s*(?P<value>{NUMBER})(?P<unit>)",
        ),
        questions,
    )
    if ratio is not None:
        values["steam_to_carbon_ratio"] = ratio[0]
    return MethaneInputs(**values)


def _coal_inputs(text: str, questions: list[str], common: dict[str, float]) -> CoalInputs:
    values = dict(common)
    flow = _one_value(
        "水煤浆质量流量",
        _matches(
            text,
            rf"(?:水煤浆|煤浆|slurry)\s*(?:进料)?(?:质量)?流量\s*(?:为|是|=|:)?\s*(?P<value>{NUMBER})\s*(?P<unit>kg\s*/\s*h|kg\s*/\s*hr)?",
        ),
        questions,
    )
    flow_value = _require_unit("水煤浆质量流量", flow, questions, "kg/h")
    if flow_value is not None:
        values["slurry_mass_flow_kg_h"] = flow_value
    fraction = _one_value(
        "煤质量分数",
        _matches(
            text,
            rf"(?:煤浆浓度|煤质量分数|coal mass fraction|slurry concentration)\s*(?:为|是|=|:)?\s*(?P<value>{NUMBER})\s*(?P<unit>wt%|%)?",
        ),
        questions,
    )
    fraction_value = _fraction("煤质量分数", fraction, questions)
    if fraction_value is not None:
        values["coal_mass_fraction"] = fraction_value
    return CoalInputs(**values)


def parse_text_to_spec(raw_text: str) -> CaseSpec:
    """Parse one request or raise a structured clarification before execution."""

    text = _normalize(raw_text)
    if not text:
        raise ClarificationRequired("自然语言请求不能为空。", ("请描述要运行的场景和工况。",))
    scenario = _scenario_from_text(text)
    questions: list[str] = []
    common = _extract_common(text, scenario, questions)
    try:
        if scenario is Scenario.TOLUENE:
            inputs = _toluene_inputs(text, questions, common)
        elif scenario is Scenario.METHANE:
            inputs = _methane_inputs(text, questions, common)
        else:
            inputs = _coal_inputs(text, questions, common)
    except ValueError as exc:
        questions.append(str(exc))
        inputs = None
    if questions:
        raise ClarificationRequired(
            "自然语言请求存在歧义或缺少必要单位，未启动 HYSYS。",
            tuple(dict.fromkeys(questions)),
        )
    assert inputs is not None
    return CaseSpec(scenario=scenario, inputs=inputs)
