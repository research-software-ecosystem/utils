# --------------------------------------------------------------
# license_normalizer.py   (updated – still a single file, stdlib only)
# --------------------------------------------------------------
"""
Utility that normalises free‑form licence strings to SPDX identifiers.

The new version recognises inputs such as:
    "Apache License (>= 2)"                →  "Apache-2.0"
    "GPL (>= 3) + file LICENSE"            →  "GPL-3.0-or-later"
    "LGPL (>= 2.1)"                        →  "LGPL-2.1-or-later"
    "BSD 3-clause License + file LICENSE" →  "BSD-3-Clause"

Only the `normalize_license` function is part of the public API.
"""

import re
import unicodedata
import difflib
from typing import Optional, Dict, Set

# ----------------------------------------------------------------------
# 1️⃣  Full SPDX identifier set (copy‑paste from https://spdx.org/licenses/)
# ----------------------------------------------------------------------
_SP_dx_IDS: Set[str] = {
    "0BSD",
    "AFL-1.1",
    "AFL-1.2",
    "AFL-2.0",
    "AFL-2.1",
    "AFL-3.0",
    "AGPL-1.0-only",
    "AGPL-1.0-or-later",
    "AGPL-3.0-only",
    "AGPL-3.0-or-later",
    "Apache-2.0",
    "Artistic-1.0",
    "Artistic-2.0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "BSD-4-Clause",
    "CC0-1.0",
    "CC-BY-4.0",
    "CC-BY-NC-4.0",
    "CC-BY-NC-ND-4.0",
    "CC-BY-NC-SA-4.0",
    "CC-BY-ND-4.0",
    "CC-BY-SA-4.0",
    "CDDL-1.0",
    "CDDL-1.1",
    "CECT-1.0",
    "CPL-1.0",
    "EPL-1.0",
    "EPL-2.0",
    "GPL-1.0-only",
    "GPL-1.0-or-later",
    "GPL-2.0-only",
    "GPL-2.0-or-later",
    "GPL-3.0-only",
    "GPL-3.0-or-later",
    "LGPL-2.0-only",
    "LGPL-2.0-or-later",
    "LGPL-2.1-only",
    "LGPL-2.1-or-later",
    "LGPL-3.0-only",
    "LGPL-3.0-or-later",
    "MIT",
    "MPL-2.0",
    "Unlicense",
    "Zlib",
}
# ----------------------------------------------------------------------


# ----------------------------------------------------------------------
# 2️⃣  Hand‑crafted exact‑match table (kept unchanged)
# ----------------------------------------------------------------------
_ALIAS_MAP: Dict[str, str] = {
    # GPL family
    "gpl": "GPL-1.0-or-later",
    "gpl-1": "GPL-1.0-only",
    "gpl-1.0": "GPL-1.0-only",
    "gpl-2": "GPL-2.0-only",
    "gpl-2.0": "GPL-2.0-only",
    "gpl-2.0-or-later": "GPL-2.0-or-later",
    "gpl-3": "GPL-3.0-only",
    "gpl-3.0": "GPL-3.0-only",
    "gpl-3.0-or-later": "GPL-3.0-or-later",
    # LGPL family
    "lgpl": "LGPL-2.0-or-later",
    "lgpl-2": "LGPL-2.0-only",
    "lgpl-2.0": "LGPL-2.0-only",
    "lgpl-2.1": "LGPL-2.1-only",
    "lgpl-3": "LGPL-3.0-only",
    # Apache
    "apache": "Apache-2.0",
    "apache-2": "Apache-2.0",
    "apache-2.0": "Apache-2.0",
    # MIT
    "mit": "MIT",
    "mit-license": "MIT",
    # BSD
    "bsd-2-clause": "BSD-2-Clause",
    "bsd-3-clause": "BSD-3-Clause",
    # Artistic
    "artistic-1.0": "Artistic-1.0",
    "artistic-2.0": "Artistic-2.0",
    # AGPL
    "agpl-3": "AGPL-3.0-only",
    "agpl-3.0-only": "AGPL-3.0-only",
    # Creative‑Commons (short forms)
    "cc0": "CC0-1.0",
    "cc-by-4.0": "CC-BY-4.0",
    "cc-by-nc-nd-4.0": "CC-BY-NC-ND-4.0",
    "cc-by-sa-4.0": "CC-BY-SA-4.0",
    # Misc
    "epl": "EPL-1.0",
    "cpl": "CPL-1.0",
    "mozilla-public-license-2.0": "MPL-2.0",
    "unlimited": "Unlicense",
}
# ----------------------------------------------------------------------


def _strip_noise(raw: str) -> str:
    """
    Remove the typical “+ file LICENSE”, “file …”, and trailing whitespace
    that are not part of the licence name itself.
    """
    s = raw.lower()
    s = re.sub(r"\+.*$", "", s)  # drop “+ file LICENSE”
    s = re.sub(r"file.*$", "", s)  # drop plain “file …”
    return s.strip()


def _extract_family_version(raw: str) -> tuple:
    """
    Parse the *original* string (before we destroy punctuation) and return
    a tuple ``(family, major, later_flag)``.

    * *family* – one of the known families (gpl, lgpl, apache, bsd, mit,
      artistic, agpl, cc0, cc‑by, cc‑by‑nc‑nd, cc‑by‑sa …).  ``None`` if not found.
    * *major* – the numeric part (e.g. ``3`` for “GPL 3”, ``2.1`` for “LGPL 2.1”).
                ``None`` if the string does not contain a number.
    * *later* – ``True`` if the raw string contains a “>=”, “>”, “or later”
                or an explicit “or‑later” marker; otherwise ``False``.
    """
    low = raw.lower()

    # ----- family -------------------------------------------------------
    families = [
        "gpl",
        "lgpl",
        "apache",
        "bsd",
        "mit",
        "artistic",
        "agpl",
        "cc0",
        "cc-by-nc-nd",
        "cc-by-nc",
        "cc-by-sa",
        "cc-by",
        "epl",
        "cpl",
    ]
    family = None
    for f in families:
        if re.search(r"\b" + re.escape(f) + r"\b", low):
            family = f
            break

    # ----- numeric version -----------------------------------------------
    # Picks the first number after the family name (if any)
    version = None
    if family:
        # look for something like “>= 2.1”, “==3”, “3.0”, “2” etc.
        m = re.search(rf"{re.escape(family)}[^0-9]*([0-9]+(?:\.[0-9]+)?)", low)
        if m:
            version = m.group(1)

    # ----- later flag ----------------------------------------------------
    later = bool(re.search(r">=|>|or[-\s]*later|or[-\s]*later", low))

    return family, version, later


def _clean_string_for_exact_match(raw: str) -> str:
    """
    Normalise a licence string for the *exact‑match* stage.
    This is the same routine you already had, but it is now applied **after**
    we have already extracted the family/version information.
    """
    s = _strip_noise(raw)  # drop “+ file …” etc.
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[\s_]+", "-", s)  # collapse space/underscore -> '-'
    s = re.sub(r"[^a-z0-9\-]", "", s)  # keep only alphanum and '-'
    s = s.strip("-")
    return s.lower()


def _family_fallback(
    family: Optional[str], version: Optional[str], later: bool
) -> Optional[str]:
    """
    Build a SPDX identifier from the data extracted by ``_extract_family_version``.
    The function is intentionally *conservative* – it only returns a value
    when the combination is unambiguous.
    """
    if family in {"apache"}:
        # SPDX only defines Apache‑2.0, any version specifier maps to that.
        return "Apache-2.0"

    if family == "mit":
        return "MIT"

    if family == "bsd":
        # BSD 2‑clause or 3‑clause – we look for the number in the version string
        if version and version.startswith("2"):
            return "BSD-2-Clause"
        if version and version.startswith("3"):
            return "BSD-3-Clause"
        # fallback to generic BSD (rare)
        return None

    if family == "artistic":
        if version and version.startswith("1"):
            return "Artistic-1.0"
        if version and version.startswith("2"):
            return "Artistic-2.0"
        return None

    if family == "agpl":
        # only AGPL‑3.0‑only exists in SPDX at the moment
        return "AGPL-3.0-only"

    if family in {"epl", "cpl"}:
        return "EPL-1.0" if family == "epl" else "CPL-1.0"

    if family in {"cc0", "cc-by", "cc-by-nc", "cc-by-nc-nd", "cc-by-sa"}:
        # map the short forms we already have in the alias table
        mapping = {
            "cc0": "CC0-1.0",
            "cc-by": "CC-BY-4.0",
            "cc-by-nc": "CC-BY-NC-4.0",
            "cc-by-nc-nd": "CC-BY-NC-ND-4.0",
            "cc-by-sa": "CC-BY-SA-4.0",
        }
        return mapping.get(family)

    # ----- GPL / LGPL families -------------------------------------------
    if family == "gpl":
        if not version:
            return None
        major = version.split(".")[0]  # keep only the major part
        if later:
            return f"GPL-{major}.0-or-later"
        else:
            return f"GPL-{major}.0-only"

    if family == "lgpl":
        if not version:
            return None
        major = version.split(".")[0]
        # LGPL also has a 2.1 sub‑branch – keep the full version if it exists
        if later:
            return f"LGPL-{version}-or-later"
        else:
            # When we only have “2” we assume “2.0‑only”
            if major == "2" and not version.startswith("2.1"):
                return "LGPL-2.0-only"
            return f"LGPL-{version}-only"

    return None


def _fuzzy_match(
    candidate: str, spdx_set: Set[str], cutoff: float = 0.92
) -> Optional[str]:
    """
    Conservative fuzzy matcher – uses difflib and only returns a match if
    the similarity ratio is >= *cutoff*.
    """
    lowered = {s.lower(): s for s in spdx_set}
    matches = difflib.get_close_matches(
        candidate.lower(), lowered.keys(), n=1, cutoff=cutoff
    )
    if matches:
        return lowered[matches[0]]
    return None


def normalize_license(
    raw_license: str,
    *,
    alias_map: Optional[Dict[str, str]] = None,
    spdx_ids: Optional[Set[str]] = None,
    fuzzy_cutoff: float = 0.92,
) -> Optional[str]:
    """
    Convert a possibly noisy licence string to an SPDX identifier.

    Parameters
    ----------
    raw_license : str
        The licence text you extracted from JSON / CSV / etc.
    alias_map : dict | None
        Optional custom mapping; defaults to the built‑in ``_ALIAS_MAP``.
    spdx_ids : set | None
        Optional SPDX identifier set; defaults to the built‑in ``_SP_dx_IDS``.
    fuzzy_cutoff : float
        Minimum similarity (0‑1) required for the fuzzy fallback.

    Returns
    -------
    str | None
        The SPDX identifier (e.g. ``"MIT"``, ``"Apache-2.0"``, ``"GPL-3.0-or-later"``)
        or ``None`` if the function cannot decide with high confidence.

    Examples
    --------
    >>> normalize_license('Apache License (>= 2)')
    'Apache-2.0'
    >>> normalize_license('GPL (>= 3) + file LICENSE')
    'GPL-3.0-or-later'
    >>> normalize_license('GPL (>= 2) + file LICENSE')
    'GPL-2.0-or-later'
    >>> normalize_license('file LICENSE') is None
    True
    """
    # ------------------------------------------------------------------
    # 1️⃣ Choose data structures
    # ------------------------------------------------------------------
    alias = alias_map if alias_map is not None else _ALIAS_MAP
    spdx = spdx_ids if spdx_ids is not None else _SP_dx_IDS

    # ------------------------------------------------------------------
    # 2️⃣ Try the *exact‑alias* table first (fast, 100 % confidence)
    # ------------------------------------------------------------------
    cleaned = _clean_string_for_exact_match(raw_license)
    if cleaned in alias:
        return alias[cleaned]

    # ------------------------------------------------------------------
    # 3️⃣ Direct SPDX‑ID match (case‑insensitive)
    # ------------------------------------------------------------------
    if cleaned.upper() in spdx:
        return cleaned.upper()

    # ------------------------------------------------------------------
    # 4️⃣ Family‑based fallback – this is the new part that handles
    #     "GPL (>= 3)", "Apache License (>= 2)", etc.
    # ------------------------------------------------------------------
    family, version, later = _extract_family_version(raw_license)
    fallback = _family_fallback(family, version, later)
    if fallback:
        return fallback

    # ------------------------------------------------------------------
    # 5️⃣ Conservative fuzzy matcher (high cutoff)
    # ------------------------------------------------------------------
    fuzzy = _fuzzy_match(cleaned, spdx, cutoff=fuzzy_cutoff)
    if fuzzy:
        return fuzzy

    # ------------------------------------------------------------------
    # 6️⃣ No confident match – caller must decide what to do
    # ------------------------------------------------------------------
    return None


# ----------------------------------------------------------------------
# 7️⃣ Simple demo (runs when the file is executed directly)
# ----------------------------------------------------------------------
if __name__ == "__main__":
    demo = [
        "AGPL-3",
        "Apache License (>= 2)",
        "BSD 3-clause License + file LICENSE",
        "GPL (>= 3) + file LICENSE",
        "GPL (>= 3) + file LICENCE",
        "GPL (>=3) | file LICENSE",
        "GPL (>= 3); File LICENSE",
        "GPL (>= 2) + file LICENSE",
        "MIT",
        "MIT + file LICENCE",
        "file LICENSE",
    ]

    print(f"{'RAW INPUT':45}   SPDX ID")
    print("-" * 70)
    for line in demo:
        spdx = normalize_license(line)
        print(f"{line:45}   {spdx or '❓ (no match)'}")
