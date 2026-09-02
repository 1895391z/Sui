from __future__ import annotations

import unittest

from core.errors import AdapterExecutionError, ResultValidationError
from core.models import CaseSpec, Scenario, TolueneInputs
from core.service import execute_case


class ServiceBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = CaseSpec(Scenario.TOLUENE, TolueneInputs())

    def test_adapter_exception_is_wrapped(self) -> None:
        def failing_runner(spec: CaseSpec) -> dict[str, object]:
            raise OSError("COM unavailable")

        with self.assertRaisesRegex(AdapterExecutionError, "COM unavailable"):
            execute_case(self.spec, runners={Scenario.TOLUENE: failing_runner})

    def test_invalid_native_result_is_wrapped(self) -> None:
        def invalid_runner(spec: CaseSpec) -> dict[str, object]:
            return {"converged": False}

        with self.assertRaisesRegex(ResultValidationError, "result validation failed"):
            execute_case(self.spec, runners={Scenario.TOLUENE: invalid_runner})


if __name__ == "__main__":
    unittest.main()
