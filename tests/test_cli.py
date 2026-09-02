from __future__ import annotations

import json
import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import run_case


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

    def test_natural_language_clarification_never_executes_adapter(self) -> None:
        with patch.object(run_case, "execute_case") as execute:
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = run_case.main(["--text", "运行甲苯歧化，压力 25"])
        self.assertEqual(exit_code, 2)
        execute.assert_not_called()
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
