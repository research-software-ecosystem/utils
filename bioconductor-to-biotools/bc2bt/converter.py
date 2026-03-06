"""
Converter module for transforming Bioconductor metadata to bio.tools format.
"""

import re
import json
from pathlib import Path
from typing import Optional
from bs4 import BeautifulSoup
from .license_normalizer import normalize_license
from .doi import get_publication_metadata

# Fields to preserve when updating existing bio.tools entries
PRESERVED_FIELDS = [
    "additionDate",
    "biotoolsCURIE",
    "biotoolsID",
    "collectionID",
    "editPermission",
    "function",
]


def process_authors(author_str: str) -> list:
    """
    Process the author field, extracting names, roles, and ORCIDs.

    Args:
        author_str: Raw author string from Bioconductor metadata

    Returns:
        List of author dictionaries with name, typeEntity, typeRole, and optional orcid
    """
    authors = []
    author_entries = re.split(r",(?![^\[]*\])", author_str)

    for entry in author_entries:
        entry = entry.strip()

        roles_match = re.findall(r"\[([^\]]+)\]", entry)
        roles = [role.strip() for group in roles_match for role in group.split(",")]

        orcid_match = re.search(
            r"\(<(https://orcid\.org/\d{4}-\d{4}-\d{4}-\d{4})>\)", entry
        )
        orcid = orcid_match.group(1) if orcid_match else None

        name_match = re.match(r"^[^\[\(<]+", entry)
        if name_match:
            type_role = []
            author_entry = {"name": name_match.group(0).strip()}

            if "aut" in roles or "cre" in roles or "ctb" in roles:
                author_entry["typeEntity"] = "Person"
            elif "fnd" in roles:
                author_entry["typeEntity"] = "Funding agency"

            if "ctb" in roles or "fnd" in roles:
                type_role.append("Contributor")
            if "aut" in roles:
                type_role.append("Developer")
            if "cre" in roles:
                type_role.append("Maintainer")

            if orcid:
                author_entry["orcid"] = orcid
            if type_role:
                author_entry["typeRole"] = type_role

            authors.append(author_entry)

    return authors


def get_biotools_id(data: dict) -> str:
    """
    Generate the bio.tools ID from Bioconductor JSON data.

    Args:
        data: Bioconductor package metadata

    Returns:
        bio.tools ID (e.g., "bioconductor-limma")
    """
    return f"bioconductor-{data['Package'].lower()}"


def convert_package(
    bioc_data: dict,
    citation_html: Optional[str] = None,
    existing_biotools: Optional[dict] = None,
) -> dict:
    """
    Convert a Bioconductor package dictionary to bio.tools format.

    Args:
        bioc_data: Bioconductor package metadata dictionary
        citation_html: Optional HTML content from citation file
        existing_biotools: Optional existing bio.tools entry to preserve fields from

    Returns:
        bio.tools formatted dictionary
    """
    package_name = bioc_data.get("Package", "")

    result = {
        "biotoolsCURIE": f"biotools:{get_biotools_id(bioc_data)}",
        "biotoolsID": get_biotools_id(bioc_data),
        "collectionID": ["BioConductor"],
        "credit": process_authors(bioc_data.get("Author", "")),
        "description": bioc_data.get("Description", ""),
        "documentation": [
            {
                "type": ["User manual"],
                "url": f"https://bioconductor.org/packages/{package_name}",
            }
        ],
        "download": [{"type": "Source code", "url": f"{bioc_data.get('URL', '')}"}],
        "homepage": f"https://bioconductor.org/packages/{package_name}",
        "language": ["R"],
        "license": normalize_license(bioc_data.get("License", "")),
        "name": package_name,
        "operatingSystem": ["Linux", "Mac", "Windows"],
        "owner": "bioconductor_import",
        "toolType": ["Command-line tool", "Library"],
        "version": [bioc_data.get("Version", "")],
    }

    # Extract publications from citation HTML if provided
    if citation_html:
        result["publication"] = extract_publications(citation_html)

    # Preserve fields from existing bio.tools entry
    if existing_biotools:
        result = merge_with_existing(result, existing_biotools)

    return result


def extract_publications(citation_html: str) -> list:
    """
    Extract publication DOIs from Bioconductor citation HTML.

    Args:
        citation_html: HTML content from citation file

    Returns:
        List of publication dictionaries with DOI entries
    """
    publications = []
    soup = BeautifulSoup(citation_html, "html.parser")

    for link in soup.find_all("a", href=True):
        href = link["href"].strip()
        if "doi.org" in href:
            doi = href.split("doi.org/")[-1]
            meta = get_publication_metadata(doi)
            publications.append({"doi": doi, "metadata": meta})

    return publications


def merge_with_existing(new_data: dict, existing_data: dict) -> dict:
    """
    Merge new bioconductor data with existing bio.tools entry.
    Preserves bio.tools-specific fields from the existing entry.

    Args:
        new_data: Newly generated bio.tools data from Bioconductor
        existing_data: Existing bio.tools entry

    Returns:
        Merged dictionary
    """
    result = new_data.copy()

    for key in PRESERVED_FIELDS:
        if key in existing_data:
            result[key] = existing_data[key]

    return result


def batch_convert(
    input_dir: str,
    output_dir: str,
    existing_biotools_dir: Optional[str] = None,
) -> list:
    """
    Batch convert all Bioconductor JSON files in input directory.

    Args:
        input_dir: Directory containing Bioconductor .json files and .citation.html files
        output_dir: Directory to write converted bio.tools JSON files
        existing_biotools_dir: Optional directory with existing bio.tools entries for merging

    Returns:
        List of output file paths created
    """
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    output_files = []

    for json_file in input_path.glob("*.bioconductor.json"):
        base_name = json_file.stem
        citation_file = input_path / f"{base_name}.citation.html"

        # Load Bioconductor data
        with open(json_file, "r", encoding="utf-8") as f:
            bioc_data = json.load(f)

        # Load citation HTML if available
        citation_html = None
        if citation_file.exists():
            with open(citation_file, "r", encoding="utf-8") as f:
                citation_html = f.read()

        # Load existing bio.tools entry if available
        existing_data = None
        if existing_biotools_dir:
            biotools_id = get_biotools_id(bioc_data)
            existing_file = Path(existing_biotools_dir) / f"{biotools_id}.biotools.json"
            if existing_file.exists():
                with open(existing_file, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)

        # Convert package
        processed = convert_package(bioc_data, citation_html, existing_data)

        # Write output
        output_file = output_path / f"{processed['biotoolsID']}.biotools.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(processed, f, indent=4)

        output_files.append(str(output_file))
    return output_files
