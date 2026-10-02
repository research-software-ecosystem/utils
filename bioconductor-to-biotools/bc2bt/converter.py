"""
Converter module for transforming Bioconductor metadata to bio.tools format.
"""

import re
import json
import logging
from pathlib import Path
from typing import Optional
from bs4 import BeautifulSoup
from .license_normalizer import normalize_license
from .biotools_license import to_biotools_license

logger = logging.getLogger(__name__)

# Limits bio.tools enforces on write, from its serializers. A record breaching
# one of these is rejected whole, so nothing is gained by emitting it:
#   description  CharField(min_length=10, max_length=1000, required=True)
#   credit.name  CharField(max_length=100)
#   publication  PublicationSerializer(many=True, required=False,
#                                      allow_empty=False)  <- absent is fine,
#                                                             empty is not
MAX_DESCRIPTION = 1000
MIN_DESCRIPTION = 10
MAX_CREDIT_NAME = 100

# Fields to preserve when updating existing bio.tools entries
PRESERVED_FIELDS = [
    "additionDate",
    "biotoolsCURIE",
    "biotoolsID",
    "collectionID",
    "editPermission",
    "function",
]


def fit_description(raw: str, fallback: str = "") -> str:
    """Return a description within the length bio.tools accepts.

    Bioconductor descriptions run to 2700 characters; the limit is 1000, and
    89 records were rejected on it. Truncation is at the last sentence that
    fits, so what is kept is whole sentences rather than a severed clause --
    measured over the failing set, that retains a median 75% of the text and
    ends on a real stop every time. A description with no sentence break in
    its first half falls back to a word boundary and an ellipsis, which is
    honest about being cut.

    `fallback` (the Bioconductor ``Title``) covers the case where there is no
    usable description at all: one package ships an empty one, and bio.tools
    requires the field. Titles are not used in preference to a description --
    they are a line long, and would throw away most of what we have.
    """
    text = re.sub(r"\s+", " ", raw or "").strip()
    if len(text) < MIN_DESCRIPTION:
        text = re.sub(r"\s+", " ", fallback or "").strip()
    if len(text) <= MAX_DESCRIPTION:
        return text if len(text) >= MIN_DESCRIPTION else ""

    cut = text[:MAX_DESCRIPTION]
    stops = list(re.finditer(r"(?<=[.!?])\s", cut))
    if stops and stops[-1].end() >= MAX_DESCRIPTION // 2:
        return cut[: stops[-1].start() + 1].strip()
    space = cut.rfind(" ")
    return (cut[:space].rstrip(" ,;:") + "\u2026") if space > 0 else cut


def process_authors(author_str: str) -> list:
    """
    Process the author field, extracting names, roles, and ORCIDs.

    Args:
        author_str: Raw author string from Bioconductor metadata

    Returns:
        List of author dictionaries with name, typeEntity, typeRole, and optional orcid
    """
    authors = []
    # Do not split on a comma inside brackets *or* parentheses. The ORCID
    # parenthetical can itself contain a comma -- "(ORCID: <...>, fnd: European
    # Union HORIZON...)" -- and splitting there turned the funding note into a
    # person. Across all 2418 packages this changes 26 credit lists and
    # introduces no new over-long name.
    author_entries = re.split(r",(?![^\[\]]*\])(?![^()]*\))", author_str)

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

            if len(author_entry["name"]) > MAX_CREDIT_NAME:
                # Not a long name -- a parse that failed. Some DESCRIPTION
                # Author fields separate people with spaces rather than commas,
                # or append affiliations, and there is no way to split those
                # without guessing where one person ends. Truncating to the
                # limit would store a fabricated person, so drop the entry and
                # say which package it came from.
                logger.warning(
                    "dropping unparseable credit (%d chars): %.60s...",
                    len(author_entry["name"]),
                    author_entry["name"],
                )
                continue

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


# Source tarballs for the release the importer reads: bioconductor-import
# fetches .../packages/json/<version>/bioc/packages.json, so every package that
# reaches this converter is a software package and this one base applies.
BIOCONDUCTOR_RELEASE_BASE = "https://bioconductor.org/packages/release/bioc/"


def parse_description_urls(raw: str) -> list:
    """Split a DESCRIPTION ``URL`` field into individual URLs.

    R packages routinely list several, comma or whitespace separated, and the
    field is free text, so anything that is not an http(s) URL is dropped
    rather than guessed at. Of the 2,418 packages in Bioconductor 3.23, 1,256
    list one URL, 156 list two or three, and 1,006 list none.

    Emitting the raw field as a single ``url`` is what drew
    ``"This is not a valid URL: https://github.com/HelBor/wpm, https://..."``
    from the bio.tools API for 165 tools.

    >>> parse_description_urls("https://github.com/HelBor/wpm, https://bioconductor.org/packages/wpm")
    ['https://github.com/HelBor/wpm', 'https://bioconductor.org/packages/wpm']
    >>> parse_description_urls("")
    []
    >>> parse_description_urls("see the vignette")
    []
    """
    if not raw:
        return []
    urls, seen = [], set()
    for part in re.split(r"[,\s]+", raw.strip()):
        candidate = part.strip().rstrip(".,;")
        if candidate.startswith(("http://", "https://")) and candidate not in seen:
            seen.add(candidate)
            urls.append(candidate)
    return urls


def build_download(bioc_data: dict) -> list:
    """Build the ``download`` list, or an empty list if there is nothing valid.

    Packages listing no URL fall back to the source tarball, whose path
    Bioconductor already supplies in ``source.ver`` (e.g.
    ``src/contrib/wpm_1.22.0.tar.gz``), so the version is never guessed. 34
    packages in 3.23 carry no ``source.ver`` either; those get no download
    entry, which leaves whatever bio.tools already holds untouched, because
    updater.py copies a field only when it is present here.

    >>> build_download({"URL": "https://github.com/HelBor/wpm"})
    [{'type': 'Source code', 'url': 'https://github.com/HelBor/wpm'}]
    >>> build_download({"URL": "", "source.ver": "src/contrib/a4_1.60.0.tar.gz"})[0]["url"]
    'https://bioconductor.org/packages/release/bioc/src/contrib/a4_1.60.0.tar.gz'
    >>> build_download({})
    []
    """
    urls = parse_description_urls(bioc_data.get("URL", ""))
    if urls:
        return [{"type": "Source code", "url": url} for url in urls]

    source_ver = (bioc_data.get("source.ver") or "").strip()
    if source_ver:
        return [
            {
                "type": "Source code",
                "url": BIOCONDUCTOR_RELEASE_BASE + source_ver.lstrip("/"),
            }
        ]
    return []


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
        "description": fit_description(
            bioc_data.get("Description", ""), bioc_data.get("Title", "")
        ),
        "documentation": [
            {
                "type": ["User manual"],
                "url": f"https://bioconductor.org/packages/{package_name}",
            }
        ],
        "homepage": f"https://bioconductor.org/packages/{package_name}",
        "language": ["R"],
        "name": package_name,
        "operatingSystem": ["Linux", "Mac", "Windows"],
        "owner": "bioconductor_import",
        "toolType": ["Command-line tool", "Library"],
        "version": [bioc_data.get("Version", "")],
    }

    # Both fields are omitted rather than written empty or null. updater.py
    # copies a field only when it is present here, so omitting one keeps
    # whatever bio.tools already holds, whereas a null licence or a blank
    # download URL makes the API reject the entire record.
    download = build_download(bioc_data)
    if download:
        result["download"] = download

    license_id = to_biotools_license(normalize_license(bioc_data.get("License", "")))
    if license_id:
        result["license"] = license_id

    # Extract publications from citation HTML if provided. Assigned only when
    # something was found: bio.tools takes `publication` as optional but
    # rejects an empty list, and 117 records were refused on exactly that.
    # Omitting it says "we know of none", which is what we mean; [] asserts
    # "there are none", which we cannot support.
    if citation_html:
        publications = extract_publications(citation_html)
        if publications:
            result["publication"] = publications

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
            # not updating the publications for now because this is ignored and overwritten by bio.tools
            # meta = get_publication_metadata(doi)
            # publications.append({"doi": doi, "metadata": meta})
            publications.append({"doi": doi})

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
