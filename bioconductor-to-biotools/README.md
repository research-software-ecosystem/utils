# Bioconductor to bio.tools Integration

## Overview

This project provides tools to update [Bioconductor](https://bioconductor.org/) package entries in [bio.tools](https://bio.tools), part of the [ELIXIR Research Software Ecosystem](https://research-software-ecosystem.github.io/). The goal is to leverage the high-quality metadata produced by the Bioconductor community to enrich and maintain accurate tool descriptions in bio.tools.

The `bc2bt` package provides a complete workflow for synchronizing Bioconductor package metadata with the bio.tools registry.

## Goal

The primary objective is to synchronize Bioconductor package metadata with bio.tools entries by:
- Converting Bioconductor package metadata to the biotoolsSchema format used by bio.tools
- Identifying existing bio.tools entries that correspond to Bioconductor packages
- Creating new entries for Bioconductor packages not yet in bio.tools
- Updating existing bio.tools entries with the latest Bioconductor metadata

## Architecture

The `bc2bt` package provides a modular three-step workflow:

### Step 1: Convert
**Module:** `bc2bt.converter`
**CLI:** `bc2bt-convert`

Transforms Bioconductor JSON metadata into biotoolsSchema-compliant JSON files that can be ingested by bio.tools. Features include:
- Extracts author information with roles (aut/cre/ctb/fnd) and ORCID IDs
- Extracts DOIs from citation HTML files and fetches publication metadata
- Normalizes licenses to SPDX identifiers
- Maps Bioconductor fields to biotoolsSchema
- Merges with existing bio.tools entries to preserve bio.tools-specific fields

### Step 2: Compare (Map)
**Module:** `bc2bt.mapper`
**CLI:** `bc2bt-compare`

Compares the generated biotoolsSchema entries against existing bio.tools entries using configurable identity functions:
- **name_homepage**: Combined name and homepage (strongest match)
- **doi**: Matching publication DOIs
- **name**: Exact tool name match
- **name_insensitive**: Case-insensitive name match
- **homepage**: Normalized homepage URL
- **biotoolsID_unprefixed**: bio.tools ID without "bioconductor-" prefix

Generates match results showing which entries exist in both datasets and produces UpSet plots for visualization.

### Step 3: Update
**Module:** `bc2bt.updater`
**CLI:** `bc2bt-update`

Creates new bio.tools entries and updates existing ones based on match results:
- **Create**: New entries in subdirectories named after their biotoolsID
- **Update**: Merges Bioconductor data while preserving bio.tools-specific fields (additionDate, biotoolsID, collectionID, editPermission, function)
- Supports dry-run mode and backup creation

## Installation

### Prerequisites
- Python 3.9 or higher
- pip (Python package installer)

### Install from Source

```bash
git clone <repository-url>
cd bioconductor-to-biotools
pip install -e .
```

### Development Installation

```bash
pip install -e ".[dev]"
```

### Requirements

Core dependencies (installed automatically):
- beautifulsoup4 >= 4.12.0 (HTML parsing)
- tqdm >= 4.65.0 (progress bars)
- requests >= 2.31.0 (HTTP requests)
- pandas >= 2.0.0 (data processing)
- numpy >= 1.24.0 (numerical operations)
- matplotlib >= 3.7.0 (visualization)
- upsetplot >= 0.8.0 (UpSet plots for match visualization)
- lxml >= 4.9.0 (HTML parsing)
- typing-extensions >= 4.7.0 (type hints)

## Usage

### Full Workflow (Recommended)

Run all three steps in one command:

```bash
bc2bt-sync <input_dir> <bt_files_dir> [options]
```

Example:
```bash
bc2bt-sync imports/bioconductor data/ \
  --work-dir bc2bt_work \
  --methods name_homepage doi \
  --dry-run
```

Options:
- `input_dir`: Directory containing Bioconductor JSON files
- `bt_files_dir`: Directory containing existing bio.tools entries
- `--work-dir`: Working directory for intermediate files (default: `bc2bt_work`)
- `--methods`: Identity methods for matching (default: `name_homepage doi`)
- `--workers`: Number of parallel workers
- `--upset1`, `--upset2`: Paths to save UpSet plots
- `--dry-run`: Preview changes without applying
- `--no-backup`: Don't create backup files before updating
- `--keep-work-dir`: Keep working directory after completion

### Step-by-Step Workflow

#### 1. Convert Bioconductor Packages

Convert Bioconductor JSON files to bio.tools format:

```bash
bc2bt-convert <input_dir> <output_dir> [--existing <existing_dir>]
```

Example:
```bash
bc2bt-convert imports/bioconductor converted/ --existing data/
```

Options:
- `input_dir`: Directory containing Bioconductor .json files (and optional .citation.html files)
- `output_dir`: Directory to write converted bio.tools JSON files
- `--existing`: Optional directory with existing bio.tools entries to merge

#### 2. Compare Datasets

Find matches between two sets of bio.tools entries:

```bash
bc2bt-compare <pattern1> <pattern2> [options]
```

Example:
```bash
bc2bt-compare "data/*/*.biotools.json" "converted/*.biotools.json" \
  --methods name_homepage doi \
  --results matches.json \
  --upset1 upset_existing.png \
  --upset2 upset_converted.png
```

Options:
- `pattern1`, `pattern2`: File patterns for the two datasets (glob format)
- `--methods`: Identity methods for matching (default: `name_homepage doi`)
- `--results`: Output file for match results (default: `matches.json`)
- `--upset1`, `--upset2`: Paths to save UpSet plots
- `--workers`: Number of parallel workers for JSON loading

Available identity methods:
- `name`: Tool name (case-sensitive)
- `name_insensitive`: Tool name (case-insensitive)
- `homepage`: Normalized homepage URL
- `doi`: Publication DOIs
- `name_homepage`: Combined name and homepage (strong duplicate detection)
- `biotoolsID_unprefixed`: bio.tools ID without "bioconductor-" prefix

#### 3. Update bio.tools Entries

Apply create/update operations based on match results:

```bash
bc2bt-update <results_file> <converted_dir> <bt_files_dir> [options]
```

Example:
```bash
bc2bt-update matches.json converted/ data/ --dry-run
```

Options:
- `results_file`: JSON file with match results from compare command
- `converted_dir`: Directory with converted Bioconductor files
- `bt_files_dir`: Directory containing existing bio.tools entries
- `--dry-run`: Preview changes without applying
- `--no-backup`: Don't create backup files before updating

### Python API

The package can also be used programmatically:

```python
from bc2bt import convert_package, batch_convert
from bc2bt import compare_files, IdentityRegistry
from bc2bt import update_entries, create_entry

# Convert a single package
with open("package.json") as f:
    bioc_data = json.load(f)
biotools_entry = convert_package(bioc_data)

# Batch convert
created_files = batch_convert(
    input_dir="imports/bioconductor/",
    output_dir="converted/",
    existing_biotools_dir="data/"
)

# Compare datasets
results = compare_files(
    pattern1="data/*/*.biotools.json",
    pattern2="converted/*.biotools.json",
    identity_methods=["name_homepage", "doi"],
    upset1_path="upset1.png",
    upset2_path="upset2.png"
)

# Update entries
summary = update_entries(
    match_results=results,
    converted_files_dir="converted/",
    bt_files_dir="data/",
    dry_run=True
)
```

## Module Structure

### `bc2bt/converter.py`

Handles conversion of Bioconductor metadata to bio.tools format:

- `convert_package()`: Convert a single Bioconductor package
- `batch_convert()`: Batch process multiple packages
- `process_authors()`: Parse author strings with roles and ORCIDs
- `extract_publications()`: Extract DOIs from citation HTML
- `merge_with_existing()`: Preserve fields from existing bio.tools entries

### `bc2bt/mapper.py`

Provides identity-based matching between datasets:

- `compare_files()`: Compare two datasets and find matches
- `IdentityRegistry`: Registry for identity functions
- `build_identity_index()`: Pre-compute identity values for fast lookup
- `create_match_upsetplot()`: Generate UpSet plots for match visualization

### `bc2bt/updater.py`

Manages creation and updating of bio.tools entries:

- `Updater`: Class for managing updates with dry-run and backup support
- `update_entries()`: Update existing entries based on match results
- `create_entry()`: Create new bio.tools entries

### `bc2bt/license_normalizer.py`

Normalizes free-form license strings to SPDX identifiers:

- `normalize_license()`: Convert license strings to SPDX format
- Supports GPL, LGPL, Apache, MIT, BSD, Artistic, AGPL, and Creative Commons families

### `bc2bt/doi.py`

Fetches publication metadata using DOI resolution:

- `get_publication_metadata()`: Fetch metadata from doi.org with caching
- `clean_jats_abstract()`: Convert JATS XML abstracts to plain text

### `bc2bt/cli.py`

Command-line interface with subcommands for convert, compare, update, and sync operations.

## Input/Output File Formats

### Bioconductor Input

Directory containing:
- `{package}.bioconductor.json`: Package metadata from Bioconductor
- `{package}.citation.html` (optional): Citation HTML for DOI extraction

### bio.tools Output

Standard bio.tools JSON format following biotoolsSchema, written to:
- New entries: `{bt_files_dir}/{biotoolsID}/{biotoolsID}.biotools.json`
- Updated entries: Modified in place with `.backup` files

## Identity Matching Strategy

The package uses configurable identity functions to match entries between datasets:

1. **Strong matching** (`name_homepage`): Matches when both name and homepage are identical
2. **DOI matching** (`doi`): Matches when publications share a DOI
3. **Name matching** (`name`/`name_insensitive`): Matches by tool name
4. **Homepage matching** (`homepage`): Matches by normalized homepage URL

The comparison generates:
- Match results showing which files matched via which methods
- Lists of unmatched files in each dataset
- Optional UpSet plots visualizing overlap between matching methods

## Update Strategy

When updating existing bio.tools entries:

- **Preserve**: bio.tools-specific fields (additionDate, biotoolsCURIE, biotoolsID, collectionID, editPermission, function)
- **Update**: Bioconductor-derived fields (credit, description, documentation, download, homepage, license, publication, version)
- **Merge**: collectionID to ensure "BioConductor" is included

## Console Scripts

After installation, the following commands are available:

- `bc2bt-sync`: Full workflow (convert, compare, update)
- `bc2bt-convert`: Convert Bioconductor packages only
- `bc2bt-compare`: Compare datasets only
- `bc2bt-update`: Update entries based on match results

## License

MIT License

## Author

Hervé Ménager - herve.menager@pasteur.fr

## Development Tools

Parts of this codebase were generated or modified using AI assistance:
- **Tool**: Claude (Anthropic)
- **Date**: March 2026
- **Human Review**: All AI-generated code has been reviewed and tested
