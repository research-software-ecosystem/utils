"""Regression tests for the Bioconductor -> bio.tools identity matching.

Each test corresponds to something that actually went wrong in the commons.
"""

import json

from bc2bt.mapper import (
    PLACEHOLDER_DOI,
    build_identity_index,
    find_matches_optimized,
    identity_doi,
)

METHODS = ["name_homepage", "doi"]


def rec(name, homepage, dois):
    return {
        "name": name,
        "homepage": homepage,
        "publication": [{"doi": d} for d in dois],
    }


def run(data1, data2, methods=METHODS):
    v1, _ = build_identity_index(data1, methods)
    v2, i2 = build_identity_index(data2, methods)
    return find_matches_optimized(v1, v2, i2, methods, data1, data2)


def test_placeholder_doi_is_not_an_identity():
    """10.18129/B9.bioc.<pkg> identifies a package, not a work."""
    assert PLACEHOLDER_DOI.match("10.18129/B9.bioc.a4")
    assert identity_doi(rec("a4", "h", ["10.18129/B9.bioc.a4"])) is None
    assert identity_doi(rec("a4", "h", ["10.1038/nmeth.3252"])) == frozenset(
        {"10.1038/nmeth.3252"}
    )


def test_shared_doi_alone_does_not_match_different_tools():
    """ARRmNormalization must not absorb sesame because they cite one paper.

    Two Bioconductor methylation packages routinely share a methods citation.
    Before the fix, one shared DOI was enough to declare them the same software
    and merge one into the other.
    """
    shared = "10.1093/nar/gkt090"
    existing = {"arrm.json": rec("ARRmNormalization", "https://x/arrm", [shared])}
    converted = {"sesame.json": rec("sesame", "https://y/sesame", [shared])}
    *_, matched1, matched2, conflicts = run(existing, converted)
    assert matched1 == set(), "must not match on a shared reference alone"
    assert matched2 == set()
    assert any("names differ" in c["reason"] for c in conflicts)


def test_shared_doi_with_matching_name_does_match():
    """The legitimate case still works: same name plus a shared paper."""
    shared = "10.1074/mcp.RA119.001777"
    existing = {"poly.json": rec("PolySTest", "https://own.site/PolySTest", [shared])}
    converted = {"polyc.json": rec("polystest", "https://bioc/PolySTest", [shared])}
    *_, matched1, matched2, conflicts = run(existing, converted)
    assert matched1 == {"poly.json"}
    assert matched2 == {"polyc.json"}
    assert conflicts == []


def test_ambiguous_candidates_are_refused_not_guessed():
    """Several verified candidates must produce a conflict, never a silent pick."""
    shared = "10.1038/nmeth.3252"
    existing = {"e.json": rec("thing", "https://h/thing", [shared])}
    converted = {
        "c1.json": rec("thing", "https://bioc/thing1", [shared]),
        "c2.json": rec("thing", "https://bioc/thing2", [shared]),
    }
    *_, matched1, matched2, conflicts = run(existing, converted)
    assert matched1 == set()
    assert matched2 == set()
    assert any(c["reason"] == "multiple candidates verified" for c in conflicts)


def test_result_is_independent_of_iteration_order():
    """The winner used to depend on set iteration order, i.e. on PYTHONHASHSEED."""
    shared = "10.1038/nmeth.3252"
    existing = {"e.json": rec("alpha", "https://h/alpha", [shared])}
    converted = {
        f"c{i}.json": rec("alpha", f"https://bioc/alpha{i}", [shared]) for i in range(6)
    }
    runs = []
    for _ in range(5):
        *_, m1, _m2, conflicts = run(dict(existing), dict(converted))
        runs.append((sorted(m1), sorted(c["reason"] for c in conflicts)))
    assert len(set(map(json.dumps, runs))) == 1, f"unstable across runs: {runs}"
