from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from core.errors import HysysConnectionError
from core.hysys_connection import _extract_executable, managed_hysys


class FakeProcess:
    def __init__(self, return_code: int | None = None) -> None:
        self.pid = 1234
        self.return_code = return_code

    def poll(self) -> int | None:
        return self.return_code


class HysysConnectionTests(unittest.TestCase):
    def test_extracts_quoted_and_unquoted_registered_executable(self) -> None:
        self.assertEqual(
            _extract_executable('"C:\\Aspen HYSYS\\aspenhysys.exe" /Automation'),
            Path("C:\\Aspen HYSYS\\aspenhysys.exe"),
        )
        self.assertEqual(
            _extract_executable("C:\\Aspen HYSYS\\aspenhysys.exe /Automation"),
            Path("C:\\Aspen HYSYS\\aspenhysys.exe"),
        )

    def test_reuses_active_object_without_owning_process(self) -> None:
        active = object()
        with (
            patch("core.hysys_connection._get_active_object", return_value=active),
            patch("core.hysys_connection._launch_hysys") as launch,
            patch("core.hysys_connection._shutdown_owned_process") as shutdown,
        ):
            with managed_hysys() as connection:
                self.assertFalse(connection.started_by_manager)
                self.assertIsNone(connection.process_id)
        launch.assert_not_called()
        shutdown.assert_not_called()

    def test_normal_launch_waits_for_active_object_and_cleans_up(self) -> None:
        process = FakeProcess()
        with (
            patch(
                "core.hysys_connection._get_active_object",
                side_effect=(None, object()),
            ),
            patch(
                "core.hysys_connection._registered_executable",
                return_value=Path("hysys.exe"),
            ),
            patch("core.hysys_connection._launch_hysys", return_value=process),
            patch("core.hysys_connection._shutdown_owned_process") as shutdown,
        ):
            with managed_hysys() as connection:
                self.assertTrue(connection.started_by_manager)
                self.assertEqual(connection.process_id, 1234)
        shutdown.assert_called_once_with(process)

    def test_body_failure_still_cleans_up_owned_process(self) -> None:
        process = FakeProcess()
        with (
            patch(
                "core.hysys_connection._get_active_object",
                side_effect=(None, object()),
            ),
            patch(
                "core.hysys_connection._registered_executable",
                return_value=Path("hysys.exe"),
            ),
            patch("core.hysys_connection._launch_hysys", return_value=process),
            patch("core.hysys_connection._shutdown_owned_process") as shutdown,
        ):
            with self.assertRaisesRegex(RuntimeError, "adapter failed"):
                with managed_hysys():
                    raise RuntimeError("adapter failed")
        shutdown.assert_called_once_with(process)

    def test_startup_process_exit_is_explicit_and_still_cleaned_up(self) -> None:
        process = FakeProcess(return_code=41)
        with (
            patch("core.hysys_connection._get_active_object", return_value=None),
            patch(
                "core.hysys_connection._registered_executable",
                return_value=Path("hysys.exe"),
            ),
            patch("core.hysys_connection._launch_hysys", return_value=process),
            patch("core.hysys_connection._shutdown_owned_process") as shutdown,
        ):
            with self.assertRaisesRegex(HysysConnectionError, "exit_code=41"):
                with managed_hysys():
                    self.fail("context must not yield after startup failure")
        shutdown.assert_called_once_with(process)

    def test_registration_timeout_is_explicit_and_still_cleaned_up(self) -> None:
        process = FakeProcess()
        with (
            patch("core.hysys_connection._get_active_object", return_value=None),
            patch(
                "core.hysys_connection._registered_executable",
                return_value=Path("hysys.exe"),
            ),
            patch("core.hysys_connection._launch_hysys", return_value=process),
            patch("core.hysys_connection._shutdown_owned_process") as shutdown,
        ):
            with self.assertRaisesRegex(HysysConnectionError, "within 0 seconds"):
                with managed_hysys(start_timeout_seconds=0):
                    self.fail("context must not yield after timeout")
        shutdown.assert_called_once_with(process)


if __name__ == "__main__":
    unittest.main()
