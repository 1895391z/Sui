from __future__ import annotations

import sys
import unittest

from core.models import CaseSpec, CoalInputs, Scenario
from core.registry import dispatch_native


class RegistryTests(unittest.TestCase):
    def test_injected_runner_avoids_adapter_import(self) -> None:
        spec = CaseSpec(Scenario.COAL, CoalInputs())
        seen: list[CaseSpec] = []

        def fake_runner(actual: CaseSpec) -> dict[str, object]:
            seen.append(actual)
            return {"marker": "fake"}

        result = dispatch_native(spec, runners={Scenario.COAL: fake_runner})
        self.assertEqual(result, {"marker": "fake"})
        self.assertEqual(seen, [spec])
        self.assertNotIn("adapters.coal.coal_gasification_adapter", sys.modules)

    def test_missing_registration_fails_explicitly(self) -> None:
        spec = CaseSpec(Scenario.COAL, CoalInputs())
        with self.assertRaisesRegex(ValueError, "No runner registered"):
            dispatch_native(spec, runners={})


if __name__ == "__main__":
    unittest.main()
