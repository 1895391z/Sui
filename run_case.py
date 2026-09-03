"""Unified command-line entry point for the three fixed HYSYS scenarios."""

from __future__ import annotations

import argparse
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

from core.errors import (
    AdapterExecutionError,
    HysysConnectionError,
    ResultValidationError,
)
from core.hysys_connection import managed_hysys
from core.models import (
    SCHEMA_VERSION,
    CaseSpec,
    CoalInputs,
    ComparisonPlan,
    MethaneInputs,
    Scenario,
    TolueneInputs,
    XyleneSplit,
)
from core.service import execute_case
from core.natural_language import ClarificationRequired, parse_text_request


EXIT_OK = 0
EXIT_UNEXPECTED = 1
EXIT_INPUT = 2
EXIT_MISSING_SEED = 3
EXIT_ADAPTER = 4
EXIT_RESULT = 5


class CliInputError(ValueError):
    """An argparse error represented through the normal JSON failure envelope."""


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CliInputError(message)


def configure_standard_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")


def add_output_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--output-format",
        choices=("json", "pretty"),
        default="json",
        help="Use compact JSON or indented JSON output (default: json).",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        help="Also write the same JSON payload to this file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print CaseSpec without importing an adapter or starting HYSYS.",
    )


def xylene_split_argument(value: str) -> XyleneSplit:
    try:
        parts = [float(item.strip()) for item in value.split(",")]
        if len(parts) != 3 or sum(parts) <= 0.0:
            raise ValueError
        total = sum(parts)
        return XyleneSplit(*(item / total for item in parts))
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError(
            "xylene split must contain three non-negative comma-separated values"
        ) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(
        description="Run a validated fixed-scenario HYSYS case through one unified CLI."
    )
    parser.add_argument(
        "--text",
        help="Parse one Chinese or English natural-language case request.",
    )
    parser.add_argument(
        "--case-spec",
        type=Path,
        help="Read one strict UTF-8 CaseSpec JSON file.",
    )
    add_output_arguments(parser)
    subparsers = parser.add_subparsers(dest="command")

    toluene = subparsers.add_parser("toluene", help="Toluene disproportionation")
    toluene.add_argument("--feed-mass-flow-kg-h", type=float, default=10000.0)
    toluene.add_argument("--feed-temperature-c", type=float, default=380.0)
    toluene.add_argument("--pressure-bar", type=float, default=25.0)
    toluene.add_argument("--conversion", type=float, default=0.50)
    toluene.add_argument(
        "--xylene-split",
        type=xylene_split_argument,
        default=XyleneSplit(),
        metavar="O,M,P",
        help="Assumed o-/m-/p-xylene split; values are normalized to sum to one.",
    )
    add_output_arguments(toluene)

    methane = subparsers.add_parser("methane", help="Methane steam reforming")
    methane.add_argument(
        "--total-feed-molar-flow-kgmole-h", type=float, default=100.0
    )
    methane.add_argument("--steam-to-carbon-ratio", type=float, default=2.7)
    methane.add_argument("--feed-temperature-c", type=float, default=520.0)
    methane.add_argument("--pressure-bar", type=float, default=13.5)
    methane.add_argument("--outlet-temperature-c", type=float, default=600.0)
    add_output_arguments(methane)

    coal = subparsers.add_parser("coal", help="Coal-slurry steam gasification")
    coal.add_argument("--slurry-mass-flow-kg-h", type=float, default=1000.0)
    coal.add_argument("--coal-mass-fraction", type=float, default=0.62)
    coal.add_argument("--feed-temperature-c", type=float, default=40.0)
    coal.add_argument("--pressure-bar", type=float, default=40.0)
    coal.add_argument("--outlet-temperature-c", type=float, default=1400.0)
    add_output_arguments(coal)
    return parser


def build_spec(args: argparse.Namespace) -> CaseSpec | ComparisonPlan:
    source_count = sum(
        source is not None
        for source in (args.text, args.case_spec, args.command)
    )
    if source_count != 1:
        raise CliInputError(
            "provide exactly one input source: --text, --case-spec, "
            "or a scenario subcommand"
        )
    if args.text is not None:
        return parse_text_request(args.text)
    if args.case_spec is not None:
        return load_case_spec(args.case_spec)
    if args.command == "toluene":
        return CaseSpec(
            scenario=Scenario.TOLUENE,
            inputs=TolueneInputs(
                feed_mass_flow_kg_h=args.feed_mass_flow_kg_h,
                feed_temperature_c=args.feed_temperature_c,
                pressure_bar=args.pressure_bar,
                conversion=args.conversion,
                xylene_split=args.xylene_split,
            ),
        )
    if args.command == "methane":
        return CaseSpec(
            scenario=Scenario.METHANE,
            inputs=MethaneInputs(
                total_feed_molar_flow_kgmole_h=(
                    args.total_feed_molar_flow_kgmole_h
                ),
                steam_to_carbon_ratio=args.steam_to_carbon_ratio,
                feed_temperature_c=args.feed_temperature_c,
                pressure_bar=args.pressure_bar,
                outlet_temperature_c=args.outlet_temperature_c,
            ),
        )
    if args.command == "coal":
        return CaseSpec(
            scenario=Scenario.COAL,
            inputs=CoalInputs(
                slurry_mass_flow_kg_h=args.slurry_mass_flow_kg_h,
                coal_mass_fraction=args.coal_mass_fraction,
                feed_temperature_c=args.feed_temperature_c,
                pressure_bar=args.pressure_bar,
                outlet_temperature_c=args.outlet_temperature_c,
            ),
        )
    raise CliInputError("provide --text or a scenario subcommand")


def load_case_spec(path: Path) -> CaseSpec:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CliInputError(f"cannot read CaseSpec file {path}: {exc}") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CliInputError(
            f"invalid CaseSpec JSON in {path}: line {exc.lineno}, "
            f"column {exc.colno}: {exc.msg}"
        ) from exc
    return CaseSpec.from_dict(payload)


def serialize_payload(payload: dict[str, Any], output_format: str) -> str:
    if output_format == "pretty":
        return json.dumps(payload, ensure_ascii=False, indent=2)
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def emit_payload(payload: dict[str, Any], args: argparse.Namespace) -> None:
    text = serialize_payload(payload, args.output_format)
    if args.output_file is not None:
        args.output_file.write_text(text + "\n", encoding="utf-8")
    print(text)


def error_payload(
    args: argparse.Namespace,
    exc: Exception,
    request: CaseSpec | ComparisonPlan | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": (
            "clarification_required"
            if isinstance(exc, ClarificationRequired)
            else "failed"
        ),
        "scenario": (
            request.scenario.value
            if request is not None
            else getattr(args, "command", None)
        ),
        "error": {"type": type(exc).__name__, "message": str(exc)},
    }
    if isinstance(exc, ClarificationRequired):
        payload["questions"] = list(exc.questions)
    return payload


def exit_code_for(exc: Exception) -> int:
    if isinstance(exc, (CliInputError, ClarificationRequired)):
        return EXIT_INPUT
    if isinstance(exc, FileNotFoundError):
        return EXIT_MISSING_SEED
    if isinstance(exc, (AdapterExecutionError, HysysConnectionError)):
        return EXIT_ADAPTER
    if isinstance(exc, ResultValidationError):
        return EXIT_RESULT
    return EXIT_UNEXPECTED


def main(argv: list[str] | None = None) -> int:
    configure_standard_streams()
    parser = build_parser()
    args: argparse.Namespace | None = None
    request: CaseSpec | ComparisonPlan | None = None
    try:
        args = parser.parse_args(argv)
        try:
            request = build_spec(args)
        except ClarificationRequired:
            raise
        except (TypeError, ValueError) as exc:
            raise CliInputError(str(exc)) from exc
        if args.dry_run:
            key = (
                "comparison_plan"
                if isinstance(request, ComparisonPlan)
                else "case_spec"
            )
            emit_payload(
                {
                    "schema_version": SCHEMA_VERSION,
                    "status": "dry_run",
                    key: request.to_dict(),
                },
                args,
            )
            return EXIT_OK

        if isinstance(request, ComparisonPlan):
            raise CliInputError(
                "ComparisonPlan currently supports --dry-run only; "
                "review the sequential cases before live execution"
            )
        spec = request

        adapter_output = io.StringIO()
        try:
            with redirect_stdout(adapter_output):
                with managed_hysys():
                    result = execute_case(spec)
        finally:
            logs = adapter_output.getvalue()
            if logs:
                print(logs, end="", file=sys.stderr)
        emit_payload(result.to_dict(), args)
        return EXIT_OK
    except Exception as exc:
        if args is None:
            print(
                serialize_payload(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "status": "failed",
                        "scenario": None,
                        "error": {"type": type(exc).__name__, "message": str(exc)},
                    },
                    "json",
                )
            )
        else:
            print(
                serialize_payload(
                    error_payload(args, exc, request),
                    args.output_format,
                )
            )
        return exit_code_for(exc)


if __name__ == "__main__":
    raise SystemExit(main())
