"""
Updater module for creating and updating bio.tools entries based on match results.
"""

import json
import re
import shutil
import unicodedata
from collections import defaultdict
import logging
from pathlib import Path


logger = logging.getLogger(__name__)


def _fold(text: str) -> str:
    """Case- and accent-insensitive key, so Schwämmle and Schwammle are one person."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    return (
        "".join(c for c in decomposed if not unicodedata.combining(c)).strip().lower()
    )


PLACEHOLDER_DOI = re.compile(r"^10\.18129/B9\.bioc\.", re.IGNORECASE)


def _publication_key(pub: dict):
    """Identify a publication by whichever identifier it carries."""
    for field in ("doi", "pmid", "pmcid"):
        value = (pub.get(field) or "").strip().lower()
        if value:
            return (field, value)
    return None


def _is_real_doi(key) -> bool:
    return bool(key) and key[0] == "doi" and not PLACEHOLDER_DOI.match(key[1])


def merge_publications(existing: list | None, incoming: list | None) -> list:
    """Union two publication lists, keyed by identifier.

    Assigning the converted list over the existing one displaced a real paper
    with Bioconductor's per-package DOI, 10.18129/B9.bioc.<pkg>, on about 780
    entries, and stripped the citation metadata from another 210. Existing
    entries are therefore kept whole, and the placeholder is only ever added
    when nothing else identifies the software.
    """
    merged = [dict(pub) for pub in (existing or [])]
    seen = {k for k in (_publication_key(p) for p in merged) if k}

    # Decided up front over both lists, so the outcome cannot depend on order.
    has_real = any(
        _is_real_doi(_publication_key(p)) for p in (existing or []) + (incoming or [])
    )

    for pub in incoming or []:
        key = _publication_key(pub)
        if key is None or key in seen:
            continue
        if has_real and key[0] == "doi" and PLACEHOLDER_DOI.match(key[1]):
            continue  # never in place of a real citation
        merged.append(dict(pub))
        seen.add(key)
    return merged


def is_valid_url(url) -> bool:
    """Reject what bio.tools would reject, and nothing else.

    The converter has emitted two URLs joined into one field, e.g.
    "https://github.com/HelBor/wpm, https://bioconductor.org/packages/wpm",
    and host names with no dot, e.g. http://bioconductor/packages/... which
    never resolved. Both are refused by the registry.
    """
    if not isinstance(url, str):
        return False
    candidate = url.strip()
    if not candidate.startswith(("http://", "https://")):
        return False
    if any(ch.isspace() for ch in candidate) or ", " in candidate:
        return False
    host = candidate.split("//", 1)[1].split("/", 1)[0]
    return "." in host


def _url_key(entry: dict) -> str:
    return (entry.get("url") or "").strip().rstrip("/").lower()


# Two or more dot-separated numbers, so a release version matches but an
# accession such as GSE12345 does not.
VERSION_TOKEN = re.compile(r"\d+(?:\.\d+)+")


def _version_family(url: str) -> str:
    """The URL with its version numbers blanked, identifying one resource."""
    return VERSION_TOKEN.sub("#", url)


def _version_sort_key(url: str):
    """Order URLs of one family by the release they point at."""
    return [
        tuple(int(part) for part in match.group(0).split("."))
        for match in VERSION_TOKEN.finditer(url)
    ]


def merge_urls(existing: list | None, incoming: list | None) -> list:
    """Union documentation or download lists, dropping only invalid URLs.

    Nothing usable is discarded: a third-party download or documentation link
    survives a Bioconductor import. Invalid entries are dropped from either
    side, which is what removes the http://bioconductor/... links that never
    resolved.

    Release tarballs carry a version, so a plain union would accumulate one
    dead link per release -- a4_1.59.0.tar.gz, then _1.60.0, then _1.61.0. URLs
    differing only by version are therefore one resource, and only the latest
    is kept.
    """
    kept: list = []
    seen: set = set()
    for entry in (existing or []) + (incoming or []):
        if not isinstance(entry, dict) or not is_valid_url(entry.get("url")):
            continue
        key = _url_key(entry)
        if key in seen:
            continue
        kept.append(dict(entry))
        seen.add(key)

    newest: dict = {}
    for entry in kept:
        url = (entry.get("url") or "").strip()
        family = (str(entry.get("type")), _version_family(url))
        current = newest.get(family)
        if current is None or _version_sort_key(url) > _version_sort_key(
            (current.get("url") or "").strip()
        ):
            newest[family] = entry

    winners = {id(entry) for entry in newest.values()}
    return [entry for entry in kept if id(entry) in winners]


def dedupe_credit(people: list | None) -> list:
    """Collapse repeated names into one entry, unioning their roles.

    A Bioconductor Author string can name the same person twice, e.g. ggmanh's
    "John Lee [aut, cre], John Lee [aut] (AbbVie), Xiuwen Zheng [ctb, dtc]".
    Written out verbatim that produces two John Lee entries, and merging them
    later changed the file, so a second run was not a no-op. Both the create
    and the update path go through this, so they agree.
    """
    collapsed: list = []
    index: dict = {}
    for person in people or []:
        key = _fold(person.get("name", ""))
        if not key:
            collapsed.append(dict(person))
            continue
        current = index.get(key)
        if current is None:
            collapsed.append(dict(person))
            index[key] = collapsed[-1]
            continue
        for field, value in person.items():
            if field != "typeRole" and value and not current.get(field):
                current[field] = value
        roles = set(current.get("typeRole") or []) | set(person.get("typeRole") or [])
        if roles:
            current["typeRole"] = sorted(roles)
    return collapsed


def merge_credit(existing: list | None, incoming: list | None) -> list:
    """Union two credit lists instead of replacing one with the other.

    Bioconductor's Author string rarely carries e-mail addresses, so assigning
    the converted list over the curated one dropped a contact address from
    about 1,270 entries. Here an existing person keeps every field they already
    had, blanks are filled in from Bioconductor, roles are unioned, and people
    Bioconductor knows about but bio.tools does not are appended.
    """
    merged = dedupe_credit(existing)
    incoming = dedupe_credit(incoming)
    index = {
        _fold(person.get("name", "")): person for person in merged if person.get("name")
    }

    for person in incoming or []:
        key = _fold(person.get("name", ""))
        if not key:
            continue
        current = index.get(key)
        if current is None:
            merged.append(dict(person))
            index[key] = merged[-1]
            continue
        for field, value in person.items():
            if field == "typeRole":
                continue
            if value and not current.get(field):
                current[field] = value  # fill a blank, never overwrite
        roles = set(current.get("typeRole") or []) | set(person.get("typeRole") or [])
        if roles:
            current["typeRole"] = sorted(roles)

    # An address Bioconductor supplies for someone who already has a different
    # one would otherwise be lost, since a credit entry holds a single e-mail.
    known = {_fold(p.get("email", "")) for p in merged if p.get("email")}
    for person in incoming or []:
        email = _fold(person.get("email", ""))
        if email and email not in known:
            merged.append(dict(person))
            known.add(email)

    return merged


def merge_homepage(existing: str | None, incoming: str | None) -> str | None:
    """Keep the project's own homepage; only refresh a Bioconductor one.

    A package is often more than its Bioconductor release -- PolySTest and
    VSClust are both web applications -- and pointing the homepage at
    bioconductor.org misrepresents what the tool is.
    """
    if existing and "bioconductor.org" not in existing.lower():
        return existing
    return incoming or existing


def keep_existing_text(existing, incoming):
    """Curated prose wins. bio.tools is the authority for its own description."""
    return existing if existing else incoming


def normalise_record(data: dict) -> dict:
    """Apply the merge policies to a record with nothing to merge against.

    create_entry used to write the converted record verbatim, so the first
    update afterwards cleaned it up and the run after that differed from the
    one before -- the converter was not idempotent for any newly created
    entry. Running the same helpers here means the create and update paths
    agree by construction: whatever a merge would produce, a create produces
    too.
    """
    if data.get("credit"):
        data["credit"] = dedupe_credit(data["credit"])
    if data.get("publication"):
        data["publication"] = merge_publications(None, data["publication"])
    for field in ("documentation", "download"):
        if data.get(field):
            data[field] = merge_urls(None, data[field])
    return data


class Updater:
    """Handles creation and updating of bio.tools entries."""

    def __init__(
        self,
        bt_files_dir: str,
        dry_run: bool = False,
        backup: bool = True,
        bioc_files_dir: str | None = None,
        copy_source: bool = True,
    ):
        """
        Initialize the updater.

        Args:
            bt_files_dir: Directory containing existing bio.tools entries
            dry_run: If True, don't actually write any changes
            backup: If True, create .backup files before modifying
            bioc_files_dir: Directory containing original Bioconductor JSON files
            copy_source: If True, copy original Bioconductor files to data directory
        """
        self.bt_files_dir = Path(bt_files_dir)
        self.dry_run = dry_run
        self.backup = backup
        self.bioc_files_dir = Path(bioc_files_dir) if bioc_files_dir else None
        self.copy_source = copy_source

    def _get_source_bioc_file(self, biotools_id: str) -> Path | None:
        """
        Get the path to the original Bioconductor source file.

        The biotools_id is formatted as "bioconductor-{package_name}",
        so we extract the package name and look for {package}.bioconductor.json.

        Args:
            biotools_id: The bio.tools ID (e.g., "bioconductor-limma")

        Returns:
            Path to the source Bioconductor file, or None if not found
        """
        if not self.bioc_files_dir:
            return None

        # Extract package name from biotools_id (remove "bioconductor-" prefix)
        if biotools_id.startswith("bioconductor-"):
            package_name = biotools_id[len("bioconductor-") :]
        else:
            package_name = biotools_id

        source_file = self.bioc_files_dir / f"{package_name}.bioconductor.json"
        return source_file if source_file.exists() else None

    def _copy_source_file(self, biotools_id: str, target_dir: Path) -> Path | None:
        """
        Copy the original Bioconductor source file to the target directory.

        Args:
            biotools_id: The bio.tools ID
            target_dir: Directory to copy the source file to

        Returns:
            Path to the copied file, or None if not copied
        """
        if not self.copy_source or not self.bioc_files_dir:
            return None

        source_file = self._get_source_bioc_file(biotools_id)
        if not source_file:
            logger.debug(f"No source Bioconductor file found for {biotools_id}")
            return None

        if self.dry_run:
            target_path = target_dir / f"{biotools_id}.bioconductor.json"
            logger.info(f"[DRY RUN] Would copy source: {source_file} -> {target_path}")
            return target_path

        # Ensure target directory exists
        target_dir.mkdir(parents=True, exist_ok=True)

        # Copy the source file with biotools_id naming
        target_path = target_dir / f"{biotools_id}.bioconductor.json"
        shutil.copy2(source_file, target_path)
        logger.info(f"Copied source: {target_path}")
        return target_path

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

        # The matcher only pairs converted files against entries it matched,
        # so an entry registered by another flow (e.g. gh2biotools) can still
        # reach this branch as "new". Overwriting it would clobber protected
        # registration fields (owner, additionDate, lastUpdate,
        # editPermission) — merge into the existing entry instead.
        if target_path.exists():
            logger.info(f"Entry already exists, updating instead: {target_path}")
            return self.update_entry(str(target_path), str(source_path))

        if self.dry_run:
            logger.info(f"[DRY RUN] Would create: {target_path}")
            # Also log source copy in dry run mode
            self._copy_source_file(biotools_id, target_path.parent)
            return str(target_path)

        data = normalise_record(data)

        # Ensure target directory exists
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Write the file
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

        logger.info(f"Created: {target_path}")

        # Copy source Bioconductor file if enabled
        self._copy_source_file(biotools_id, target_path.parent)

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

        # Get biotoolsID for source copying
        biotools_id = existing_data.get("biotoolsID") or bioc_data.get("biotoolsID")

        # Start with existing data (preserves ALL fields from bio.tools)
        merged_data = {**existing_data}

        # Fields taken verbatim from Bioconductor. These describe the release
        # itself, so the upstream value is the better one.
        # Bioconductor is authoritative for the release itself. Silence is not
        # an assertion though, so an absent or empty value must not erase what
        # bio.tools already knows -- a null licence is rejected outright.
        bioc_fields_to_assign = [
            "license",
            "version",
        ]
        for field in bioc_fields_to_assign:
            if bioc_data.get(field):
                merged_data[field] = bioc_data[field]

        # Fields where the curated bio.tools value must survive.
        if "credit" in bioc_data or existing_data.get("credit"):
            merged_data["credit"] = merge_credit(
                existing_data.get("credit"), bioc_data.get("credit")
            )
        if "description" in bioc_data:
            merged_data["description"] = keep_existing_text(
                existing_data.get("description"), bioc_data.get("description")
            )
        if "homepage" in bioc_data:
            merged_data["homepage"] = merge_homepage(
                existing_data.get("homepage"), bioc_data.get("homepage")
            )
        if "publication" in bioc_data or existing_data.get("publication"):
            merged_data["publication"] = merge_publications(
                existing_data.get("publication"), bioc_data.get("publication")
            )
        for field in ("documentation", "download"):
            if field in bioc_data or existing_data.get(field):
                merged_data[field] = merge_urls(
                    existing_data.get(field), bioc_data.get(field)
                )

        # Merge collectionID: ensure "BioConductor" is included
        existing_collections = set(existing_data.get("collectionID", []))
        existing_collections.add("BioConductor")
        merged_data["collectionID"] = sorted(list(existing_collections))

        if self.dry_run:
            logger.info(f"[DRY RUN] Would update: {existing_path}")
            # Also log source copy in dry run mode
            if biotools_id:
                self._copy_source_file(biotools_id, existing_path.parent)
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

        # Copy source Bioconductor file if enabled
        if biotools_id:
            self._copy_source_file(biotools_id, existing_path.parent)

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
            "conflicts": [],
        }

        summary["conflicts"].extend(match_results.get("conflicts", []))

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

        # Build the pairing both ways round. The previous version kept a single
        # converted -> existing dict and let a later write replace an earlier
        # one, so when several converted packages pointed at the same entry the
        # last one applied decided its contents -- and dict order came from a
        # set of path strings, i.e. from PYTHONHASHSEED. That is how
        # ARRmNormalization came to hold minfi's, then derfinder's, then
        # sesame's metadata on successive runs. Ambiguity is now refused and
        # reported instead of resolved arbitrarily.
        converted_to_existing = defaultdict(set)
        existing_to_converted = defaultdict(set)
        for method_results in match_results.get("match_results", {}).values():
            for existing_file, converted_files in method_results.items():
                for converted_file in converted_files:
                    converted_to_existing[converted_file].add(existing_file)
                    existing_to_converted[existing_file].add(converted_file)

        pairs = []
        for converted_file in sorted(converted_to_existing):
            targets = converted_to_existing[converted_file]
            if len(targets) > 1:
                summary["conflicts"].append(
                    {
                        "converted": converted_file,
                        "existing": sorted(targets),
                        "reason": "one converted package matched several entries",
                    }
                )
                continue
            existing_file = next(iter(targets))
            sources = existing_to_converted[existing_file]
            if len(sources) > 1:
                summary["conflicts"].append(
                    {
                        "existing": existing_file,
                        "converted": sorted(sources),
                        "reason": "several converted packages matched one entry",
                    }
                )
                continue
            pairs.append((converted_file, existing_file))

        # Update matched entries
        for converted_file, existing_file in pairs:
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
    bioc_files_dir: str | None = None,
    copy_source: bool = True,
) -> dict:
    """
    Convenience function to update/create bio.tools entries based on match results.

    Args:
        match_results: Result dictionary from mapper.compare_files()
        converted_files_dir: Directory containing converted Bioconductor files
        bt_files_dir: Directory containing existing bio.tools entries
        dry_run: If True, don't actually write any changes
        backup: If True, create .backup files before modifying
        bioc_files_dir: Directory containing original Bioconductor JSON files
        copy_source: If True, copy original Bioconductor files to data directory

    Returns:
        Summary of operations performed
    """
    updater = Updater(bt_files_dir, dry_run, backup, bioc_files_dir, copy_source)
    return updater.apply_changes(match_results, converted_files_dir)
