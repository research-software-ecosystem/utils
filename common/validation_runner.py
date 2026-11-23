"""Shared engine for the per-source import validators.

Each ``<source>-validate/validate.py`` calls :func:`main` with its source
name, JSON Schema path and the glob patterns of the files it owns inside a
checkout of research-software-ecosystem/content. Structure and value rules
both live in the schema; value formats come from ``validation_checks``.
"""

import argparse
import glob
import json
import logging
import os

import yaml
from jsonschema import Draft202012Validator
from validation_checks import WARNING_FORMATS, make_format_checker

logger = logging.getLogger(__name__)

ERROR = "error"
WARNING = "warning"


class Finding:
    def __init__(self, severity, path, location, message):
        self.severity = severity
        self.path = path
        self.location = location
        self.message = message

    def as_dict(self):
        return {
            "severity": self.severity,
            "file": self.path,
            "location": self.location,
            "message": self.message,
        }


def _json_path(error):
    """Dotted path of a jsonschema error inside the instance."""
    parts = []
    for p in error.absolute_path:
        if isinstance(p, int):
            parts.append(f"[{p}]")
        else:
            parts.append(("." if parts else "") + str(p))
    return "".join(parts) or "<root>"


def _load(path):
    with open(path, encoding="utf-8") as fh:
        if path.endswith((".yaml", ".yml")):
            return yaml.safe_load(fh)
        return json.load(fh)


def _severity(error):
    if error.validator == "format" and error.validator_value in WARNING_FORMATS:
        return WARNING
    return ERROR


def validate_file(path, validator):
    """Validate one file; returns a list of Finding."""
    try:
        data = _load(path)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return [Finding(ERROR, path, "<file>", f"cannot parse: {exc}")]
    findings = []
    for error in validator.iter_errors(data):
        message = error.message
        if len(message) > 300:
            message = message[:297] + "..."
        findings.append(Finding(_severity(error), path, _json_path(error), message))
    return findings


def collect_files(root, globs):
    files = []
    for pattern in globs:
        files.extend(glob.glob(os.path.join(root, pattern)))
    return sorted(set(files))


def _emit(finding, output):
    if output == "github":
        kind = "error" if finding.severity == ERROR else "warning"
        print(f"::{kind} file={finding.path}::{finding.location}: {finding.message}")
    else:
        print(
            f"{finding.severity.upper()} {finding.path}: "
            f"{finding.location}: {finding.message}"
        )


def run(source, schema_path, globs, argv=None):
    parser = argparse.ArgumentParser(
        description=f"Validate {source} files imported into the content repo."
    )
    parser.add_argument(
        "content_path",
        help="path to a checkout of research-software-ecosystem/content",
    )
    parser.add_argument(
        "--glob",
        action="append",
        dest="globs",
        help="override the default file globs (repeatable)",
    )
    parser.add_argument(
        "--output",
        choices=("text", "github", "json"),
        default="text",
        help="report style (default: text)",
    )
    parser.add_argument(
        "--warnings-as-errors",
        action="store_true",
        help="exit non-zero on warnings too",
    )
    parser.add_argument(
        "--report-file",
        metavar="PATH",
        help="also write a plain-text report (findings + summary) to PATH",
    )
    parser.add_argument(
        "--max-errors",
        type=int,
        default=0,
        metavar="N",
        help="stop after N files with errors (0 = no limit)",
    )
    args = parser.parse_args(argv)

    if not os.path.isdir(args.content_path):
        parser.error(f"{args.content_path} is not a directory")

    with open(schema_path, encoding="utf-8") as fh:
        schema = json.load(fh)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=make_format_checker())

    files = collect_files(args.content_path, args.globs or globs)
    if not files:
        print(f"{source}: no files matched under {args.content_path}")
        return 2

    all_findings = []
    files_with_errors = 0
    for path in files:
        findings = validate_file(path, validator)
        rel = os.path.relpath(path, args.content_path)
        for f in findings:
            f.path = rel
        all_findings.extend(findings)
        if any(f.severity == ERROR for f in findings):
            files_with_errors += 1
            if args.max_errors and files_with_errors >= args.max_errors:
                break
        if args.output != "json":
            for f in findings:
                _emit(f, args.output)

    errors = sum(1 for f in all_findings if f.severity == ERROR)
    warnings = sum(1 for f in all_findings if f.severity == WARNING)
    summary = (
        f"{source}: {len(files)} files checked, "
        f"{errors} errors in {files_with_errors} files, "
        f"{warnings} warnings"
    )
    if args.report_file:
        with open(args.report_file, "w", encoding="utf-8") as fh:
            for f in all_findings:
                fh.write(f"{f.severity.upper()} {f.path}: {f.location}: {f.message}\n")
            fh.write(summary + "\n")
    if args.output == "json":
        print(
            json.dumps(
                {
                    "source": source,
                    "files_checked": len(files),
                    "errors": errors,
                    "warnings": warnings,
                    "findings": [f.as_dict() for f in all_findings],
                },
                indent=2,
            )
        )
    else:
        print(summary)
    if errors or (warnings and args.warnings_as_errors):
        return 1
    return 0


def main(source, schema_path, globs, argv=None):
    return run(source, str(schema_path), globs, argv)
