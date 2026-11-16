"""Unit tests for the shared value checkers.

python3 -m unittest discover -s common
"""

import unittest

import validation_checks as vc


class Orcid(unittest.TestCase):
    def test_valid_bare_and_url_forms(self):
        self.assertTrue(vc.is_orcid("0000-0002-1825-0097"))
        self.assertTrue(vc.is_orcid("https://orcid.org/0000-0002-1825-0097"))

    def test_checksum_x(self):
        self.assertTrue(vc.is_orcid("0000-0002-9079-593X"))

    def test_bad_checksum(self):
        self.assertFalse(vc.is_orcid("0000-0002-1825-0098"))

    def test_bad_shape(self):
        self.assertFalse(vc.is_orcid("0000-0002-1825"))
        self.assertFalse(vc.is_orcid("0000_0002_1825_0097"))


class Doi(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(vc.is_doi("10.1093/bioinformatics/btp352"))
        self.assertTrue(vc.is_doi("doi:10.1093/bioinformatics/btp352"))
        self.assertTrue(
            vc.is_doi("https://doi.org/10.48546/workflowhub.workflow.1297.1")
        )
        self.assertTrue(vc.is_doi("10.1093/BIOINFORMATICS/BTZ786"))

    def test_invalid(self):
        self.assertFalse(vc.is_doi("11.1093/bioinformatics"))
        self.assertFalse(vc.is_doi("10.1093/bio informatics"))
        self.assertTrue(
            vc.is_doi("10.1002/(sici)1097-0134(199707)28:3<405::aid-prot10>3.0.co;2-l")
        )
        self.assertFalse(vc.is_doi("10.1093"))


class Url(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(vc.is_url("https://bio.tools"))
        self.assertTrue(vc.is_url("ftp://ftp.example.org/pub"))

    def test_invalid(self):
        self.assertFalse(vc.is_url("None"))
        self.assertFalse(vc.is_url("example.org/no-scheme"))
        self.assertFalse(vc.is_url("https://exa mple.org"))
        self.assertFalse(vc.is_url("mailto:a@b.cc"))


class Email(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(vc.is_email("rd@sanger.ac.uk"))
        self.assertTrue(vc.is_email("first.last+tag@example-host.org"))

    def test_invalid(self):
        self.assertFalse(vc.is_email("not-an-email"))
        self.assertFalse(vc.is_email("a@nodot"))
        self.assertFalse(vc.is_email("a b@example.org"))
        self.assertFalse(vc.is_email("a..b@example.org"))


class Ids(unittest.TestCase):
    def test_pmid(self):
        self.assertTrue(vc.is_pmid("19505943"))
        self.assertFalse(vc.is_pmid("0195"))
        self.assertFalse(vc.is_pmid("PMC123"))

    def test_pmcid(self):
        self.assertTrue(vc.is_pmcid("PMC2723002"))
        self.assertFalse(vc.is_pmcid("2723002"))

    def test_edam(self):
        self.assertTrue(vc.is_edam_uri("http://edamontology.org/topic_2885"))
        self.assertFalse(vc.is_edam_uri("http://edamontology.org/thing_2885"))
        self.assertFalse(vc.is_edam_uri("edam:topic_2885"))

    def test_biotools(self):
        self.assertTrue(vc.is_biotools_id("samtools"))
        self.assertTrue(vc.is_biotools_curie("biotools:samtools"))
        self.assertFalse(vc.is_biotools_id("sam tools"))
        self.assertFalse(vc.is_biotools_curie("samtools"))
        self.assertFalse(vc.is_biotools_curie("biotools:"))

    def test_curie(self):
        self.assertTrue(vc.is_curie("biotools:samtools"))
        self.assertTrue(vc.is_curie("doi:10.1093/bioinformatics/btp352"))
        self.assertTrue(vc.is_curie("PMID:19505943"))
        self.assertTrue(vc.is_curie("usegalaxy-eu:10x_bamtofastq"))
        self.assertFalse(vc.is_curie("unknownprefix:x"))
        self.assertFalse(vc.is_curie("doi:not-a-doi"))
        self.assertFalse(vc.is_curie("no-colon"))

    def test_scicrunch(self):
        self.assertTrue(vc.is_scicrunch_id("SCR_010910"))
        self.assertFalse(vc.is_scicrunch_id("SCR010910"))


class DatesAndSums(unittest.TestCase):
    def test_dates(self):
        self.assertTrue(vc.is_iso_date("2026-04-28"))
        self.assertFalse(vc.is_iso_date("2026-13-01"))
        self.assertFalse(vc.is_iso_date("28/04/2026"))
        self.assertTrue(vc.is_iso_datetime("2020-12-01T14:56:23Z"))
        self.assertTrue(vc.is_iso_datetime("2026-11-12T14:22:05.920904Z"))
        self.assertTrue(vc.is_iso_datetime("2023-04-28T14:32:28+00:00"))
        self.assertFalse(vc.is_iso_datetime("2020-12-01"))

    def test_sums(self):
        self.assertTrue(vc.is_md5("7b904940a9f5331affa84d4b72dedb30"))
        self.assertFalse(vc.is_md5("7b904940a9f5331affa84d4b72dedb3"))
        self.assertTrue(
            vc.is_sha256(
                "bc20ae2701a0b2e323e4e515b7cfa18a0f0cb34a4ff5844b289b2de0154e3d3e"
            )
        )
        self.assertFalse(vc.is_sha256("deadbeef"))


class Versions(unittest.TestCase):
    def test_debian(self):
        self.assertTrue(vc.is_debian_version("0.7.19"))
        self.assertTrue(vc.is_debian_version("2.12.0+ds"))
        self.assertTrue(vc.is_debian_version("0~beta.20100307"))
        self.assertTrue(vc.is_debian_version("1:1.2-3"))
        self.assertFalse(vc.is_debian_version("version one"))

    def test_semverish(self):
        self.assertTrue(vc.is_semverish("1.52.0"))
        self.assertTrue(vc.is_semverish("0.6.22.post1"))
        self.assertFalse(vc.is_semverish("v1.0 beta"))


class Spdx(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(vc.is_spdx_license("MIT"))
        self.assertTrue(vc.is_spdx_license("GPL-3.0-or-later"))
        self.assertTrue(vc.is_spdx_license("LGPL-2.0-or-later"))

    def test_invalid(self):
        self.assertFalse(vc.is_spdx_license("other-open"))
        self.assertFalse(vc.is_spdx_license("GPL (>= 2)"))


class NonStrings(unittest.TestCase):
    def test_non_strings_pass_through(self):
        # type errors are the schema's job; format checkers skip non-strings
        for func in vc.FORMAT_CHECKS.values():
            self.assertTrue(func(None))
            self.assertTrue(func(3))


if __name__ == "__main__":
    unittest.main()
