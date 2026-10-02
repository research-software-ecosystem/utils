"""Emit only what bio.tools will accept.

    cd bioconductor-to-biotools && python3 -m unittest discover -s tests

Each limit asserted here is one bio.tools enforces on write, and each case is
drawn from a record it actually rejected in the 2026-09-30 import.
"""

import json
import logging
import tempfile
import unittest
from pathlib import Path
from typing import ClassVar

from bc2bt.converter import (
    MAX_CREDIT_NAME,
    MAX_DESCRIPTION,
    MIN_DESCRIPTION,
    convert_package,
    fit_description,
    process_authors,
)
from bc2bt.updater import Updater


class FitDescription(unittest.TestCase):
    """max_length=1000, min_length=10, required=True."""

    def test_a_short_description_is_untouched(self):
        self.assertEqual(fit_description("A tool for things."), "A tool for things.")

    def test_whitespace_is_normalised(self):
        self.assertEqual(fit_description("a  b\n\tc" * 2), "a b ca b c")

    def test_it_cuts_at_a_sentence_boundary(self):
        # Must exceed the limit, or nothing is truncated: 21 chars x 60.
        text = ("Alpha sentence here. " * 60) + "Trailing clause without a stop"
        self.assertGreater(len(text), MAX_DESCRIPTION)
        out = fit_description(text)
        self.assertLessEqual(len(out), MAX_DESCRIPTION)
        self.assertTrue(out.endswith("."), out[-40:])
        self.assertNotIn("Trailing clause", out)

    def test_a_single_long_sentence_falls_back_to_a_word_boundary(self):
        out = fit_description("word " * 400)
        self.assertLessEqual(len(out), MAX_DESCRIPTION)
        self.assertTrue(out.endswith("…"), "a severed clause should say so")
        self.assertFalse(out.rstrip("…").endswith(" "))

    def test_the_title_covers_an_empty_description(self):
        """One package ships an empty Description, and the field is required."""
        self.assertEqual(
            fit_description("", "A useful package title"), "A useful package title"
        )

    def test_nothing_usable_yields_nothing(self):
        """Better an absent field than a blank one; neither can be registered."""
        self.assertEqual(fit_description("", ""), "")
        self.assertEqual(fit_description("short", "tiny"), "")

    def test_it_is_idempotent(self):
        once = fit_description("Sentence one. " * 200)
        self.assertEqual(fit_description(once), once)

    def test_the_result_always_satisfies_both_bounds(self):
        for raw in ("x" * 5000, "Hi. " * 500, "A" * 999, "", "a b c d e f g h"):
            out = fit_description(raw, "A perfectly good fallback title")
            with self.subTest(raw=raw[:20]):
                self.assertTrue(
                    out == "" or MIN_DESCRIPTION <= len(out) <= MAX_DESCRIPTION
                )


class Credit(unittest.TestCase):
    """credit.name is capped at 100 characters."""

    CHROMATOGRAMS = (
        "Johannes Rainer [aut] (ORCID: <https://orcid.org/0000-0002-6977-7147>), "
        "Philippine Louail [aut, cre] (ORCID: <https://orcid.org/0009-0007-5429-6846>, "
        "fnd: European Union HORIZON-MSCA-2021 project Grant No. 101073062: HUMAN)"
    )
    # DESCRIPTION Author with no commas at all: unsplittable without guessing.
    CRISPRSEEK = (
        "Lihua Julie Zhu Paul Scemama Benjamin R. Holmes Herve Pages Kai Hu Hui Mao "
        "Michael Lawrence Isana Veksler-Lublinsky Victor Ambros Neil Aronin"
    )

    def test_a_comma_inside_the_orcid_parenthetical_is_not_a_separator(self):
        """Splitting there turned a funding note into a person."""
        names = [c["name"] for c in process_authors(self.CHROMATOGRAMS)]
        self.assertEqual(names, ["Johannes Rainer", "Philippine Louail"])
        self.assertFalse([n for n in names if n.startswith("fnd")])

    def test_an_unparseable_credit_is_dropped_not_truncated(self):
        """Truncating to 100 would store a fabricated person."""
        with self.assertLogs("bc2bt.converter", level=logging.WARNING):
            credits = process_authors(self.CRISPRSEEK)
        self.assertEqual(credits, [])

    def test_no_credit_ever_exceeds_the_limit(self):
        for raw in (
            self.CHROMATOGRAMS,
            self.CRISPRSEEK,
            "A. Person [aut], B. Other [cre]",
        ):
            for c in process_authors(raw):
                with self.subTest(name=c["name"][:30]):
                    self.assertLessEqual(len(c["name"]), MAX_CREDIT_NAME)

    def test_ordinary_authors_still_parse(self):
        got = process_authors("Jane Doe [aut, cre], John Roe [ctb]")
        self.assertEqual([c["name"] for c in got], ["Jane Doe", "John Roe"])
        self.assertIn("Maintainer", got[0]["typeRole"])


class Publication(unittest.TestCase):
    """required=False, allow_empty=False: absent is fine, [] is not."""

    BIOC: ClassVar[dict] = {
        "Package": "demo",
        "Description": "A package for demonstrating things.",
        "Version": "1.0.0",
        "Author": "Jane Doe [aut]",
        "License": "MIT",
    }

    def test_a_citation_page_with_no_doi_leaves_the_field_out(self):
        out = convert_package(
            self.BIOC, citation_html="<html><a href='/x'>no doi</a></html>"
        )
        self.assertNotIn("publication", out, "[] is rejected; omission is what we mean")

    def test_a_long_description_is_fitted_by_the_converter(self):
        """fit_description has to be wired in, not merely present.

        Testing the helper alone passed happily with the call removed from
        convert_package, which is the only place it matters.
        """
        bioc = dict(self.BIOC, Description="Sentence here. " * 120)
        out = convert_package(bioc)
        self.assertLessEqual(len(out["description"]), MAX_DESCRIPTION)
        self.assertGreaterEqual(len(out["description"]), MIN_DESCRIPTION)

    def test_an_empty_description_falls_back_to_the_title(self):
        bioc = dict(self.BIOC, Description="", Title="A serviceable title here")
        self.assertEqual(
            convert_package(bioc)["description"], "A serviceable title here"
        )

    def test_credits_are_filtered_by_the_converter_too(self):
        bioc = dict(self.BIOC, Author=Credit.CRISPRSEEK)
        with self.assertLogs("bc2bt.converter", level=logging.WARNING):
            out = convert_package(bioc)
        self.assertEqual(out["credit"], [])

    def test_a_citation_page_with_a_doi_still_yields_one(self):
        html = "<html><a href='https://doi.org/10.1093/nar/gkv715'>paper</a></html>"
        out = convert_package(self.BIOC, citation_html=html)
        self.assertEqual(out["publication"], [{"doi": "10.1093/nar/gkv715"}])


class UpdatePolicy(unittest.TestCase):
    """What an update may and may not overwrite."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def merge(self, existing, incoming):
        ex = self.dir / "existing.biotools.json"
        inc = self.dir / "incoming.biotools.json"
        ex.write_text(json.dumps(existing))
        inc.write_text(json.dumps(incoming))
        Updater(str(self.dir), backup=False, copy_source=False).update_entry(
            str(ex), str(inc)
        )
        return json.loads(ex.read_text())

    def test_an_existing_description_is_kept(self):
        """Somebody's considered wording outranks a package abstract."""
        out = self.merge(
            {"biotoolsID": "x", "description": "The curated description."},
            {"biotoolsID": "x", "description": "Generated from DESCRIPTION."},
        )
        self.assertEqual(out["description"], "The curated description.")

    def test_a_missing_description_is_filled(self):
        for existing in ({"biotoolsID": "x"}, {"biotoolsID": "x", "description": ""}):
            with self.subTest(existing=existing):
                out = self.merge(
                    dict(existing),
                    {"biotoolsID": "x", "description": "From Bioconductor."},
                )
                self.assertEqual(out["description"], "From Bioconductor.")

    def test_publications_are_not_replaced_by_nothing(self):
        """The loop used to assign unconditionally, losing the references."""
        out = self.merge(
            {"biotoolsID": "x", "publication": [{"doi": "10.1/abc"}]},
            {"biotoolsID": "x", "publication": []},
        )
        self.assertEqual(out["publication"], [{"doi": "10.1/abc"}])

    def test_publications_are_updated_when_there_is_something_to_say(self):
        out = self.merge(
            {"biotoolsID": "x", "publication": [{"doi": "10.1/old"}]},
            {"biotoolsID": "x", "publication": [{"doi": "10.1/new"}]},
        )
        self.assertEqual(out["publication"], [{"doi": "10.1/new"}])

    def test_an_empty_list_already_stored_is_cleaned_up(self):
        """117 records carry "publication": [] today.

        The converter no longer emits it, but without this they would keep it
        for ever: the merge only touches fields the incoming data has.
        """
        out = self.merge(
            {"biotoolsID": "x", "publication": [], "topic": []}, {"biotoolsID": "x"}
        )
        self.assertNotIn("publication", out)
        self.assertNotIn("topic", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
