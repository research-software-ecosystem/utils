"""
Mapper module for matching bio.tools entries using configurable identity functions.
"""

import os
import re
import json
import glob
import logging
from collections import defaultdict
from typing import List, Dict, Callable, Optional, FrozenSet, Tuple
from multiprocessing import Pool, cpu_count
from urllib.parse import urlparse
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

matplotlib.use("Agg")  # Set non-interactive backend
from tqdm import tqdm
import pandas as pd
from upsetplot import from_indicators, UpSet


# Configure logging
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
levels = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
    "NOTSET": logging.NOTSET,
}
logging.basicConfig(level=levels.get(log_level, logging.INFO))


def remove_protocol(url: str) -> str:
    """Remove any protocol from a URL."""
    if "://" in url:
        return url.split("://", 1)[1]
    return url


def normalize_bioconductor_url(url: str) -> str:
    """
    Normalize Bioconductor URLs with comprehensive error handling.
    """
    try:
        parsed = urlparse(url)
        if not parsed.netloc.endswith("bioconductor.org"):
            return url

        # Pattern for Bioconductor package HTML pages
        pattern = r"(https?://bioconductor\.org/packages/)(?:release|[^/]+/bioc)/html/([^/]+)\.html(?:\?.*)?$"

        match = re.match(pattern, url)
        if match:
            base_url = match.group(1)
            package_name = match.group(2)
            return f"{base_url}{package_name}"

        return url

    except Exception:
        return url


def identity_name(json_data: dict) -> Optional[str]:
    """Return the name of the bio.tools tool from JSON."""
    return json_data.get("name")


def identity_name_insensitive(json_data: dict) -> Optional[str]:
    """Return the name of the bio.tools tool from JSON (case-insensitive)."""
    name = json_data.get("name")
    return name.lower() if name else None


def identity_homepage(json_data: dict) -> Optional[str]:
    """Return the homepage of the bio.tools tool from JSON."""
    homepage = json_data.get("homepage")
    if homepage:
        return remove_protocol(normalize_bioconductor_url(homepage))
    return None


def identity_biotoolsID_unprefixed(json_data: dict) -> Optional[str]:
    """Return the biotoolsID without 'bioconductor-' prefix."""
    btid = json_data.get("biotoolsID")
    if btid:
        return btid.removeprefix("bioconductor-")
    return None


def identity_doi(json_data: dict) -> Optional[FrozenSet[str]]:
    """Return the publication DOIs of the bio.tools tool from JSON."""
    dois = set()
    publications = json_data.get("publication", [])
    for pub in publications:
        doi = pub.get("doi")
        if doi:
            dois.add(doi)
    return frozenset(dois) if dois else None


def identity_name_homepage(json_data: dict) -> Optional[Tuple]:
    """
    Return combined (name, homepage) tuple for strong duplicate detection.

    Both fields must be present and non-empty for a match.
    Name is lowercased and stripped; homepage is normalized.
    """
    name = json_data.get("name", "").lower().strip()
    homepage = json_data.get("homepage", "")
    if name and homepage:
        return (name, remove_protocol(normalize_bioconductor_url(homepage)))
    return None


# Registry of available identity functions
IDENTITY_FUNCTIONS: Dict[str, Callable] = {
    "name": identity_name,
    "doi": identity_doi,
    "name_insensitive": identity_name_insensitive,
    "homepage": identity_homepage,
    "biotoolsID_unprefixed": identity_biotoolsID_unprefixed,
    "name_homepage": identity_name_homepage,
}


def load_json(filepath: str) -> Optional[dict]:
    """Load JSON file and return its contents."""
    try:
        with open(filepath, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception as e:
        logging.error(f"Error loading {filepath}: {e}")
        return None


def load_json_with_path(filepath: str) -> tuple:
    """Helper function for parallel loading."""
    return filepath, load_json(filepath)


class IdentityRegistry:
    """Registry for identity functions."""

    def __init__(self):
        self.functions = IDENTITY_FUNCTIONS.copy()

    def resolve(self, methods: List[str]) -> List[Callable]:
        """Resolve method names to functions."""
        return [self.functions[m] for m in methods if m in self.functions]

    def list_methods(self) -> List[str]:
        """List available method names."""
        return list(self.functions.keys())

    def validate(self, methods: List[str]) -> List[str]:
        """Validate method names, return invalid ones."""
        return [m for m in methods if m not in self.functions]


def build_identity_index(
    json_data_dict: Dict[str, dict], identity_methods: List[str]
) -> tuple:
    """
    Pre-compute all identity values and create reverse indices for fast lookup.

    Args:
        json_data_dict: Dictionary mapping file paths to JSON data
        identity_methods: List of identity methods to use

    Returns:
        Tuple of (identity_values, identity_indices)
    """
    identity_values = {}
    identity_indices = {method: defaultdict(list) for method in identity_methods}

    for filepath, json_data in json_data_dict.items():
        if not json_data:
            continue

        identity_values[filepath] = {}

        for method in identity_methods:
            id_func = IDENTITY_FUNCTIONS[method]
            id_value = id_func(json_data)

            if id_value is not None:
                identity_values[filepath][method] = id_value

                # Handle set/frozenset types differently for indexing
                if isinstance(id_value, (set, frozenset)):
                    for element in id_value:
                        identity_indices[method][element].append(filepath)
                else:
                    identity_indices[method][id_value].append(filepath)

    return identity_values, identity_indices


def find_matches_optimized(
    identity_values1: dict,
    identity_values2: dict,
    identity_indices2: dict,
    identity_methods: List[str],
) -> tuple:
    """
    Find matches between two datasets using pre-computed indices.

    Args:
        identity_values1: Identity values for dataset 1
        identity_values2: Identity values for dataset 2
        identity_indices2: Reverse index for dataset 2
        identity_methods: List of identity methods to use

    Returns:
        Tuple of (match_results, match_registry1, match_registry2, matched_files1, matched_files2)
    """
    match_results = defaultdict(lambda: defaultdict(set))
    matched_files1 = set()
    matched_files2 = set()

    match_registry1 = {method: {} for method in identity_methods}
    match_registry2 = {method: {} for method in identity_methods}

    # Initialize all files as unmatched
    for file1 in identity_values1.keys():
        for method in identity_methods:
            match_registry1[method][file1] = False

    for file2 in identity_values2.keys():
        for method in identity_methods:
            match_registry2[method][file2] = False

    # Process each file from dataset 1
    for file1, id_vals1 in tqdm(
        identity_values1.items(), desc="Finding matches", unit="file"
    ):
        if file1 in matched_files1:
            continue

        candidates = set()
        method_matches = defaultdict(set)

        # Find candidate matches for each method
        for method in identity_methods:
            if method not in id_vals1:
                continue

            id_val1 = id_vals1[method]

            # Handle set/frozenset types
            if isinstance(id_val1, (set, frozenset)):
                for element in id_val1:
                    if element in identity_indices2[method]:
                        for file2 in identity_indices2[method][element]:
                            if file2 not in matched_files2:
                                candidates.add(file2)
                                method_matches[method].add(file2)
            else:
                # Direct lookup for scalar values
                if id_val1 in identity_indices2[method]:
                    for file2 in identity_indices2[method][id_val1]:
                        if file2 not in matched_files2:
                            candidates.add(file2)
                            method_matches[method].add(file2)

        if not candidates:
            continue

        # Verify matches for candidates
        for file2 in candidates:
            if file2 not in identity_values2:
                continue

            id_vals2 = identity_values2[file2]
            match_found = {}

            for method in identity_methods:
                if method not in id_vals1 or method not in id_vals2:
                    match_found[method] = False
                    continue

                id1 = id_vals1[method]
                id2 = id_vals2[method]

                if isinstance(id1, (set, frozenset)) and isinstance(
                    id2, (set, frozenset)
                ):
                    match_found[method] = bool(not id1.isdisjoint(id2))
                else:
                    match_found[method] = bool(id1 == id2)

                if match_found[method]:
                    match_registry1[method][file1] = True
                    match_registry2[method][file2] = True

            # If any method matched, record it
            if any(match_found.values()):
                for method in identity_methods:
                    if match_found[method]:
                        match_results[method][file1].add(file2)

                matched_files1.add(file1)
                matched_files2.add(file2)
                break  # Stop after finding first match

    return (
        match_results,
        match_registry1,
        match_registry2,
        matched_files1,
        matched_files2,
    )


def create_match_upsetplot(
    data: dict, filename: str, pattern: str, identity_methods: List[str]
):
    """
    Create an UpSet plot from the match data.

    Args:
        data: Dictionary of match data
        filename: Path to save the UpSet plot
        pattern: File pattern for the JSON files (used for plot title)
        identity_methods: List of identity methods used for comparison
    """
    data = {method: list(files.values()) for method, files in data.items()}
    df = pd.DataFrame(data)
    data = from_indicators(identity_methods, df)
    upset = UpSet(data, show_counts="%d", show_percentages=True)
    upset.plot()
    title = f"Matching bio.tools files from {pattern}"
    plt.suptitle(title)
    plt.savefig(filename, dpi=300, bbox_inches="tight")
    plt.close()
    logging.info(f"Upset plot {title} saved to {filename}")


def compare_files(
    pattern1: str,
    pattern2: str,
    identity_methods: List[str],
    upset1_path: Optional[str] = None,
    upset2_path: Optional[str] = None,
    num_workers: Optional[int] = None,
) -> dict:
    """
    Compare two sets of bio.tools JSON files based on the given identity methods.

    Args:
        pattern1: File pattern for the first set of JSON files
        pattern2: File pattern for the second set of JSON files
        identity_methods: List of identity methods to use for comparison
        upset1_path: Path to save the Upset plot for the first set
        upset2_path: Path to save the Upset plot for the second set
        num_workers: Number of worker processes for parallel loading

    Returns:
        Dictionary with match_results, only_in_files1, only_in_files2
    """
    if num_workers is None:
        num_workers = min(cpu_count(), 8)

    files1 = glob.glob(pattern1)
    files2 = glob.glob(pattern2)

    logging.info(
        f"Found {len(files1)} files matching pattern1 and {len(files2)} files matching pattern2"
    )

    if not files1:
        raise ValueError(f"No files found matching pattern1: {pattern1}")
    if not files2:
        raise ValueError(f"No files found matching pattern2: {pattern2}")

    # Parallel JSON loading
    logging.info("Loading JSON files from dataset 1...")
    with Pool(num_workers) as pool:
        results1 = list(
            tqdm(
                pool.imap(load_json_with_path, files1),
                total=len(files1),
                desc="Loading dataset 1",
                unit="file",
            )
        )
    json_data1 = {filepath: data for filepath, data in results1 if data is not None}

    logging.info("Loading JSON files from dataset 2...")
    with Pool(num_workers) as pool:
        results2 = list(
            tqdm(
                pool.imap(load_json_with_path, files2),
                total=len(files2),
                desc="Loading dataset 2",
                unit="file",
            )
        )
    json_data2 = {filepath: data for filepath, data in results2 if data is not None}

    logging.info(f"Loaded {len(json_data1)} valid files from dataset 1")
    logging.info(f"Loaded {len(json_data2)} valid files from dataset 2")

    # Build identity indices
    logging.info("Building identity indices...")
    identity_values1, identity_indices1 = build_identity_index(
        json_data1, identity_methods
    )
    identity_values2, identity_indices2 = build_identity_index(
        json_data2, identity_methods
    )

    # Find matches using optimized algorithm
    logging.info("Finding matches...")
    match_results, match_registry1, match_registry2, matched_files1, matched_files2 = (
        find_matches_optimized(
            identity_values1, identity_values2, identity_indices2, identity_methods
        )
    )

    # Calculate unmatched files
    only_in_files1 = set(json_data1.keys()) - matched_files1
    only_in_files2 = set(json_data2.keys()) - matched_files2

    result = {
        "match_results": {
            k: {f: list(v) for f, v in v.items()} for k, v in match_results.items()
        },
        "only_in_files1": list(only_in_files1),
        "only_in_files2": list(only_in_files2),
    }

    # Print summary
    for method, matches in match_results.items():
        print(f"{method} matched: {len(matches)} files")
    print(f"Unmatched files in pattern1: {len(only_in_files1)}")
    print(f"Unmatched files in pattern2: {len(only_in_files2)}")

    # Create upset plots
    if upset1_path or upset2_path:
        logging.info("Creating upset plots...")
        if upset1_path:
            create_match_upsetplot(
                match_registry1, upset1_path, pattern1, identity_methods
            )
        if upset2_path:
            create_match_upsetplot(
                match_registry2, upset2_path, pattern2, identity_methods
            )

    return result
