from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from verify_seeds import verify_manifest


class SeedVerifierTests(unittest.TestCase):
    def write_manifest(self, root: Path, expected_hash: str) -> Path:
        manifest = root / "seed_manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "seeds": [
                        {
                            "scenario": "test",
                            "path": "cases/constant/test.hsc",
                            "sha256": expected_hash,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return manifest

    def test_verified_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed = root / "cases" / "constant" / "test.hsc"
            seed.parent.mkdir(parents=True)
            seed.write_bytes(b"seed")
            expected = hashlib.sha256(b"seed").hexdigest()
            result = verify_manifest(self.write_manifest(root, expected))
            self.assertEqual(result["status"], "verified")

    def test_missing_and_hash_mismatch_are_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self.write_manifest(root, "0" * 64)
            missing = verify_manifest(manifest)
            self.assertEqual(missing["seeds"][0]["status"], "missing")
            seed = root / "cases" / "constant" / "test.hsc"
            seed.parent.mkdir(parents=True)
            seed.write_bytes(b"different")
            mismatch = verify_manifest(manifest)
            self.assertEqual(mismatch["seeds"][0]["status"], "hash_mismatch")


if __name__ == "__main__":
    unittest.main()
