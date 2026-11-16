"""
bc2bt - Bioconductor to bio.tools synchronization package.

This package provides tools for:
- Converting Bioconductor package metadata to bio.tools format
- Matching entries between datasets using configurable identity functions
- Updating and creating bio.tools entries
"""

__version__ = "0.1.0"
__author__ = "Hervé Ménager"
__email__ = "herve.menager@pasteur.fr"

from .converter import batch_convert, convert_package, process_authors
from .mapper import (
    IDENTITY_FUNCTIONS,
    IdentityRegistry,
    compare_files,
    identity_biotoolsID_unprefixed,
    identity_doi,
    identity_homepage,
    identity_name,
    identity_name_homepage,
    identity_name_insensitive,
)
from .updater import Updater, create_entry, update_entries

__all__ = [
    "IDENTITY_FUNCTIONS",
    # Mapper
    "IdentityRegistry",
    "Updater",
    # Version
    "__version__",
    "batch_convert",
    "compare_files",
    # Converter
    "convert_package",
    "create_entry",
    "identity_biotoolsID_unprefixed",
    "identity_doi",
    "identity_homepage",
    "identity_name",
    "identity_name_homepage",
    "identity_name_insensitive",
    "process_authors",
    # Updater
    "update_entries",
]
