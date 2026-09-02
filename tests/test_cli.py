from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


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
        self.assertEqual(payload["error"]["type"], "ValueError")

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


if __name__ == "__main__":
    unittest.main()
