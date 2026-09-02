"""Read-only verification of locally delivered HYSYS seed files."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parent
DEFAULT_MANIFEST = REPOSITORY_ROOT / "seed_manifest.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_manifest(manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    base_dir = manifest_path.resolve().parent
    results: list[dict[str, Any]] = []
    for entry in manifest["seeds"]:
        relative_path = Path(entry["path"])
        target = (base_dir / relative_path).resolve()
        expected = str(entry["sha256"]).lower()
        if not target.is_file():
            status = "missing"
            actual = None
        else:
            actual = sha256(target)
            status = "verified" if actual == expected else "hash_mismatch"
        results.append(
            {
                "scenario": entry["scenario"],
                "path": relative_path.as_posix(),
                "status": status,
                "expected_sha256": expected,
                "actual_sha256": actual,
            }
        )
    overall = "verified" if all(item["status"] == "verified" for item in results) else "failed"
    return {"schema_version": manifest["schema_version"], "status": overall, "seeds": results}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    result = verify_manifest(args.manifest)
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2 if args.pretty else None,
            separators=None if args.pretty else (",", ":"),
        )
    )
    return 0 if result["status"] == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
