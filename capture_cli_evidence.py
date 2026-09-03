"""Run the unified CLI and preserve unmodified stdout/stderr evidence."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

from verify_seeds import DEFAULT_MANIFEST, verify_manifest


REPOSITORY_ROOT = Path(__file__).resolve().parent
DEFAULT_CLI = REPOSITORY_ROOT / "run_case.py"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def hysys_pids() -> list[int]:
    """Return AspenHysys process IDs without importing COM or starting HYSYS."""
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "@(Get-Process -Name AspenHysys -ErrorAction SilentlyContinue).Id -join ','",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "cannot inspect AspenHysys processes: " + completed.stderr.strip()
        )
    value = completed.stdout.strip()
    return [] if not value else [int(item) for item in value.split(",")]


def capture(
    evidence_dir: Path,
    cli_arguments: Sequence[str],
    *,
    python_executable: Path | str = sys.executable,
    cli_path: Path = DEFAULT_CLI,
    manifest_path: Path = DEFAULT_MANIFEST,
    pid_reader: Callable[[], list[int]] = hysys_pids,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> int:
    """Capture CLI streams as bytes and emit independently checkable metadata."""
    evidence_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = evidence_dir / "stdout.json"
    stderr_path = evidence_dir / "stderr.log"
    exit_path = evidence_dir / "exit_code.txt"
    metadata_path = evidence_dir / "metadata.json"

    started_at = utc_now()
    pre_pids = pid_reader()
    seeds_before = verify_manifest(manifest_path)
    command = [str(python_executable), str(cli_path), *cli_arguments]
    metadata: dict[str, object] = {
        "started_at_utc": started_at,
        "command": command,
        "hysys_pids_before": pre_pids,
        "seed_verification_before": seeds_before,
    }

    if pre_pids:
        message = f"refusing to run: AspenHysys already active: {pre_pids}\n"
        stdout_path.write_bytes(b"")
        stderr_path.write_bytes(message.encode("utf-8"))
        exit_code = 1
    elif seeds_before["status"] != "verified":
        stdout_path.write_bytes(b"")
        stderr_path.write_bytes(b"refusing to run: seed verification failed\n")
        exit_code = 1
    else:
        with stdout_path.open("wb") as stdout_stream, stderr_path.open(
            "wb"
        ) as stderr_stream:
            completed = runner(
                command,
                cwd=REPOSITORY_ROOT,
                stdout=stdout_stream,
                stderr=stderr_stream,
                check=False,
            )
        exit_code = completed.returncode

    post_pids = pid_reader()
    seeds_after = verify_manifest(manifest_path)
    stdout_json_valid = False
    if stdout_path.stat().st_size:
        try:
            json.loads(stdout_path.read_text(encoding="utf-8"))
            stdout_json_valid = True
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass

    evidence_ok = (
        exit_code == 0
        and stdout_json_valid
        and not post_pids
        and seeds_before["status"] == "verified"
        and seeds_after == seeds_before
    )
    final_exit_code = 0 if evidence_ok else (exit_code if exit_code else 1)
    exit_path.write_text(f"{final_exit_code}\n", encoding="ascii")
    metadata.update(
        {
            "finished_at_utc": utc_now(),
            "cli_exit_code": exit_code,
            "evidence_exit_code": final_exit_code,
            "stdout_json_valid": stdout_json_valid,
            "hysys_pids_after": post_pids,
            "seed_verification_after": seeds_after,
            "seed_unchanged": seeds_after == seeds_before,
            "evidence_status": "verified" if evidence_ok else "failed",
        }
    )
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return final_exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument(
        "cli_arguments",
        nargs=argparse.REMAINDER,
        help="Arguments for run_case.py; place them after --.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cli_arguments = list(args.cli_arguments)
    if cli_arguments[:1] == ["--"]:
        cli_arguments.pop(0)
    if not cli_arguments:
        raise SystemExit("run_case.py arguments are required after --")
    return capture(
        args.evidence_dir,
        cli_arguments,
        python_executable=args.python,
    )


if __name__ == "__main__":
    raise SystemExit(main())
