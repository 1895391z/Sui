from __future__ import annotations

import json
import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager, nullcontext, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import run_case
from core.errors import HysysConnectionError
from tests.test_natural_language import (
    COAL_ASSESSMENT_TEXT,
    METHANE_ASSESSMENT_TEXT,
    TOLUENE_ASSESSMENT_TEXT,
)


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
CLI_PATH = REPOSITORY_ROOT / "run_case.py"


def run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI_PATH), *arguments],
        cwd=REPOSITORY_ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


class CliDryRunTests(unittest.TestCase):
    def test_assessment_toluene_text_dry_run(self) -> None:
        completed = run_cli(
            "--text", TOLUENE_ASSESSMENT_TEXT, "--dry-run", "--output-format", "pretty"
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["case_spec"]["inputs"]["pressure_bar"], 25.0)

    def test_assessment_methane_comparison_is_dry_run_only(self) -> None:
        completed = run_cli(
            "--text", METHANE_ASSESSMENT_TEXT, "--dry-run", "--output-format", "pretty"
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "dry_run")
        plan = payload["comparison_plan"]
        self.assertEqual(plan["execution_mode"], "sequential")
        self.assertEqual(
            [item["inputs"]["outlet_temperature_c"] for item in plan["case_specs"]],
            [710.0, 600.0],
        )

        with (
            patch.object(run_case, "execute_case") as execute,
            patch.object(run_case, "managed_hysys") as manager,
        ):
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = run_case.main(["--text", METHANE_ASSESSMENT_TEXT])
        self.assertEqual(exit_code, 2)
        execute.assert_not_called()
        manager.assert_not_called()
        self.assertEqual(json.loads(stdout.getvalue())["status"], "failed")

    def test_assessment_coal_clarification_never_starts_hysys(self) -> None:
        with (
            patch.object(run_case, "execute_case") as execute,
            patch.object(run_case, "managed_hysys") as manager,
        ):
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = run_case.main(
                    ["--text", COAL_ASSESSMENT_TEXT, "--dry-run"]
                )
        self.assertEqual(exit_code, 2)
        execute.assert_not_called()
        manager.assert_not_called()
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "clarification_required")
        self.assertIn("Nm3/h", "".join(payload["questions"]))

    def write_case_spec(self, directory: str, spec: dict[str, object]) -> Path:
        path = Path(directory) / "case_spec.json"
        path.write_text(json.dumps(spec), encoding="utf-8")
        return path

    def test_json_case_spec_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            spec = run_case.CaseSpec(
                run_case.Scenario.METHANE,
                run_case.MethaneInputs(outlet_temperature_c=710.0),
            )
            path = self.write_case_spec(directory, spec.to_dict())
            completed = run_cli(
                "--case-spec", str(path), "--dry-run", "--output-format", "pretty"
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "dry_run")
        self.assertEqual(
            payload["case_spec"]["inputs"]["outlet_temperature_c"], 710.0
        )

    def test_json_case_spec_is_mutually_exclusive_with_other_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            spec = run_case.CaseSpec(
                run_case.Scenario.COAL,
                run_case.CoalInputs(),
            )
            path = self.write_case_spec(directory, spec.to_dict())
            completed = run_cli(
                "--case-spec", str(path), "--text", "运行水煤浆气化", "--dry-run"
            )
            subcommand = run_cli(
                "--case-spec", str(path), "coal", "--dry-run"
            )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)["error"]["type"], "CliInputError")
        self.assertEqual(subcommand.returncode, 2)
        self.assertEqual(json.loads(subcommand.stdout)["error"]["type"], "CliInputError")

    def test_json_case_spec_errors_are_exit_two(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            malformed = Path(directory) / "malformed.json"
            malformed.write_text("{invalid", encoding="utf-8")
            malformed_result = run_cli("--case-spec", str(malformed), "--dry-run")
            missing_result = run_cli(
                "--case-spec", str(Path(directory) / "missing.json"), "--dry-run"
            )
        self.assertEqual(malformed_result.returncode, 2)
        self.assertEqual(missing_result.returncode, 2)
        self.assertEqual(
            json.loads(malformed_result.stdout)["error"]["type"], "CliInputError"
        )
        self.assertEqual(
            json.loads(missing_result.stdout)["error"]["type"], "CliInputError"
        )

    def test_json_dry_run_never_enters_hysys_manager(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            spec = run_case.CaseSpec(
                run_case.Scenario.TOLUENE,
                run_case.TolueneInputs(),
            )
            path = self.write_case_spec(directory, spec.to_dict())
            with patch.object(run_case, "managed_hysys") as manager:
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    exit_code = run_case.main(
                        ["--case-spec", str(path), "--dry-run"]
                    )
        self.assertEqual(exit_code, 0)
        manager.assert_not_called()

    def test_natural_language_dry_run_builds_case_spec(self) -> None:
        completed = run_cli(
            "--text",
            "甲苯歧化，进料流量 12000 kg/h，压力 26 bar，转化率 60%",
            "--dry-run",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "dry_run")
        self.assertEqual(payload["case_spec"]["inputs"]["conversion"], 0.6)

    def test_explicit_xylene_split_is_normalized_in_dry_run(self) -> None:
        completed = run_cli(
            "toluene", "--xylene-split", "20,30,50", "--dry-run"
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        split = json.loads(completed.stdout)["case_spec"]["inputs"]["xylene_split"]
        self.assertEqual(split, {"o_xylene": 0.2, "m_xylene": 0.3, "p_xylene": 0.5})

    def test_natural_language_clarification_never_executes_adapter(self) -> None:
        with (
            patch.object(run_case, "execute_case") as execute,
            patch.object(run_case, "managed_hysys") as manager,
        ):
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = run_case.main(["--text", "运行甲苯歧化，压力 25"])
        self.assertEqual(exit_code, 2)
        execute.assert_not_called()
        manager.assert_not_called()
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "clarification_required")
        self.assertTrue(payload["questions"])

    def test_all_scenarios_dry_run_without_adapter_import(self) -> None:
        expected = {
            "toluene": "toluene_disproportionation",
            "methane": "methane_steam_reforming",
            "coal": "coal_slurry_gasification",
        }
        for command, scenario in expected.items():
            with self.subTest(command=command):
                completed = run_cli(command, "--dry-run")
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertEqual(completed.stderr, "")
                payload = json.loads(completed.stdout)
                self.assertEqual(payload["status"], "dry_run")
                self.assertEqual(payload["case_spec"]["scenario"], scenario)

    def test_dry_run_does_not_enter_hysys_manager(self) -> None:
        with patch.object(run_case, "managed_hysys") as manager:
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = run_case.main(["coal", "--dry-run"])
        self.assertEqual(exit_code, 0)
        manager.assert_not_called()

    def test_connection_failure_is_exit_four_with_parsed_scenario(self) -> None:
        with patch.object(
            run_case,
            "managed_hysys",
            side_effect=HysysConnectionError("startup failed"),
        ):
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = run_case.main(["--text", "运行甲苯歧化默认工况"])
        self.assertEqual(exit_code, 4)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["scenario"], "toluene_disproportionation")
        self.assertEqual(payload["error"]["type"], "HysysConnectionError")

    def test_connection_and_adapter_logs_stay_on_stderr(self) -> None:
        class FakeResult:
            def to_dict(self) -> dict[str, object]:
                return {"schema_version": "1.0", "status": "success"}

        @contextmanager
        def fake_manager():
            print("HYSYS_NORMAL_LAUNCH_STARTED: pid=1234")
            yield
            print("HYSYS_LAUNCHED_PROCESS_CLOSED: pid=1234")

        def fake_execute(_spec):
            print("ADAPTER_OK")
            return FakeResult()

        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch.object(run_case, "managed_hysys", fake_manager),
            patch.object(run_case, "execute_case", fake_execute),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            exit_code = run_case.main(["toluene"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["status"], "success")
        self.assertNotIn("HYSYS_", stdout.getvalue())
        self.assertIn("HYSYS_NORMAL_LAUNCH_STARTED", stderr.getvalue())
        self.assertIn("ADAPTER_OK", stderr.getvalue())

    def test_semantic_input_error_is_json_and_exit_two(self) -> None:
        completed = run_cli("toluene", "--conversion", "1.5", "--dry-run")
        self.assertEqual(completed.returncode, 2)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["error"]["type"], "CliInputError")

    def test_argparse_type_error_is_json_and_exit_two(self) -> None:
        completed = run_cli("coal", "--pressure-bar", "not-a-number", "--dry-run")
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stderr, "")
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["error"]["type"], "CliInputError")

    def test_pretty_output_file_matches_stdout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "case.json"
            completed = run_cli(
                "methane",
                "--outlet-temperature-c",
                "710",
                "--dry-run",
                "--output-format",
                "pretty",
                "--output-file",
                str(output),
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(output.read_text(encoding="utf-8"), completed.stdout)
            self.assertEqual(
                json.loads(completed.stdout)["case_spec"]["inputs"]
                ["outlet_temperature_c"],
                710.0,
            )

    def test_unwritable_output_target_falls_back_to_error_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            completed = run_cli(
                "coal", "--dry-run", "--output-file", directory
            )
            self.assertEqual(completed.returncode, 1)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "failed")
            self.assertEqual(payload["error"]["type"], "PermissionError")

    def test_chinese_success_payload_reconfigures_stdout_to_utf8(self) -> None:
        class FakeResult:
            def to_dict(self) -> dict[str, object]:
                return {
                    "schema_version": "1.0",
                    "status": "success",
                    "selection_reason": "已知甲苯转化率且不要求动力学",
                    "assumptions": ["中文输出必须保持有效JSON"],
                }

        stdout_bytes = io.BytesIO()
        stderr_bytes = io.BytesIO()
        stdout = io.TextIOWrapper(stdout_bytes, encoding="cp1252")
        stderr = io.TextIOWrapper(stderr_bytes, encoding="cp1252")
        with (
            patch.object(sys, "stdout", stdout),
            patch.object(sys, "stderr", stderr),
            patch.object(run_case, "execute_case", return_value=FakeResult()),
            patch.object(run_case, "managed_hysys", return_value=nullcontext()),
        ):
            exit_code = run_case.main(["toluene"])
            stdout.flush()
            stderr.flush()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout_bytes.getvalue().decode("utf-8"))
        self.assertEqual(payload["selection_reason"], "已知甲苯转化率且不要求动力学")
        self.assertEqual(stdout.encoding, "utf-8")
        self.assertEqual(stderr.encoding, "utf-8")

    def test_unicode_encode_error_is_not_classified_as_input(self) -> None:
        error = UnicodeEncodeError("ascii", "中", 0, 1, "unsupported")
        self.assertEqual(run_case.exit_code_for(error), run_case.EXIT_UNEXPECTED)


if __name__ == "__main__":
    unittest.main()
