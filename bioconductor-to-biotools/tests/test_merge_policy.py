"""Tests for the fields where the curated bio.tools value must survive."""

from bc2bt.updater import keep_existing_text, merge_credit, merge_homepage


def test_existing_contact_email_is_never_dropped():
    """Bioconductor's Author string carries no e-mail, so assigning it lost one."""
    existing = [
        {
            "name": "Tobias Verbeke",
            "email": "tobias@example.org",
            "typeEntity": "Person",
            "typeRole": ["Primary contact"],
        }
    ]
    incoming = [
        {"name": "Tobias Verbeke", "typeEntity": "Person", "typeRole": ["Developer"]}
    ]
    merged = merge_credit(existing, incoming)
    assert len(merged) == 1
    assert merged[0]["email"] == "tobias@example.org"
    assert merged[0]["typeRole"] == ["Developer", "Primary contact"]


def test_new_people_are_added_not_substituted():
    existing = [{"name": "Tobias Verbeke", "email": "tobias@example.org"}]
    incoming = [{"name": "Laure Cougnaud", "typeRole": ["Maintainer"]}]
    names = {c["name"] for c in merge_credit(existing, incoming)}
    assert names == {"Tobias Verbeke", "Laure Cougnaud"}


def test_a_new_email_for_a_known_person_is_kept_too():
    """A credit entry holds one e-mail, so a second address needs its own entry."""
    existing = [{"name": "Jean-Philippe Fortin", "email": "old@example.org"}]
    incoming = [{"name": "Jean-Philippe Fortin", "email": "jfortin@jhsph.edu"}]
    emails = {c.get("email") for c in merge_credit(existing, incoming)}
    assert emails == {"old@example.org", "jfortin@jhsph.edu"}


def test_names_differing_only_by_accent_are_one_person():
    existing = [{"name": "Veit Schwämmle", "email": "veits@bmb.sdu.dk"}]
    incoming = [{"name": "Veit Schwammle", "typeRole": ["Maintainer"]}]
    merged = merge_credit(existing, incoming)
    assert len(merged) == 1
    assert merged[0]["email"] == "veits@bmb.sdu.dk"


def test_curated_description_survives():
    curated = "Robust statistical testing of quantitative proteomics data."
    assert keep_existing_text(curated, "The complexity of high-throughput …") == curated


def test_description_is_taken_when_there_is_none():
    assert keep_existing_text(None, "From Bioconductor") == "From Bioconductor"
    assert keep_existing_text("", "From Bioconductor") == "From Bioconductor"


def test_project_homepage_is_not_replaced_by_the_bioconductor_page():
    """PolySTest and VSClust are web applications as well as packages."""
    own = "http://computproteomics.bmb.sdu.dk/app_direct/PolySTest"
    assert merge_homepage(own, "https://bioconductor.org/packages/PolySTest") == own


def test_a_bioconductor_homepage_is_refreshed():
    stale = "http://bioconductor.org/packages/release/bioc/html/a4.html"
    fresh = "https://bioconductor.org/packages/a4"
    assert merge_homepage(stale, fresh) == fresh


def test_homepage_is_taken_when_there_is_none():
    fresh = "https://bioconductor.org/packages/a4"
    assert merge_homepage(None, fresh) == fresh


def test_a_name_listed_twice_upstream_collapses_to_one_person():
    """ggmanh's Author string is "John Lee [aut, cre], John Lee [aut] (AbbVie), …".

    Written out verbatim that made two entries, and merging them on the next
    run changed the file, so the converter was not idempotent.
    """
    from bc2bt.updater import dedupe_credit

    incoming = [
        {
            "name": "John Lee",
            "typeEntity": "Person",
            "typeRole": ["Developer", "Maintainer"],
        },
        {"name": "John Lee", "typeEntity": "Person", "typeRole": ["Developer"]},
        {"name": "Xiuwen Zheng", "typeEntity": "Person", "typeRole": ["Contributor"]},
    ]
    once = dedupe_credit(incoming)
    assert [c["name"] for c in once] == ["John Lee", "Xiuwen Zheng"]
    assert once[0]["typeRole"] == ["Developer", "Maintainer"]
    # and merging it again must not change anything
    assert merge_credit(once, incoming) == once


# --------------------------------------------------------------- publications
def test_placeholder_never_displaces_a_real_paper():
    """The a4 family lost 10.1038/nmeth.3252 to 10.18129/B9.bioc.a4."""
    from bc2bt.updater import merge_publications

    existing = [
        {
            "doi": "10.1038/nmeth.3252",
            "metadata": {"title": "Orchestrating high-throughput …"},
        }
    ]
    incoming = [{"doi": "10.18129/B9.bioc.a4"}]
    merged = merge_publications(existing, incoming)
    assert [p["doi"] for p in merged] == ["10.1038/nmeth.3252"]
    assert merged[0]["metadata"], "citation metadata must survive"


def test_a_second_real_paper_is_added():
    from bc2bt.updater import merge_publications

    existing = [{"doi": "10.1074/mcp.RA119.001777", "metadata": {"citationCount": 26}}]
    incoming = [{"doi": "10.1093/bioinformatics/bty224"}]
    dois = [p["doi"] for p in merge_publications(existing, incoming)]
    assert dois == ["10.1074/mcp.RA119.001777", "10.1093/bioinformatics/bty224"]


def test_placeholder_is_kept_when_it_is_all_there_is():
    from bc2bt.updater import merge_publications

    merged = merge_publications([], [{"doi": "10.18129/B9.bioc.vsclust"}])
    assert [p["doi"] for p in merged] == ["10.18129/B9.bioc.vsclust"]


def test_publication_merge_is_order_independent_and_idempotent():
    from bc2bt.updater import merge_publications

    real = [{"doi": "10.1038/nmeth.3252"}]
    ph = [{"doi": "10.18129/B9.bioc.a4"}]
    once = merge_publications(real, ph)
    assert merge_publications(once, ph) == once
    assert merge_publications(once, real) == once


# ----------------------------------------------------------------------- urls
def test_third_party_download_url_is_not_dropped():
    from bc2bt.updater import merge_urls

    existing = [{"type": "Source code", "url": "https://github.com/Sarah145/CCPlotR"}]
    incoming = [
        {"type": "Source code", "url": "https://bioconductor.org/packages/CCPlotR"}
    ]
    urls = [e["url"] for e in merge_urls(existing, incoming)]
    assert urls == [
        "https://github.com/Sarah145/CCPlotR",
        "https://bioconductor.org/packages/CCPlotR",
    ]


def test_invalid_urls_are_the_only_thing_dropped():
    from bc2bt.updater import is_valid_url, merge_urls

    assert not is_valid_url("http://bioconductor/packages/a4_1.22.0.tar.gz")
    assert not is_valid_url("https://github.com/HelBor/wpm, https://bioconductor.org/x")
    assert not is_valid_url("not a url")
    assert is_valid_url("https://bioconductor.org/packages/a4")

    existing = [
        {"type": "Source code", "url": "http://bioconductor/packages/a4_1.22.0.tar.gz"}
    ]
    incoming = [
        {
            "type": "Source code",
            "url": "https://bioconductor.org/packages/a4_1.60.0.tar.gz",
        }
    ]
    urls = [e["url"] for e in merge_urls(existing, incoming)]
    assert urls == ["https://bioconductor.org/packages/a4_1.60.0.tar.gz"]


def test_versioned_tarballs_accumulate_by_design():
    """Documents the cost of "never drop a valid URL".

    Both release tarballs are valid, so both are kept. Across releases this
    grows, and superseding a URL that differs only by version would mean
    dropping a valid one -- a policy decision, not a bug to fix quietly.
    """
    from bc2bt.updater import merge_urls

    existing = [
        {
            "type": "Source code",
            "url": "https://bioconductor.org/packages/a4_1.59.0.tar.gz",
        }
    ]
    incoming = [
        {
            "type": "Source code",
            "url": "https://bioconductor.org/packages/a4_1.60.0.tar.gz",
        }
    ]
    assert len(merge_urls(existing, incoming)) == 2


def test_a_created_entry_is_already_normalised():
    """create_entry wrote the converted record verbatim, so the next update
    changed it and the converter was not idempotent for new entries.

    bioconductor-isanalytics is the real case: the converter emits
    10.1093/bib/bbac551 twice alongside the Bioconductor placeholder, plus a
    download list needing validation.
    """
    from bc2bt.updater import merge_publications, merge_urls, normalise_record

    data = {
        "biotoolsID": "bioconductor-isanalytics",
        "publication": [
            {"doi": "10.18129/B9.bioc.ISAnalytics"},
            {"doi": "10.1093/bib/bbac551"},
            {"doi": "10.1093/bib/bbac551"},
        ],
        "download": [
            {"type": "Source code", "url": "https://calabrialab.github.io/ISAnalytics"},
            {"type": "Source code", "url": "http://bioconductor/packages/x_1.0.tar.gz"},
        ],
        "credit": [{"name": "A B"}, {"name": "A B"}],
    }
    once = normalise_record(dict(data))
    assert [p["doi"] for p in once["publication"]] == ["10.1093/bib/bbac551"]
    assert [d["url"] for d in once["download"]] == [
        "https://calabrialab.github.io/ISAnalytics"
    ]
    assert len(once["credit"]) == 1

    # and a subsequent merge against the same converted data changes nothing
    assert (
        merge_publications(once["publication"], data["publication"])
        == once["publication"]
    )
    assert merge_urls(once["download"], data["download"]) == once["download"]
