import argparse
import json
import sys
from pathlib import Path

from entrypoints.bootstrap import build_analyzer
from entrypoints.http.models import from_analysis
from usecases.errors import ServiceError

PROBLEM_TYPE_PREFIX = "https://itau.example/document-intelligence/errors/"


def analyze_file(path: Path, profile: str | None = None) -> int:
    if not path.is_file():
        sys.stderr.write(f"Error: file not found: {path}\n")
        return 1

    content = path.read_bytes()
    analyze = build_analyzer(profile=profile)
    try:
        analysis = analyze(content)
        result = from_analysis(analysis).model_dump(mode="json")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except ServiceError as error:
        problem = {
            "type": f"{PROBLEM_TYPE_PREFIX}{error.code.value}",
            "title": error.title,
            "status": error.status,
            "detail": error.detail,
            "code": error.code.value,
            **error.extra,
        }
        print(json.dumps(problem, indent=2, ensure_ascii=False))
        return 0
    except Exception as error:
        sys.stderr.write(f"Error: analysis failed: {error}\n")
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="document-intelligence",
        description="Document Intelligence Service command-line interface.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze_parser = subparsers.add_parser("analisar", help="Analyse a document")
    analyze_parser.add_argument("file", type=Path, help="Path to document file to analyse")
    analyze_parser.add_argument(
        "--profile",
        choices=("fake", "aws"),
        default=None,
        help="Runtime profile (defaults to configured profile or fake)",
    )

    args = parser.parse_args(argv)
    if args.command == "analisar":
        return analyze_file(args.file, profile=args.profile)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
