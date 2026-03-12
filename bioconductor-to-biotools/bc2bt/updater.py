"""
Updater module for creating and updating bio.tools entries based on match results.
"""

import json
import shutil
import logging
from pathlib import Path


logger = logging.getLogger(__name__)


class Updater:
    """Handles creation and updating of bio.tools entries."""

    def __init__(
        self,
        bt_files_dir: str,
        dry_run: bool = False,
        backup: bool = True,
    ):
        """
        Initialize the updater.

        Args:
            bt_files_dir: Directory containing existing bio.tools entries
            dry_run: If True, don't actually write any changes
            backup: If True, create .backup files before modifying
        """
        self.bt_files_dir = Path(bt_files_dir)
        self.dry_run = dry_run
        self.backup = backup

    def create_entry(self, converted_file_path: str, target_dir: str) -> str:
        """
        Create a new bio.tools entry from a converted Bioconductor file.

        Args:
            converted_file_path: Path to the converted bio.tools JSON file
            target_dir: Directory to create the entry in

        Returns:
            Path to the created file
        """
        source_path = Path(converted_file_path)

        # Load the converted data
        with open(source_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Determine target path (create subdirectory for each entry)
        biotools_id = data["biotoolsID"]
        target_path = Path(target_dir) / biotools_id / f"{biotools_id}.biotools.json"

        if self.dry_run:
            logger.info(f"[DRY RUN] Would create: {target_path}")
            return str(target_path)

        # Ensure target directory exists
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Write the file
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

        logger.info(f"Created: {target_path}")
        return str(target_path)

    def update_entry(
        self,
        existing_file_path: str,
        converted_file_path: str,
    ) -> str:
        """
        Update an existing bio.tools entry with Bioconductor metadata.

        Strategy: Start with existing bio.tools data (preserves all fields),
        then selectively update specific fields from Bioconductor.

        Args:
            existing_file_path: Path to the existing bio.tools JSON file
            converted_file_path: Path to the converted Bioconductor JSON file

        Returns:
            Path to the updated file
        """
        existing_path = Path(existing_file_path)

        # Load both files
        with open(existing_path, "r", encoding="utf-8") as f:
            existing_data = json.load(f)

        with open(converted_file_path, "r", encoding="utf-8") as f:
            bioc_data = json.load(f)

        # Start with existing data (preserves ALL fields from bio.tools)
        merged_data = {**existing_data}

        # Fields to update from Bioconductor (only these will be overwritten)
        bioc_fields_to_update = [
            "credit",
            "description",
            "documentation",
            "download",
            "homepage",
            "license",
            "publication",
            "version",
        ]

        for field in bioc_fields_to_update:
            if field in bioc_data:
                merged_data[field] = bioc_data[field]

        # Merge collectionID: ensure "BioConductor" is included
        existing_collections = set(existing_data.get("collectionID", []))
        existing_collections.add("BioConductor")
        merged_data["collectionID"] = sorted(list(existing_collections))

        if self.dry_run:
            logger.info(f"[DRY RUN] Would update: {existing_path}")
            return str(existing_path)

        # Create backup if requested
        if self.backup:
            backup_path = existing_path.with_suffix(".biotools.json.backup")
            shutil.copy2(existing_path, backup_path)
            logger.debug(f"Backup created: {backup_path}")

        # Write the merged data
        with open(existing_path, "w", encoding="utf-8") as f:
            json.dump(merged_data, f, indent=4)

        logger.info(f"Updated: {existing_path}")
        return str(existing_path)

    def apply_changes(
        self,
        match_results: dict,
        converted_files_dir: str,
    ) -> dict:
        """
        Apply create/update operations based on match results.

        Args:
            match_results: Result dictionary from mapper.compare_files()
            converted_files_dir: Directory containing converted Bioconductor files

        Returns:
            Summary of operations performed
        """
        summary = {
            "created": [],
            "updated": [],
            "skipped": [],
            "errors": [],
        }

        # Files that exist only in dataset 2 (converted files) need to be created
        for new_file_path in match_results.get("only_in_files2", []):
            try:
                created_path = self.create_entry(new_file_path, str(self.bt_files_dir))
                summary["created"].append(created_path)
            except Exception as e:
                logger.error(f"Error creating entry from {new_file_path}: {e}")
                summary["errors"].append({"file": new_file_path, "error": str(e)})

        # Files that matched need to be updated
        # A file is considered matched if it appears in any method's results
        matched_files1 = set()
        for method_results in match_results.get("match_results", {}).values():
            matched_files1.update(method_results.keys())

        # Build mapping from converted files to existing files
        conversion_to_existing = {}
        for method, method_results in match_results.get("match_results", {}).items():
            for existing_file, converted_files in method_results.items():
                for converted_file in converted_files:
                    conversion_to_existing[converted_file] = existing_file

        # Update matched entries
        for converted_file, existing_file in conversion_to_existing.items():
            try:
                updated_path = self.update_entry(existing_file, converted_file)
                summary["updated"].append(
                    {
                        "source": converted_file,
                        "target": updated_path,
                    }
                )
            except Exception as e:
                logger.error(
                    f"Error updating {existing_file} from {converted_file}: {e}"
                )
                summary["errors"].append(
                    {
                        "source": converted_file,
                        "target": existing_file,
                        "error": str(e),
                    }
                )

        return summary


def create_entry(
    converted_file_path: str,
    bt_files_dir: str,
    dry_run: bool = False,
) -> str:
    """
    Convenience function to create a single bio.tools entry.

    Args:
        converted_file_path: Path to the converted bio.tools JSON file
        bt_files_dir: Directory containing existing bio.tools entries
        dry_run: If True, don't actually write any changes

    Returns:
        Path to the created file
    """
    updater = Updater(bt_files_dir, dry_run, backup=False)
    return updater.create_entry(converted_file_path, bt_files_dir)


def update_entries(
    match_results: dict,
    converted_files_dir: str,
    bt_files_dir: str,
    dry_run: bool = False,
    backup: bool = True,
) -> dict:
    """
    Convenience function to update/create bio.tools entries based on match results.

    Args:
        match_results: Result dictionary from mapper.compare_files()
        converted_files_dir: Directory containing converted Bioconductor files
        bt_files_dir: Directory containing existing bio.tools entries
        dry_run: If True, don't actually write any changes
        backup: If True, create .backup files before modifying

    Returns:
        Summary of operations performed
    """
    updater = Updater(bt_files_dir, dry_run, backup)
    return updater.apply_changes(match_results, converted_files_dir)
