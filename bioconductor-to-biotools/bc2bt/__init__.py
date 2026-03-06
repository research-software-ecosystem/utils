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

from .converter import convert_package, batch_convert, process_authors
from .mapper import (
    IdentityRegistry,
    compare_files,
    IDENTITY_FUNCTIONS,
    identity_name,
    identity_name_insensitive,
    identity_homepage,
    identity_doi,
    identity_name_homepage,
    identity_biotoolsID_unprefixed,
)
from .updater import update_entries, create_entry, Updater

__all__ = [
    # Version
    "__version__",
    # Converter
    "convert_package",
    "batch_convert",
    "process_authors",
    # Mapper
    "IdentityRegistry",
    "compare_files",
    "IDENTITY_FUNCTIONS",
    "identity_name",
    "identity_name_insensitive",
    "identity_homepage",
    "identity_doi",
    "identity_name_homepage",
    "identity_biotoolsID_unprefixed",
    # Updater
    "update_entries",
    "create_entry",
    "Updater",
]
