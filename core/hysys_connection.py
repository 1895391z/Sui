"""Lifecycle manager for HYSYS instances used by the unified CLI.

COM imports are deliberately delayed until a live execution enters the context.
This keeps validation and ``--dry-run`` independent of HYSYS and pywin32.
"""

from __future__ import annotations

import ctypes
import gc
import os
import re
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from .errors import HysysConnectionError


PROG_ID = "HYSYS.Application"
DEFAULT_START_TIMEOUT_SECONDS = 60.0
DEFAULT_POLL_INTERVAL_SECONDS = 1.0
DEFAULT_SHUTDOWN_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class HysysConnection:
    started_by_manager: bool
    process_id: int | None


def _get_active_object() -> Any | None:
    try:
        import pythoncom
        import win32com.client
    except ImportError as exc:
        raise HysysConnectionError(
            f"pywin32 is required for live HYSYS execution: {exc}"
        ) from exc
    try:
        return win32com.client.GetActiveObject(PROG_ID)
    except pythoncom.com_error:
        return None


def _extract_executable(command: str) -> Path:
    match = re.match(r'^\s*"(?P<quoted>[^"]+\.exe)"', command, re.IGNORECASE)
    if match:
        return Path(match.group("quoted"))
    match = re.match(r"^\s*(?P<plain>.+?\.exe)(?:\s|$)", command, re.IGNORECASE)
    if not match:
        raise HysysConnectionError(
            f"Cannot extract HYSYS executable from LocalServer32={command!r}"
        )
    return Path(match.group("plain"))


def _registered_executable() -> Path:
    configured = os.environ.get("HYSYS_EXE_PATH")
    if configured:
        executable = Path(configured)
    else:
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CLASSES_ROOT, rf"{PROG_ID}\CLSID"
            ) as key:
                clsid, _ = winreg.QueryValueEx(key, None)
            with winreg.OpenKey(
                winreg.HKEY_CLASSES_ROOT, rf"CLSID\{clsid}\LocalServer32"
            ) as key:
                command, _ = winreg.QueryValueEx(key, None)
        except (OSError, ImportError) as exc:
            raise HysysConnectionError(
                f"Cannot read the {PROG_ID} LocalServer32 registration: {exc}"
            ) from exc
        executable = _extract_executable(str(command))
    if not executable.is_file():
        raise HysysConnectionError(f"HYSYS executable does not exist: {executable}")
    return executable


def _launch_hysys(executable: Path) -> subprocess.Popen[bytes]:
    try:
        return subprocess.Popen(
            [str(executable)],
            cwd=str(executable.parent),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise HysysConnectionError(
            f"Cannot normally launch HYSYS executable {executable}: {exc}"
        ) from exc


def _post_close_to_windows(process_id: int) -> None:
    if os.name != "nt":
        return
    user32 = ctypes.windll.user32
    enum_callback = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def close_window(window: int, _parameter: int) -> bool:
        owner = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(window, ctypes.byref(owner))
        if owner.value == process_id:
            user32.PostMessageW(window, 0x0010, 0, 0)  # WM_CLOSE
        return True

    user32.EnumWindows(enum_callback(close_window), 0)


def _shutdown_owned_process(
    process: subprocess.Popen[bytes],
    timeout_seconds: float = DEFAULT_SHUTDOWN_TIMEOUT_SECONDS,
) -> None:
    if process.poll() is not None:
        return
    _post_close_to_windows(process.pid)
    try:
        process.wait(timeout=timeout_seconds)
        return
    except subprocess.TimeoutExpired:
        process.terminate()
    try:
        process.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5.0)


@contextmanager
def managed_hysys(
    *,
    start_timeout_seconds: float = DEFAULT_START_TIMEOUT_SECONDS,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
) -> Iterator[HysysConnection]:
    """Provide an active HYSYS object, launching normally when none exists."""

    app = _get_active_object()
    if app is not None:
        print("HYSYS_ACTIVE_OBJECT_REUSED")
        try:
            yield HysysConnection(started_by_manager=False, process_id=None)
        finally:
            app = None
            gc.collect()
        return

    executable = _registered_executable()
    process = _launch_hysys(executable)
    print(f"HYSYS_NORMAL_LAUNCH_STARTED: pid={process.pid}")
    app = None
    try:
        deadline = time.monotonic() + start_timeout_seconds
        attempt = 0
        while time.monotonic() < deadline:
            attempt += 1
            return_code = process.poll()
            if return_code is not None:
                raise HysysConnectionError(
                    f"HYSYS exited during normal startup: pid={process.pid}, "
                    f"exit_code={return_code}"
                )
            app = _get_active_object()
            if app is not None:
                print(f"HYSYS_ACTIVE_OBJECT_READY: attempt={attempt}")
                break
            time.sleep(poll_interval_seconds)
        if app is None:
            raise HysysConnectionError(
                f"HYSYS did not register {PROG_ID} within "
                f"{start_timeout_seconds:.0f} seconds"
            )
        yield HysysConnection(started_by_manager=True, process_id=process.pid)
    finally:
        app = None
        gc.collect()
        _shutdown_owned_process(process)
        print(f"HYSYS_LAUNCHED_PROCESS_CLOSED: pid={process.pid}")
