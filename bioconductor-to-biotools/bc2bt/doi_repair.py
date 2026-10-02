"""Turn the DOI strings found in citation pages into DOIs bio.tools accepts.

Bioconductor citation pages are generated from BibTeX, and what reaches the
href is often not a bare DOI: percent-encoded separators, BibTeX braces left
in place, a backslash-escaped slash, a `dx.doi.org` prefix with the slash
missing, an arXiv identifier, or simply the wrong string. Sixteen of them were
rejected in the 2026-09-30 import.

Two stages, and the distinction between them matters:

normalise()  Decoding and unwrapping only. Nothing is added or inferred, so it
             cannot produce a DOI that was not already written down. Ten of the
             sixteen come back valid from this alone.

candidates() Repairs, restricted to the lossless kind: the original string
             survives verbatim and what is added is a constant true of every
             DOI of that kind, so no rule infers which paper was meant. Even
             so, none is used until the DOI registry confirms it exists. An
             unverified repair is never emitted: a DOI pointing at the wrong
             paper is false provenance, and worse than no DOI at all. Two more
             of the sixteen come back this way.

The remaining four are discarded with a warning rather than sent. Deliberately
no requests_cache here: importing doi.py installs a global sqlite cache as a
side effect, and a verification memo for the handful of candidates in a run
does not need one.
"""

import logging
import re
from urllib.parse import quote, unquote

import requests

logger = logging.getLogger(__name__)

# bio.tools' own IsDOIValidator, so what passes here is what it will accept.
DOI = re.compile(r"^10\.\d{4,9}/[-.\[\]<>_;()/:a-zA-Z0-9]+$")

# Handles rather than Crossref: Crossref 404s on DataCite-registered DOIs,
# including every arXiv one, and would reject a repair that is in fact correct.
HANDLE_API = "https://doi.org/api/handles/"
TIMEOUT = 15

# candidate -> exists. Only definite answers are kept, so a transient network
# failure does not condemn a DOI for the rest of the run.
_verified: dict[str, bool] = {}


def normalise(raw: str) -> str:
    """Decode and unwrap a DOI string. Adds nothing that was not there."""
    text = (raw or "").strip()
    # Repeatedly: %252F is a percent-encoded percent sign, and one pass leaves
    # %2F behind.
    for _ in range(3):
        decoded = unquote(text)
        if decoded == text:
            break
        text = decoded
    # A fixpoint rather than one pass each, because the wrappers nest in either
    # order: "{https://doi.org/10.x}" needs the brace off before the prefix,
    # and "https://doi.org/{10.x}" needs the prefix off before the brace. Doing
    # it once in a fixed order left a leading brace on the second form, which
    # is how half of generxcluster's citations were being discarded.
    for _ in range(6):
        before = text
        text = text.strip().strip("{}[]").strip()
        # A BibTeX \/ survives as a literal backslash. No DOI contains one.
        text = text.replace("\\", "")
        text = re.sub(r"(?i)^(?:https?://)?(?:dx\.)?doi\.org/?", "", text)
        text = re.sub(r"(?i)^doi:\s*", "", text)
        text = text.strip().rstrip(".,;")
        if text == before:
            break
    return text


def candidates(text: str) -> list[str]:
    """Ordered repair candidates. Each must still be verified before use.

    Only lossless repairs: the original string survives verbatim in the
    result, and what is added is a constant that is true of every DOI of that
    kind. Nothing here infers which paper was meant.

    Two rules that did infer were deliberately removed. One stripped junk
    preceding an otherwise intact DOI, which turned `110.3389/fpls.2022.858711`
    into `10.3389/...` by deciding the leading digit was a typo. The other read
    a bare `btac457` as an Oxford Bioinformatics article id and supplied the
    journal prefix. Both resolved, and by title both were in fact the right
    paper -- but a rule that guesses an identifier can resolve to a real and
    wrong paper, and a citation pointing at the wrong work is a worse outcome
    than a missing one. Two records lose a reference as a result:
    bioconductor-pengls and bioconductor-ctsv.
    """
    out = []

    # arXiv registers a DOI for every paper under this prefix, and carries the
    # identifier over unchanged.
    arxiv = re.match(r"(?i)^(?:arxiv:|arxiv\.org/abs/)(\d{4}\.\d{4,5}(?:v\d+)?)$", text)
    if arxiv:
        out.append(f"10.48550/arXiv.{arxiv.group(1)}")

    # The "10." prefix is common to every DOI there is, so restoring it infers
    # nothing about this one.
    if re.match(r"^\d{4,9}/", text):
        out.append(f"10.{text}")

    return [c for c in dict.fromkeys(out) if DOI.match(c)]


def exists(doi: str) -> bool:
    """True when the DOI registry has a record for this DOI."""
    if doi in _verified:
        return _verified[doi]
    try:
        response = requests.get(
            HANDLE_API + quote(doi, safe="/:"),
            headers={"Accept": "application/json"},
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        # Not cached: unverified is unusable, but a blip should not rule the
        # candidate out for the rest of the run.
        logger.warning("could not reach the DOI registry for %s (%s)", doi, exc)
        return False
    if response.status_code == 404:
        _verified[doi] = False
        return False
    try:
        found = response.json().get("responseCode") == 1
    except ValueError:
        logger.warning("unreadable registry response for %s", doi)
        return False
    _verified[doi] = found
    return found


def resolve(raw: str) -> str | None:
    """Return a DOI bio.tools will accept, or None if there is not one."""
    text = normalise(raw)
    if DOI.match(text):
        return text
    for candidate in candidates(text):
        if exists(candidate):
            logger.info(
                "repaired DOI %r as %r (confirmed by the registry)", raw, candidate
            )
            return candidate
    logger.warning("discarding unusable DOI %r (normalised to %r)", raw, text)
    return None
