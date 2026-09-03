from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.capture_cli_evidence import capture


class CaptureCliEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        seed = self.root / "seed.hsc"
        seed.write_bytes(b"immutable seed")
        import hashlib

        digest = hashlib.sha256(seed.read_bytes()).hexdigest()
        self.manifest = self.root / "seed_manifest.json"
        self.manifest.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "seeds": [
                        {
                            "scenario": "test",
                            "path": "seed.hsc",
                            "sha256": digest,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_preserves_raw_streams_and_writes_verified_metadata(self) -> None:
        pid_snapshots = iter(([], []))

        def fake_runner(command, *, cwd, stdout, stderr, check):
            self.assertFalse(check)
            stdout.write('{"status":"success"}\n'.encode("utf-8"))
            stderr.write("第一行日志\nSOLVED_OK\n".encode("utf-8"))
            return subprocess.CompletedProcess(command, 0)

        evidence_dir = self.root / "evidence"
        exit_code = capture(
            evidence_dir,
            ["--dry-run"],
            manifest_path=self.manifest,
            pid_reader=lambda: next(pid_snapshots),
            runner=fake_runner,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            (evidence_dir / "stderr.log").read_bytes(),
            "第一行日志\nSOLVED_OK\n".encode("utf-8"),
        )
        metadata = json.loads(
            (evidence_dir / "metadata.json").read_text(encoding="utf-8")
        )
        self.assertEqual(metadata["evidence_status"], "verified")
        self.assertTrue(metadata["stdout_json_valid"])
        self.assertTrue(metadata["seed_unchanged"])

    def test_refuses_to_run_when_hysys_is_already_active(self) -> None:
        runner_called = False

        def fake_runner(*args, **kwargs):
            nonlocal runner_called
            runner_called = True
            raise AssertionError("runner must not be called")

        evidence_dir = self.root / "evidence"
        exit_code = capture(
            evidence_dir,
            ["--dry-run"],
            manifest_path=self.manifest,
            pid_reader=lambda: [1234],
            runner=fake_runner,
        )

        self.assertEqual(exit_code, 1)
        self.assertFalse(runner_called)
        self.assertIn(
            "AspenHysys already active",
            (evidence_dir / "stderr.log").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
