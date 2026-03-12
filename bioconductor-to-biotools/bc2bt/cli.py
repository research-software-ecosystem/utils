#!/usr/bin/env python3
"""
Command-line interface for bc2bt package.
"""

import argparse
import json
import sys
from pathlib import Path

from .converter import batch_convert
from .mapper import compare_files, IdentityRegistry
from .updater import update_entries


def convert_command():
    """Convert Bioconductor packages to bio.tools format."""
    parser = argparse.ArgumentParser(
        description="Convert Bioconductor metadata to bio.tools format"
    )
    parser.add_argument(
        "input_dir",
        help="Directory containing Bioconductor JSON files",
    )
    parser.add_argument(
        "output_dir",
        help="Directory to write converted bio.tools JSON files",
    )
    parser.add_argument(
        "--existing",
        default=None,
        help="Directory with existing bio.tools entries to merge with",
    )
    parser.add_argument(
        "--citation-dir",
        default=None,
        help="Directory containing citation HTML files",
    )

    args = parser.parse_args()

    try:
        result = batch_convert(
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            existing_biotools_dir=args.existing,
        )
        print(f"Converted {len(result)} packages")
        print(f"Output written to: {args.output_dir}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def compare_command():
    """Compare two sets of bio.tools entries to find matches."""
    parser = argparse.ArgumentParser(
        description="Compare bio.tools entries to find matches and duplicates"
    )
    parser.add_argument(
        "pattern1",
        help="File pattern for first set (e.g., 'data/*/*.biotools.json')",
    )
    parser.add_argument(
        "pattern2",
        help="File pattern for second set (e.g., 'converted/*.biotools.json')",
    )
    parser.add_argument(
        "--methods",
        nargs="+",
        default=["name_homepage", "doi"],
        help="Identity methods to use for matching",
    )
    parser.add_argument(
        "--results",
        default="matches.json",
        help="Output file for match results",
    )
    parser.add_argument(
        "--upset1",
        default=None,
        help="Path to save UpSet plot for first set",
    )
    parser.add_argument(
        "--upset2",
        default=None,
        help="Path to save UpSet plot for second set",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Number of parallel workers",
    )

    args = parser.parse_args()

    # Validate methods
    registry = IdentityRegistry()
    invalid = registry.validate(args.methods)
    if invalid:
        print(f"Error: Invalid identity methods: {invalid}", file=sys.stderr)
        print(f"Available methods: {registry.list_methods()}", file=sys.stderr)
        return 1

    try:
        results = compare_files(
            pattern1=args.pattern1,
            pattern2=args.pattern2,
            identity_methods=args.methods,
            upset1_path=args.upset1,
            upset2_path=args.upset2,
            num_workers=args.workers,
        )

        # Save results
        with open(args.results, "w") as f:
            json.dump(results, f, indent=2)

        print(f"\nResults saved to: {args.results}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


def update_command():
    """Update bio.tools entries based on match results."""
    parser = argparse.ArgumentParser(
        description="Update or create bio.tools entries based on match results"
    )
    parser.add_argument(
        "results_file",
        help="JSON file with match results from compare command",
    )
    parser.add_argument(
        "converted_dir",
        help="Directory with converted Bioconductor files",
    )
    parser.add_argument(
        "bt_files_dir",
        help="Directory containing existing bio.tools entries",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Don't create backup files before updating",
    )

    args = parser.parse_args()

    try:
        with open(args.results_file, "r") as f:
            match_results = json.load(f)

        summary = update_entries(
            match_results=match_results,
            converted_files_dir=args.converted_dir,
            bt_files_dir=args.bt_files_dir,
            dry_run=args.dry_run,
            backup=not args.no_backup,
        )

        print("\n" + "=" * 60)
        print("UPDATE SUMMARY")
        print("=" * 60)
        print(f"Created: {len(summary['created'])}")
        print(f"Updated: {len(summary['updated'])}")
        print(f"Errors: {len(summary['errors'])}")

        if args.dry_run:
            print("\n[DRY RUN - No changes made]")

        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


def sync_command(args=None):
    """Run all three operations (convert, compare, update) in one go."""
    # Parse arguments if not provided (when called as console script)
    if args is None:
        parser = argparse.ArgumentParser(
            description="Full workflow: convert, compare, and update in one go"
        )
        parser.add_argument("input_dir", help="Directory with Bioconductor JSON files")
        parser.add_argument(
            "bt_files_dir", help="Directory with existing bio.tools entries"
        )
        parser.add_argument(
            "--work-dir",
            default="bc2bt_work",
            help="Working directory for intermediate files",
        )
        parser.add_argument(
            "--methods",
            nargs="+",
            default=["name_homepage", "doi"],
            help="Identity methods to use",
        )
        parser.add_argument(
            "--workers",
            type=int,
            default=None,
            help="Number of parallel workers",
        )
        parser.add_argument(
            "--upset1",
            default=None,
            help="Path to save UpSet plot for existing bio.tools entries",
        )
        parser.add_argument(
            "--upset2",
            default=None,
            help="Path to save UpSet plot for converted entries",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview changes without applying",
        )
        parser.add_argument(
            "--no-backup",
            action="store_true",
            help="Don't create backup files",
        )
        parser.add_argument(
            "--keep-work-dir",
            action="store_true",
            help="Keep working directory after completion",
        )
        args = parser.parse_args()

    # Validate methods
    registry = IdentityRegistry()
    invalid = registry.validate(args.methods)
    if invalid:
        print(f"Error: Invalid identity methods: {invalid}", file=sys.stderr)
        print(f"Available methods: {registry.list_methods()}", file=sys.stderr)
        return 1

    # Set up working directory
    work_dir = Path(args.work_dir)
    converted_dir = work_dir / "converted"
    results_file = work_dir / "matches.json"

    try:
        # Step 1: Convert
        print("=" * 60)
        print("STEP 1: CONVERT")
        print("=" * 60)

        converted_files = batch_convert(
            input_dir=args.input_dir,
            output_dir=str(converted_dir),
            existing_biotools_dir=args.bt_files_dir,
        )
        print(f"Converted {len(converted_files)} packages")
        print(f"Output written to: {converted_dir}")

        if not converted_files:
            print("No packages converted. Exiting.")
            return 0

        # Step 2: Compare
        print("\n" + "=" * 60)
        print("STEP 2: COMPARE")
        print("=" * 60)

        pattern1 = f"{args.bt_files_dir}/*/*.biotools.json"
        pattern2 = f"{converted_dir}/*.biotools.json"

        results = compare_files(
            pattern1=pattern1,
            pattern2=pattern2,
            identity_methods=args.methods,
            upset1_path=args.upset1,
            upset2_path=args.upset2,
            num_workers=args.workers,
        )

        # Save results
        with open(results_file, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to: {results_file}")

        # Print comparison summary
        for method, matches in results.get("match_results", {}).items():
            print(f"{method} matched: {len(matches)} files")
        print(
            f"Unmatched in existing bio.tools: {len(results.get('only_in_files1', []))}"
        )
        print(f"Unmatched in converted: {len(results.get('only_in_files2', []))}")

        # Step 3: Update
        print("\n" + "=" * 60)
        print("STEP 3: UPDATE")
        print("=" * 60)

        if args.dry_run:
            print("[DRY RUN MODE - No changes will be made]")

        summary = update_entries(
            match_results=results,
            converted_files_dir=str(converted_dir),
            bt_files_dir=args.bt_files_dir,
            dry_run=args.dry_run,
            backup=not args.no_backup,
        )

        print("\nUPDATE SUMMARY")
        print("-" * 40)
        print(f"Created: {len(summary['created'])}")
        print(f"Updated: {len(summary['updated'])}")
        print(f"Errors: {len(summary['errors'])}")

        # Full workflow summary
        print("\n" + "=" * 60)
        print("WORKFLOW COMPLETE")
        print("=" * 60)
        print(f"Converted: {len(converted_files)} packages")
        print(
            f"Matched: {sum(len(m) for m in results.get('match_results', {}).values())} entries"
        )
        print(f"Created: {len(summary['created'])} new entries")
        print(f"Updated: {len(summary['updated'])} existing entries")

        if args.dry_run:
            print("\n[DRY RUN - No changes made]")

        # Clean up working directory unless requested to keep
        if not args.keep_work_dir and not args.dry_run:
            import shutil

            shutil.rmtree(work_dir)
            print(f"\nCleaned up working directory: {work_dir}")
        else:
            print(f"\nWorking directory preserved: {work_dir}")

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


def main():
    """Main entry point with subcommands."""
    parser = argparse.ArgumentParser(
        prog="bc2bt",
        description="Bioconductor to bio.tools synchronization tool",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Sync command (all-in-one)
    sync_parser = subparsers.add_parser(
        "sync",
        help="Full workflow: convert, compare, and update in one go",
    )
    sync_parser.add_argument("input_dir", help="Directory with Bioconductor JSON files")
    sync_parser.add_argument(
        "bt_files_dir", help="Directory with existing bio.tools entries"
    )
    sync_parser.add_argument(
        "--work-dir",
        default="bc2bt_work",
        help="Working directory for intermediate files",
    )
    sync_parser.add_argument(
        "--methods",
        nargs="+",
        default=["name_homepage", "doi"],
        help="Identity methods to use",
    )
    sync_parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Number of parallel workers",
    )
    sync_parser.add_argument(
        "--upset1",
        default=None,
        help="Path to save UpSet plot for existing bio.tools entries",
    )
    sync_parser.add_argument(
        "--upset2",
        default=None,
        help="Path to save UpSet plot for converted entries",
    )
    sync_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without applying",
    )
    sync_parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Don't create backup files",
    )
    sync_parser.add_argument(
        "--keep-work-dir",
        action="store_true",
        help="Keep working directory after completion",
    )

    # Convert command
    convert_parser = subparsers.add_parser(
        "convert",
        help="Convert Bioconductor packages to bio.tools format",
    )
    convert_parser.add_argument("input_dir", help="Input directory")
    convert_parser.add_argument("output_dir", help="Output directory")
    convert_parser.add_argument(
        "--existing",
        default=None,
        help="Directory with existing bio.tools entries to merge",
    )

    # Compare command
    compare_parser = subparsers.add_parser(
        "compare",
        help="Compare two sets of bio.tools entries",
    )
    compare_parser.add_argument("pattern1", help="First file pattern")
    compare_parser.add_argument("pattern2", help="Second file pattern")
    compare_parser.add_argument(
        "--methods",
        nargs="+",
        default=["name_homepage", "doi"],
        help="Identity methods to use",
    )
    compare_parser.add_argument(
        "--results",
        default="matches.json",
        help="Output file for results",
    )

    # Update command
    update_parser = subparsers.add_parser(
        "update",
        help="Update bio.tools entries based on matches",
    )
    update_parser.add_argument("results_file", help="Match results JSON")
    update_parser.add_argument("converted_dir", help="Converted files directory")
    update_parser.add_argument("bt_files_dir", help="bio.tools files directory")
    update_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without applying",
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 1

    # Dispatch to appropriate command
    if args.command == "sync":
        return sync_command(args)
    elif args.command == "convert":
        return convert_command()
    elif args.command == "compare":
        return compare_command()
    elif args.command == "update":
        return update_command()

    return 0


if __name__ == "__main__":
    sys.exit(main())
