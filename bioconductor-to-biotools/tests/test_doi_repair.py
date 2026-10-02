"""DOI repair, driven by the strings bio.tools actually rejected.

    cd bioconductor-to-biotools && python3 -m unittest discover -s tests

Offline: the registry is stubbed. The real strings below are from the
2026-09-30 import log, with the package each came from.
"""

import logging
import unittest
from unittest import mock

from bc2bt import doi_repair
from bc2bt.converter import extract_publications
from bc2bt.doi_repair import DOI, candidates, normalise, resolve

# (package, string bio.tools rejected, what it should become)
SYNTACTIC = [
    ("champ", "10.1016%5C%252Fj.ymeth.2014.10.036", "10.1016/j.ymeth.2014.10.036"),
    ("dss", "%2010.1093/nar/gkv715", "10.1093/nar/gkv715"),
    (
        "generxcluster",
        "%7B10.1093/bioinformatics/btu035%7D",
        "10.1093/bioinformatics/btu035",
    ),
    (
        "generxcluster",
        "10.1093/bioinformatics/btu035%7D",
        "10.1093/bioinformatics/btu035",
    ),
    ("messina", "%7B10.1371/journal.pone.0005337%7D", "10.1371/journal.pone.0005337"),
    ("messina", "10.1371/journal.pone.0005337%7D", "10.1371/journal.pone.0005337"),
    ("mirlab", "10.1371%2Fjournal.pone.0145386", "10.1371/journal.pone.0145386"),
    (
        "shortread",
        "http://dx.doi.org10.1093/bioinformatics/btp450",
        "10.1093/bioinformatics/btp450",
    ),
    ("bioconductor-dmcfb", "%2010.1111/biom.12965", "10.1111/biom.12965"),
    (
        "bioconductor-dominosignal",
        "10.1038%2Fs41551-021-00770-5",
        "10.1038/s41551-021-00770-5",
    ),
]

# These need a repair, so each must be confirmed by the registry first.
REPAIRABLE = [
    ("ihw", "arXiv%3A1701.05179", "10.48550/arXiv.1701.05179"),
    (
        "bioconductor-nucler",
        "1093/bioinformatics/btr345",
        "10.1093/bioinformatics/btr345",
    ),
    ("bioconductor-pengls", "110.3389/fpls.2022.858711", "10.3389/fpls.2022.858711"),
    ("bioconductor-ctsv", "btac457", "10.1093/bioinformatics/btac457"),
]

UNUSABLE = [("bioconductor-clustergvis", "1111"), ("bioconductor-scqtltools", "NULL")]


class Normalise(unittest.TestCase):
    """Decoding and unwrapping only: it must not invent a DOI."""

    def setUp(self):
        # Any network call here would be a bug in the code under test.
        patcher = mock.patch.object(
            doi_repair, "requests", side_effect=AssertionError("no network")
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_every_syntactic_case_comes_out_valid(self):
        for pkg, raw, want in SYNTACTIC:
            with self.subTest(package=pkg, raw=raw):
                got = normalise(raw)
                self.assertEqual(got, want)
                self.assertRegex(got, DOI)

    def test_a_clean_doi_is_left_alone(self):
        self.assertEqual(normalise("10.1093/nar/gkv715"), "10.1093/nar/gkv715")

    def test_it_is_idempotent(self):
        for _, raw, want in SYNTACTIC:
            with self.subTest(raw=raw):
                self.assertEqual(normalise(normalise(raw)), want)

    def test_it_never_fabricates_a_prefix(self):
        """Normalisation must leave a broken DOI broken; repairs get verified."""
        for raw in ("1111", "NULL", "btac457", "1093/bioinformatics/btr345"):
            with self.subTest(raw=raw):
                self.assertNotRegex(normalise(raw), DOI)

    def test_empty_input_is_handled(self):
        for raw in ("", None, "   "):
            self.assertEqual(normalise(raw), "")


class Candidates(unittest.TestCase):
    """Repairs are proposals, not conclusions."""

    def test_each_repairable_case_proposes_the_right_doi(self):
        for pkg, raw, want in REPAIRABLE:
            with self.subTest(package=pkg, raw=raw):
                self.assertIn(want, candidates(normalise(raw)))

    def test_nothing_is_proposed_for_junk(self):
        for _, raw in UNUSABLE:
            with self.subTest(raw=raw):
                self.assertEqual(candidates(normalise(raw)), [])

    def test_every_proposal_is_syntactically_a_doi(self):
        for _, raw, _ in REPAIRABLE + [(p, r, None) for p, r in UNUSABLE]:
            for candidate in candidates(normalise(raw)):
                with self.subTest(candidate=candidate):
                    self.assertRegex(candidate, DOI)


class Resolve(unittest.TestCase):
    def setUp(self):
        doi_repair._verified.clear()
        self.addCleanup(doi_repair._verified.clear)

    def stub_registry(self, known=(), fail=False):
        def get(url, **kwargs):
            if fail:
                raise doi_repair.requests.RequestException("down")
            doi = url.split("/api/handles/", 1)[1]
            resp = mock.MagicMock()
            resp.status_code = 200 if doi in known else 404
            resp.json.return_value = {"responseCode": 1 if doi in known else 100}
            return resp

        p = mock.patch.object(doi_repair.requests, "get", side_effect=get)
        self.mock = p.start()
        self.addCleanup(p.stop)

    def test_a_syntactic_fix_needs_no_registry_call(self):
        self.stub_registry()
        for pkg, raw, want in SYNTACTIC:
            with self.subTest(package=pkg):
                self.assertEqual(resolve(raw), want)
        self.assertEqual(self.mock.call_count, 0, "no lookup should be needed")

    def test_a_verified_repair_is_accepted(self):
        self.stub_registry(known={want for _, _, want in REPAIRABLE})
        for pkg, raw, want in REPAIRABLE:
            with (
                self.subTest(package=pkg),
                self.assertLogs("bc2bt.doi_repair", level=logging.INFO),
            ):
                self.assertEqual(resolve(raw), want)

    def test_an_unverified_repair_is_refused(self):
        """A DOI the registry does not know is not a DOI we may attach."""
        self.stub_registry(known=set())
        for pkg, raw, _ in REPAIRABLE:
            with (
                self.subTest(package=pkg),
                self.assertLogs("bc2bt.doi_repair", level=logging.WARNING),
            ):
                self.assertIsNone(resolve(raw))

    def test_an_unreachable_registry_refuses_rather_than_guesses(self):
        self.stub_registry(fail=True)
        with self.assertLogs("bc2bt.doi_repair", level=logging.WARNING):
            self.assertIsNone(resolve("btac457"))

    def test_a_registry_failure_is_not_cached(self):
        """A blip must not condemn the candidate for the rest of the run."""
        self.stub_registry(fail=True)
        resolve("btac457")
        self.assertEqual(doi_repair._verified, {})

    def test_junk_is_discarded(self):
        self.stub_registry()
        for pkg, raw in UNUSABLE:
            with (
                self.subTest(package=pkg),
                self.assertLogs("bc2bt.doi_repair", level=logging.WARNING),
            ):
                self.assertIsNone(resolve(raw))

    def test_each_candidate_is_looked_up_once(self):
        self.stub_registry(known={"10.1093/bioinformatics/btac457"})
        for _ in range(4):
            resolve("btac457")
        self.assertEqual(self.mock.call_count, 1)


class InCitationPages(unittest.TestCase):
    """What extract_publications makes of a real citation page."""

    def setUp(self):
        p = mock.patch.object(doi_repair, "exists", return_value=False)
        self.exists = p.start()
        self.addCleanup(p.stop)

    @staticmethod
    def page(*hrefs):
        return "<html>" + "".join(f"<a href='{h}'>p</a>" for h in hrefs) + "</html>"

    def test_each_wrapping_resolves_on_its_own(self):
        """Checked separately: asserting only the deduped list let a dropped
        href hide behind a good one, which is how the brace-before-prefix bug
        survived its first test."""
        for href in (
            "https://doi.org/%7B10.1093/bioinformatics/btu035%7D",
            "https://doi.org/10.1093/bioinformatics/btu035%7D",
            "%7Bhttps://doi.org/10.1093/bioinformatics/btu035%7D",
            "https://doi.org/10.1093/bioinformatics/btu035",
        ):
            with self.subTest(href=href):
                self.assertEqual(
                    extract_publications(self.page(href)),
                    [{"doi": "10.1093/bioinformatics/btu035"}],
                )

    def test_the_same_doi_braced_and_bare_yields_one_entry(self):
        """generxcluster and messina each list theirs twice."""
        got = extract_publications(
            self.page(
                "https://doi.org/%7B10.1093/bioinformatics/btu035%7D",
                "https://doi.org/10.1093/bioinformatics/btu035%7D",
            )
        )
        self.assertEqual(got, [{"doi": "10.1093/bioinformatics/btu035"}])

    def test_a_missing_slash_in_the_prefix_still_resolves(self):
        got = extract_publications(
            self.page("http://dx.doi.org10.1093/bioinformatics/btp450")
        )
        self.assertEqual(got, [{"doi": "10.1093/bioinformatics/btp450"}])

    def test_an_unusable_doi_is_left_out_entirely(self):
        with self.assertLogs("bc2bt.doi_repair", level=logging.WARNING):
            got = extract_publications(self.page("https://doi.org/NULL"))
        self.assertEqual(got, [])

    def test_non_doi_links_are_ignored_without_a_lookup(self):
        self.assertEqual(extract_publications(self.page("/help", "https://x.org")), [])
        self.assertEqual(self.exists.call_count, 0)

    def test_good_and_bad_on_one_page(self):
        with self.assertLogs("bc2bt.doi_repair", level=logging.WARNING):
            got = extract_publications(
                self.page("https://doi.org/1111", "https://doi.org/10.1093/nar/gkv715")
            )
        self.assertEqual(got, [{"doi": "10.1093/nar/gkv715"}])


if __name__ == "__main__":
    unittest.main(verbosity=2)
