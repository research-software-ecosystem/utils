"""Shared syntactic value checkers for the per-source import validators.

Every checker is a pure, offline predicate: it never touches the network.
`make_format_checker()` registers them all as JSON Schema formats, so a
schema can request e.g. ``"format": "orcid"`` on a string field.

Formats listed in `WARNING_FORMATS` are reported as warnings instead of
errors by the validation runner.
"""

import re
from urllib.parse import urlparse

from jsonschema import FormatChecker

# Formats whose violations are soft findings (style/registry drift), not
# hard syntax errors.
WARNING_FORMATS = frozenset({"spdx-license"})

_ORCID_RE = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")
_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
_EMAIL_RE = re.compile(
    r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$"
)
_PMID_RE = re.compile(r"^[1-9]\d{0,7}$")
_PMCID_RE = re.compile(r"^PMC\d+$")
_EDAM_URI_RE = re.compile(
    r"^https?://edamontology\.org/(topic|operation|data|format)_\d{4}$"
)
_BIOTOOLS_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_ISO_DATE_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")
_ISO_DATETIME_RE = re.compile(
    r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])"
    r"[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$"
)
_MD5_RE = re.compile(r"^[0-9a-fA-F]{32}$")
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_SCICRUNCH_RE = re.compile(r"^SCR_\d+$")
# Debian policy: [epoch:]upstream-version[-debian-revision]
_DEBIAN_VERSION_RE = re.compile(r"^(\d+:)?[0-9][A-Za-z0-9.+~:-]*?(-[A-Za-z0-9.+~]+)?$")
_SEMVERISH_RE = re.compile(r"^\d+(\.\d+)*([.+_~-]?[A-Za-z0-9.+_~-]*)$")

# Prefixes seen in CURIE-style identifier lists (biocontainers `identifiers`,
# bioconda `extra.identifiers`, debian registries).
CURIE_PREFIXES = frozenset(
    {
        "biotools",
        "doi",
        "PMID",
        "pmid",
        "usegalaxy-eu",
        "RRID",
        "arxiv",
        "isbn",
    }
)

# A deliberately small vendored subset of SPDX identifiers plus the special
# values bio.tools accepts; only used at warning level.
SPDX_LICENSES = frozenset(
    {
        "0BSD",
        "AFL-3.0",
        "AGPL-1.0",
        "AGPL-3.0",
        "AGPL-3.0-only",
        "AGPL-3.0-or-later",
        "Apache-1.1",
        "Apache-2.0",
        "APSL-2.0",
        "Artistic-1.0",
        "Artistic-2.0",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "BSD-4-Clause",
        "BSL-1.0",
        "CC0-1.0",
        "CC-BY-3.0",
        "CC-BY-4.0",
        "CC-BY-NC-4.0",
        "CC-BY-NC-SA-4.0",
        "CC-BY-SA-4.0",
        "CDDL-1.0",
        "CECILL-2.1",
        "ECL-2.0",
        "EFL-2.0",
        "EPL-1.0",
        "EPL-2.0",
        "EUPL-1.1",
        "EUPL-1.2",
        "GPL-1.0",
        "GPL-2.0",
        "GPL-2.0-only",
        "GPL-2.0-or-later",
        "GPL-3.0",
        "GPL-3.0-only",
        "GPL-3.0-or-later",
        "ISC",
        "LGPL-2.0",
        "LGPL-2.1",
        "LGPL-2.1-only",
        "LGPL-2.1-or-later",
        "LGPL-3.0",
        "LGPL-3.0-only",
        "LGPL-3.0-or-later",
        "MIT",
        "MPL-1.1",
        "MPL-2.0",
        "NCSA",
        "OFL-1.1",
        "OSL-3.0",
        "PostgreSQL",
        "Python-2.0",
        "Unlicense",
        "WTFPL",
        "Zlib",
        # bio.tools special values
        "Freeware",
        "Proprietary",
        "Other",
        "Not licensed",
        "Unlicensed",
    }
)


def is_orcid(value):
    """ORCID iD, bare or as an https://orcid.org/ URL, with valid checksum."""
    if not isinstance(value, str):
        return True
    body = value
    for prefix in ("https://orcid.org/", "http://orcid.org/", "orcid.org/"):
        if body.startswith(prefix):
            body = body[len(prefix) :]
            break
    if not _ORCID_RE.match(body):
        return False
    digits = body.replace("-", "")
    total = 0
    for ch in digits[:-1]:
        total = (total + int(ch)) * 2
    remainder = total % 11
    check = (12 - remainder) % 11
    expected = "X" if check == 10 else str(check)
    return digits[-1] == expected


def is_doi(value):
    """DOI, bare or with a doi:/https://doi.org/ prefix."""
    if not isinstance(value, str):
        return True
    body = value
    for prefix in ("https://doi.org/", "http://doi.org/", "doi.org/", "doi:"):
        if body.lower().startswith(prefix.lower()):
            body = body[len(prefix) :]
            break
    # old SICI-style DOIs legitimately contain '<' and '>'
    return bool(_DOI_RE.match(body))


def is_url(value):
    if not isinstance(value, str):
        return True
    if any(c.isspace() for c in value):
        return False
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https", "ftp") and bool(parsed.netloc)


def is_email(value):
    if not isinstance(value, str):
        return True
    return bool(_EMAIL_RE.match(value)) and ".." not in value.split("@")[0]


def is_pmid(value):
    if not isinstance(value, str):
        return True
    return bool(_PMID_RE.match(value))


def is_pmcid(value):
    if not isinstance(value, str):
        return True
    return bool(_PMCID_RE.match(value))


def is_edam_uri(value):
    if not isinstance(value, str):
        return True
    return bool(_EDAM_URI_RE.match(value))


def is_biotools_id(value):
    if not isinstance(value, str):
        return True
    return bool(_BIOTOOLS_ID_RE.match(value))


def is_biotools_curie(value):
    if not isinstance(value, str):
        return True
    return (
        value.startswith("biotools:")
        and is_biotools_id(value[len("biotools:") :])
        and len(value) > len("biotools:")
    )


def is_curie(value):
    """`prefix:rest` with a known prefix; the DOI payload is checked too."""
    if not isinstance(value, str):
        return True
    prefix, sep, rest = value.partition(":")
    if not sep or not rest:
        return False
    if prefix not in CURIE_PREFIXES:
        return False
    if prefix == "doi":
        return is_doi(rest)
    if prefix in ("PMID", "pmid"):
        return is_pmid(rest)
    if prefix == "biotools":
        return is_biotools_id(rest)
    return True


def is_iso_date(value):
    if not isinstance(value, str):
        return True
    return bool(_ISO_DATE_RE.match(value))


def is_iso_datetime(value):
    if not isinstance(value, str):
        return True
    return bool(_ISO_DATETIME_RE.match(value))


def is_md5(value):
    if not isinstance(value, str):
        return True
    return bool(_MD5_RE.match(value))


def is_sha256(value):
    if not isinstance(value, str):
        return True
    return bool(_SHA256_RE.match(value))


def is_scicrunch_id(value):
    if not isinstance(value, str):
        return True
    return bool(_SCICRUNCH_RE.match(value))


def is_debian_version(value):
    if not isinstance(value, str):
        return True
    return bool(_DEBIAN_VERSION_RE.match(value))


def is_semverish(value):
    if not isinstance(value, str):
        return True
    return bool(_SEMVERISH_RE.match(value))


def is_spdx_license(value):
    """Warning-level: identifier in the vendored SPDX subset."""
    if not isinstance(value, str):
        return True
    base = value
    for suffix in ("-only", "-or-later", "+"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return value in SPDX_LICENSES or base in SPDX_LICENSES


FORMAT_CHECKS = {
    "orcid": is_orcid,
    "doi": is_doi,
    "url": is_url,
    "email": is_email,
    "pmid": is_pmid,
    "pmcid": is_pmcid,
    "edam-uri": is_edam_uri,
    "biotools-id": is_biotools_id,
    "biotools-curie": is_biotools_curie,
    "curie": is_curie,
    "iso-date": is_iso_date,
    "iso-datetime": is_iso_datetime,
    "md5": is_md5,
    "sha256": is_sha256,
    "scicrunch-id": is_scicrunch_id,
    "debian-version": is_debian_version,
    "semverish": is_semverish,
    "spdx-license": is_spdx_license,
}


def make_format_checker():
    """A jsonschema FormatChecker with every shared format registered."""
    checker = FormatChecker()
    for name, func in FORMAT_CHECKS.items():
        checker.checks(name)(func)
    return checker
