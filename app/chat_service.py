"""Conversation-oriented facade for the validated HYSYS command line interface."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from core.models import ComparisonPlan
from core.natural_language import ClarificationRequired, parse_text_request


SUI_ROOT = Path(__file__).resolve().parent.parent
RUN_CASE = SUI_ROOT / "run_case.py"
MAX_MESSAGE_CHARS = 12_000
TEMPLATE_NAMES = {
    "toluene_disproportionation": "甲苯歧化（Conversion Reactor）",
    "methane_steam_reforming": "甲烷蒸汽重整（Equilibrium Reactor）",
    "coal_slurry_gasification": "水煤浆气化（Gibbs Reactor）",
}


class ChatServiceError(RuntimeError):
    """A user-facing chat request error."""


def load_dotenv(path: Path) -> None:
    """Load a small .env file without adding a package dependency."""

    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


@dataclass(frozen=True)
class ModelConfig:
    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-flash"
    timeout_seconds: float = 60.0

    @classmethod
    def from_environment(cls) -> "ModelConfig":
        return cls(
            api_key=os.environ.get("HYSYS_LLM_API_KEY", "").strip(),
            base_url=os.environ.get(
                "HYSYS_LLM_BASE_URL", "https://api.deepseek.com"
            ).strip().rstrip("/"),
            model=os.environ.get(
                "HYSYS_LLM_MODEL", "deepseek-v4-flash"
            ).strip(),
            timeout_seconds=float(os.environ.get("HYSYS_LLM_TIMEOUT", "60")),
        )

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)


class OpenAICompatibleModel:
    """Minimal OpenAI-compatible Chat Completions client."""

    def __init__(self, config: ModelConfig) -> None:
        self.config = config

    def _complete(self, messages: list[dict[str, str]], *, json_mode: bool = False) -> str:
        request_payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": 0.1,
            "stream": False,
        }
        if json_mode:
            request_payload["response_format"] = {"type": "json_object"}
        body = json.dumps(request_payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.config.base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json; charset=utf-8",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.config.timeout_seconds
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
            content = payload["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("model returned empty content")
            return content.strip()
        except (OSError, ValueError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise ChatServiceError(f"大模型调用失败：{exc}") from exc

    def explain(self, user_text: str, result: dict[str, Any]) -> str:
        compact_result = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
        messages = [
            {
                "role": "system",
                "content": (
                    "你是化工流程模拟助手。只根据给出的 Aspen HYSYS JSON 结果回答，"
                    "不得虚构数值。先给结论，再列关键工况、指标、衡算误差；"
                    "必须明确复述 warnings 和 assumptions 中重要限制。使用简洁中文。"
                ),
            },
            {
                "role": "user",
                "content": f"用户请求：{user_text}\nHYSYS结果：{compact_result}",
            },
        ]
        return self._complete(messages)

    def resolve_followup(
        self,
        user_text: str,
        previous_request: str,
        previous_result: dict[str, Any],
    ) -> dict[str, str]:
        """Classify a follow-up without granting the model execution authority."""

        result_text = json.dumps(
            previous_result, ensure_ascii=False, separators=(",", ":")
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "你是HYSYS对话路由器。判断用户是在修改/新建仿真，还是询问上一次结果。"
                    "只输出JSON。若需要仿真，输出"
                    '{"action":"simulate","standalone_request":"完整工况中文描述"}；'
                    "若只是解释结果，输出"
                    '{"action":"answer","answer":"基于已有JSON的中文回答"}。'
                    "修改工况时继承上一工况未被修改的参数，但绝不能猜测用户从未给出的单位或数值；"
                    "不得输出代码、命令或第三种action。解释时不得虚构JSON中没有的数值，"
                    "必须保留warnings中的工程限制。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"上一次完整请求：{previous_request}\n"
                    f"上一次结果：{result_text}\n"
                    f"本轮用户消息：{user_text}"
                ),
            },
        ]
        raw = self._complete(messages, json_mode=True)
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE)
        try:
            decision = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ChatServiceError("大模型没有返回有效的追问路由 JSON。") from exc
        if not isinstance(decision, dict) or decision.get("action") not in {
            "simulate",
            "answer",
        }:
            raise ChatServiceError("大模型返回了不支持的追问动作。")
        action = decision["action"]
        field = "standalone_request" if action == "simulate" else "answer"
        value = decision.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ChatServiceError(f"大模型追问结果缺少 {field}。")
        return {"action": action, field: value.strip()}


class SimulationRunner:
    """Run the existing CLI in an isolated process; HYSYS jobs are serialized."""

    _lock = threading.Lock()

    def __init__(self, python_executable: str | None = None) -> None:
        self.python_executable = python_executable or sys.executable

    def run(self, text: str, dry_run: bool) -> tuple[int, dict[str, Any], str]:
        command = [
            self.python_executable,
            str(RUN_CASE),
            "--text",
            text,
            "--output-format",
            "json",
        ]
        if dry_run:
            command.append("--dry-run")
        environment = os.environ.copy()
        if not dry_run:
            try:
                parsed = parse_text_request(text)
            except (ClarificationRequired, ValueError):
                parsed = None
            if parsed is not None and not isinstance(parsed, ComparisonPlan):
                environment["HYSYS_KEEP_RUNNING"] = "1"
        with self._lock:
            completed = subprocess.run(
                command,
                cwd=SUI_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=None,
                check=False,
                env=environment,
            )
        try:
            payload = json.loads(completed.stdout.strip())
        except json.JSONDecodeError as exc:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise ChatServiceError(
                f"仿真程序没有返回有效 JSON（退出码 {completed.returncode}）：{detail[-800:]}"
            ) from exc
        return completed.returncode, payload, completed.stderr.strip()


def _number(value: Any, digits: int = 4) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:.{digits}g}"
    return str(value)


def deterministic_answer(payload: dict[str, Any], dry_run: bool) -> str:
    """Create a useful response even when no remote model is configured."""

    status = payload.get("status")
    if status == "clarification_required":
        questions = payload.get("questions") or [payload.get("error", {}).get("message")]
        return "为了安全地启动 HYSYS，还需要你确认：\n" + "\n".join(
            f"- {item}" for item in questions if item
        )
    if status == "failed":
        error = payload.get("error", {})
        message = str(error.get("message", "未知错误"))
        if "HYSYS failed to start" in message or "did not register" in message:
            return (
                "HYSYS 启动失败，尚未进入工况求解。系统已经自动重试并清理本次启动的"
                "残留进程。请先手动打开一次 HYSYS，确认许可证或启动弹窗后关闭，再重新发送；"
                f"诊断信息：{message}"
            )
        return f"仿真未完成：{message}"
    if status == "dry_run":
        plan = payload.get("comparison_plan") or payload.get("case_spec", {})
        scenario = plan.get("scenario", "未知场景")
        scenario = {
            "toluene_disproportionation": "甲苯歧化",
            "methane_steam_reforming": "甲烷蒸汽重整",
            "coal_slurry_gasification": "水煤浆气化",
        }.get(scenario, scenario)
        return (
            f"参数校验通过，已识别场景：{scenario}。当前是仅校验模式，"
            "尚未启动 HYSYS；关闭“仅校验参数”后再次发送即可执行仿真。"
        )
    if payload.get("execution_mode") == "sequential":
        rows = []
        for item in payload.get("case_summaries", []):
            rows.append(
                f"- {item.get('outlet_temperature_c')} °C：甲烷转化率 "
                f"{_number(item.get('methane_conversion_percent'))}% ，热负荷 "
                f"{_number(item.get('heat_duty_kw'))} kW"
            )
        return "HYSYS 顺序比较仿真已完成，所有工况均收敛。\n" + "\n".join(rows)

    labels = {
        "conversion_percent": "转化率 (%)",
        "methane_conversion_percent": "甲烷转化率 (%)",
        "heat_duty_kw": "热负荷 (kW)",
        "co_yield_percent": "CO 收率 (%)",
        "carbon_conversion_percent": "碳转化率 (%)",
        "syngas_hydrogen_molar_fraction": "合成气氢摩尔分数",
    }
    metrics = payload.get("metrics", {})
    lines = [
        f"HYSYS 仿真完成并收敛。场景：{payload.get('scenario', '未知')}。",
        *[
            f"- {labels.get(key, key)}：{_number(value)}"
            for key, value in metrics.items()
            if key != "conversion_fraction"
        ],
    ]
    balance = payload.get("balances", {})
    if balance:
        lines.append(
            f"- 质量衡算误差：{_number(balance.get('mass_error_percent'))}%"
        )
    warnings = payload.get("warnings") or []
    if warnings:
        lines.append("注意：" + "；".join(str(item) for item in warnings))
    return "\n".join(lines)


Runner = Callable[[str, bool], tuple[int, dict[str, Any], str]]


class ChatService:
    def __init__(
        self,
        runner: Runner | None = None,
        model: OpenAICompatibleModel | None = None,
    ) -> None:
        self.runner = runner or SimulationRunner().run
        self.model = model
        self._sessions: dict[str, tuple[str, dict[str, Any]]] = {}
        self._sessions_lock = threading.Lock()

    def _context(self, conversation_id: str | None) -> tuple[str, dict[str, Any]] | None:
        if conversation_id is None:
            return None
        if not isinstance(conversation_id, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{1,80}", conversation_id
        ):
            raise ChatServiceError("conversation_id 格式无效。")
        with self._sessions_lock:
            return self._sessions.get(conversation_id)

    def _remember(
        self,
        conversation_id: str | None,
        request_text: str,
        result: dict[str, Any],
    ) -> None:
        if conversation_id is None:
            return
        with self._sessions_lock:
            if len(self._sessions) >= 100 and conversation_id not in self._sessions:
                self._sessions.pop(next(iter(self._sessions)))
            self._sessions[conversation_id] = (request_text, result)

    @staticmethod
    def _template(scenario: Any) -> dict[str, str] | None:
        scenario_id = getattr(scenario, "value", scenario)
        if not isinstance(scenario_id, str) or scenario_id not in TEMPLATE_NAMES:
            return None
        return {"id": scenario_id, "name": TEMPLATE_NAMES[scenario_id]}

    def handle(
        self,
        message: Any,
        dry_run: Any = False,
        conversation_id: Any = None,
    ) -> dict[str, Any]:
        if not isinstance(message, str) or not message.strip():
            raise ChatServiceError("请输入要仿真的工况描述。")
        message = message.strip()
        if len(message) > MAX_MESSAGE_CHARS:
            raise ChatServiceError(f"输入不能超过 {MAX_MESSAGE_CHARS} 个字符。")
        if not isinstance(dry_run, bool):
            raise ChatServiceError("dry_run 必须是布尔值。")

        context = self._context(conversation_id)
        execution_text = message
        interpreted_from_context = False
        routing_warning = None
        # A complete standalone request is authoritative. The model is only
        # needed when the local parser confirms that this turn depends on context.
        standalone_request = True
        parsed_request = None
        try:
            parsed_request = parse_text_request(message)
        except (ClarificationRequired, ValueError):
            standalone_request = False
        if context is not None and self.model is not None and not standalone_request:
            try:
                decision = self.model.resolve_followup(message, context[0], context[1])
                if decision["action"] == "answer":
                    selected_template = self._template(context[1].get("scenario"))
                    return {
                        "ok": True,
                        "answer": decision["answer"],
                        "result": context[1],
                        "exit_code": 0,
                        "model_used": True,
                        "model_warning": None,
                        "logs": "",
                        "simulation_executed": False,
                        "conversation_id": conversation_id,
                        "selected_template": selected_template,
                    }
                execution_text = decision["standalone_request"]
                interpreted_from_context = execution_text != message
                try:
                    parsed_request = parse_text_request(execution_text)
                except (ClarificationRequired, ValueError):
                    parsed_request = None
            except ChatServiceError as exc:
                # A routing outage must not prevent a complete standalone request.
                execution_text = message
                routing_warning = f"{exc}；本轮已按独立请求处理。"

        exit_code, payload, logs = self.runner(execution_text, dry_run)
        selected_template = self._template(
            getattr(parsed_request, "scenario", None) or payload.get("scenario")
        )
        answer = deterministic_answer(payload, dry_run)
        model_warning = routing_warning
        if exit_code == 0 and not dry_run and self.model is not None:
            try:
                answer = self.model.explain(message, payload)
            except ChatServiceError as exc:
                fallback_warning = str(exc) + "；已使用本地结果摘要。"
                model_warning = (
                    f"{model_warning} {fallback_warning}"
                    if model_warning
                    else fallback_warning
                )
        if exit_code == 0:
            self._remember(conversation_id, execution_text, payload)
        return {
            "ok": exit_code == 0,
            "answer": answer,
            "result": payload,
            "exit_code": exit_code,
            "model_used": self.model is not None and model_warning is None and not dry_run,
            "model_warning": model_warning,
            "logs": logs,
            "simulation_executed": not dry_run and exit_code == 0,
            "interpreted_request": execution_text if interpreted_from_context else None,
            "conversation_id": conversation_id,
            "selected_template": selected_template,
        }
