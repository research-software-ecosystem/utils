# bc2bt - Bioconductor to bio.tools Synchronization

A Python package for converting Bioconductor package metadata to bio.tools format, matching entries between datasets, and updating bio.tools entries.

## Overview

`bc2bt` provides a complete workflow for synchronizing Bioconductor package metadata with the bio.tools registry:

1. **Convert**: Transform Bioconductor JSON metadata into bio.tools format
2. **Compare**: Match entries between Bioconductor and existing bio.tools datasets using configurable identity functions
3. **Update**: Create new entries or update existing ones based on comparison results

## Installation

### From Source

```bash
git clone https://github.com/hmenager/bc2bt.git
cd bc2bt
pip install -e .
```

### Development Installation

```bash
pip install -e ".[dev]"
```

## Requirements

- Python >= 3.9
- Dependencies listed in `requirements.txt`:
  - beautifulsoup4 >= 4.12.0
  - tqdm >= 4.65.0
  - requests >= 2.31.0
  - pandas >= 2.0.0
  - matplotlib >= 3.7.0
  - upsetplot >= 0.8.0

## Usage

### Command Line Interface

The package provides four main commands:

#### 0. Full Workflow (Sync All)

```bash
bc2bt-sync <input_dir> <bt_files_dir> [--work-dir <dir>] [--methods <methods>] [--dry-run]
```

Run all three operations (convert, compare, update) in one go:

```bash
bc2bt-sync bioconductor_json/ biotools_entries/ --dry-run
bc2bt-sync bioconductor_json/ biotools_entries/ --methods name_homepage doi --no-backup
```

**Options:**
- `input_dir`: Directory containing Bioconductor JSON files
- `bt_files_dir`: Directory containing existing bio.tools entries
- `--work-dir`: Working directory for intermediate files (default: `bc2bt_work`)
- `--methods`: Identity methods to use for matching (default: `name_homepage doi`)
- `--workers`: Number of parallel workers
- `--upset1`, `--upset2`: Paths to save UpSet plots
- `--dry-run`: Preview changes without applying
- `--no-backup`: Don't create backup files before updating
- `--keep-work-dir`: Keep working directory after completion (default: auto-cleanup)

1. Convert Bioconductor packages to bio.tools format
2. Compare with existing bio.tools entries using the specified identity methods
3. Update existing entries and create new ones based on matches
4. Clean up the working directory (unless `--keep-work-dir` is used)

#### 1. Convert Bioconductor packages

#### 1. Convert Bioconductor packages

```bash
bc2bt-convert <input_dir> <output_dir> [--existing <existing_dir>]
```

Convert Bioconductor JSON files to bio.tools format:

```bash
bc2bt-convert bioconductor_json/ converted/ --existing biotools_entries/
```

**Options:**
- `input_dir`: Directory containing Bioconductor JSON files
- `output_dir`: Directory to write converted bio.tools JSON files
- `--existing`: Optional directory with existing bio.tools entries to merge

#### 2. Compare datasets

```bash
bc2bt-compare <pattern1> <pattern2> [--methods <methods>] [--results <output>]
```

Find matches between two sets of bio.tools entries:

```bash
bc2bt-compare "biotools/*/*.biotools.json" "converted/*.biotools.json" \
  --methods name_homepage doi \
  --results matches.json \
  --upset1 upset1.png \
  --upset2 upset2.png
```

**Options:**
- `pattern1`, `pattern2`: File patterns for the two datasets (glob format)
- `--methods`: Identity methods to use for matching (default: `name_homepage doi`)
- `--results`: Output file for match results (default: `matches.json`)
- `--upset1`, `--upset2`: Paths to save UpSet plots
- `--workers`: Number of parallel workers

**Available Identity Methods:**
- `name`: Tool name (case-sensitive)
- `name_insensitive`: Tool name (case-insensitive)
- `homepage`: Normalized homepage URL
- `doi`: Publication DOIs
- `name_homepage`: Combined name and homepage (strong duplicate detection)
- `biotoolsID_unprefixed`: bio.tools ID without "bioconductor-" prefix

#### 3. Update bio.tools entries

```bash
bc2bt-update <results_file> <converted_dir> <bt_files_dir> [--dry-run]
```

Apply create/update operations based on match results:

```bash
bc2bt-update matches.json converted/ biotools_entries/ --dry-run
```

**Options:**
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
    input_dir="bioconductor_json/",
    output_dir="converted/",
    existing_biotools_dir="biotools_entries/"
)

# Compare datasets
results = compare_files(
    pattern1="biotools/*/*.biotools.json",
    pattern2="converted/*.biotools.json",
    identity_methods=["name_homepage", "doi"],
    upset1_path="upset1.png",
    upset2_path="upset2.png"
)

# Update entries
summary = update_entries(
    match_results=results,
    converted_files_dir="converted/",
    bt_files_dir="biotools_entries/",
    dry_run=True
)
```

## Module Structure

### `converter.py`

Handles conversion of Bioconductor metadata to bio.tools format:

- `convert_package()`: Convert a single Bioconductor package
- `batch_convert()`: Batch process multiple packages
- `process_authors()`: Parse author strings with roles and ORCIDs
- `extract_publications()`: Extract DOIs from citation HTML
- `merge_with_existing()`: Preserve fields from existing bio.tools entries

### `mapper.py`

Provides identity-based matching between datasets:

- `compare_files()`: Compare two datasets and find matches
- `IdentityRegistry`: Registry for identity functions
- `build_identity_index()`: Pre-compute identity values for fast lookup
- `create_match_upsetplot()`: Generate UpSet plots for match visualization

### `updater.py`

Manages creation and updating of bio.tools entries:

- `Updater`: Class for managing updates with dry-run and backup support
- `update_entries()`: Update existing entries based on match results
- `create_entry()`: Create new bio.tools entries

### `cli.py`

Command-line interface with subcommands for convert, compare, and update operations.

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

- **Preserve**: bio.tools-specific fields (additionDate, biotoolsID, collectionID, etc.)
- **Update**: Bioconductor-derived fields (description, credit, license, version, etc.)
- **Merge**: collectionID to ensure "BioConductor" is included

New entries are created in subdirectories named after their biotoolsID.

## License

MIT License

## Author

Hervé Ménager - herve.menager@pasteur.fr
