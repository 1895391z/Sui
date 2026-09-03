from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from chat_service import (
    ChatService,
    ChatServiceError,
    ModelConfig,
    deterministic_answer,
    load_dotenv,
)


class ChatServiceTests(unittest.TestCase):
    def test_rejects_empty_message_without_running(self) -> None:
        calls = []
        service = ChatService(runner=lambda text, dry: calls.append((text, dry)))
        with self.assertRaisesRegex(ChatServiceError, "请输入"):
            service.handle("  ")
        self.assertEqual(calls, [])

    def test_dry_run_is_forwarded_and_summarized(self) -> None:
        def runner(text: str, dry_run: bool):
            self.assertEqual(text, "运行甲苯歧化默认工况")
            self.assertTrue(dry_run)
            return 0, {
                "status": "dry_run",
                "case_spec": {"scenario": "toluene_disproportionation"},
            }, ""

        response = ChatService(runner=runner).handle(
            "运行甲苯歧化默认工况", dry_run=True
        )
        self.assertTrue(response["ok"])
        self.assertIn("参数校验通过", response["answer"])
        self.assertFalse(response["model_used"])
        self.assertEqual(response["selected_template"]["name"], "甲苯歧化（Conversion Reactor）")

    def test_clarification_is_returned_as_normal_chat_response(self) -> None:
        service = ChatService(
            runner=lambda text, dry: (
                2,
                {
                    "status": "clarification_required",
                    "questions": ["压力请提供 bar 或 MPa。"],
                },
                "",
            )
        )
        response = service.handle("甲苯压力25")
        self.assertFalse(response["ok"])
        self.assertIn("压力请提供", response["answer"])

    def test_success_summary_contains_metrics_and_balance(self) -> None:
        text = deterministic_answer(
            {
                "status": "success",
                "scenario": "methane_steam_reforming",
                "metrics": {
                    "methane_conversion_percent": 72.5,
                    "heat_duty_kw": 120.0,
                },
                "balances": {"mass_error_percent": 0.001},
                "warnings": [],
            },
            False,
        )
        self.assertIn("72.5", text)
        self.assertIn("质量衡算", text)

    def test_dotenv_does_not_overwrite_existing_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("HYSYS_LLM_MODEL=from-file\n", encoding="utf-8")
            with patch.dict(os.environ, {"HYSYS_LLM_MODEL": "existing"}, clear=False):
                load_dotenv(path)
                self.assertEqual(os.environ["HYSYS_LLM_MODEL"], "existing")

    def test_model_config_defaults_to_disabled_without_key(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            config = ModelConfig.from_environment()
        self.assertFalse(config.enabled)
        self.assertEqual(config.base_url, "https://api.deepseek.com")

    def test_result_question_uses_session_without_running_hysys_again(self) -> None:
        calls = []

        class FakeModel:
            def explain(self, user_text, result):
                return "首次结果"

            def resolve_followup(self, user_text, previous_request, previous_result):
                return {"action": "answer", "answer": "因为升温促进吸热重整反应。"}

        def runner(text, dry_run):
            calls.append((text, dry_run))
            return 0, {"status": "success", "scenario": "methane_steam_reforming"}, ""

        service = ChatService(runner=runner, model=FakeModel())
        service.handle("甲烷重整出口710°C", conversation_id="test-session")
        response = service.handle("为什么转化率提高？", conversation_id="test-session")
        self.assertEqual(response["answer"], "因为升温促进吸热重整反应。")
        self.assertFalse(response["simulation_executed"])
        self.assertEqual(len(calls), 1)

    def test_parameter_followup_becomes_complete_validated_request(self) -> None:
        calls = []

        class FakeModel:
            def explain(self, user_text, result):
                return "仿真完成"

            def resolve_followup(self, user_text, previous_request, previous_result):
                return {
                    "action": "simulate",
                    "standalone_request": (
                        "甲烷蒸汽重整，总进料100 kgmol/h，S/C 2.7，"
                        "进料温度520°C，压力13.5 bar，出口温度600°C"
                    ),
                }

        def runner(text, dry_run):
            calls.append(text)
            return 0, {"status": "success", "scenario": "methane_steam_reforming"}, ""

        service = ChatService(runner=runner, model=FakeModel())
        service.handle("甲烷重整出口710°C", conversation_id="test-session")
        response = service.handle("改成600°C再算", conversation_id="test-session")
        self.assertIn("出口温度600°C", calls[-1])
        self.assertEqual(response["interpreted_request"], calls[-1])
        self.assertTrue(response["simulation_executed"])

    def test_invalid_conversation_id_is_rejected(self) -> None:
        with self.assertRaisesRegex(ChatServiceError, "conversation_id"):
            ChatService(runner=lambda text, dry: None).handle(
                "甲苯歧化", conversation_id="bad id!"
            )

    def test_complete_request_bypasses_context_rewriting(self) -> None:
        calls = []

        class ModelThatMustNotRoute:
            def resolve_followup(self, *args):
                raise AssertionError("complete request must bypass model routing")

            def explain(self, user_text, result):
                return "仿真完成"

        def runner(text, dry_run):
            calls.append(text)
            return 0, {"status": "success", "scenario": "toluene_disproportionation"}, ""

        service = ChatService(runner=runner, model=ModelThatMustNotRoute())
        service.handle("甲烷蒸汽重整默认工况", conversation_id="same-page")
        full_request = (
            "请完成甲苯歧化，进料流量10000 kg/h，进料温度380°C，"
            "操作压力2.5 MPa，甲苯转化率50%"
        )
        service.handle(full_request, conversation_id="same-page")
        self.assertEqual(calls[-1], full_request)
        self.assertEqual(
            service.handle(full_request, conversation_id="same-page")["selected_template"]["id"],
            "toluene_disproportionation",
        )


if __name__ == "__main__":
    unittest.main()
