"""Author strings from DESCRIPTION are free text; these are the shapes that broke."""

from bc2bt.converter import MAX_CREDIT_NAME, process_authors


def names(author_str):
    return [person["name"] for person in process_authors(author_str)]


def test_trailing_affiliation_is_not_part_of_the_last_name():
    # AUCell. Without the cut the second name runs to 128 characters and the
    # registry refuses the record.
    assert names(
        "Sara Aibar, Stein Aerts. Laboratory of Computational Biology. "
        "VIB-KU Leuven Center for Brain & Disease Research. Leuven, Belgium."
    ) == ["Sara Aibar", "Stein Aerts"]


def test_affiliation_cut_keeps_every_person_before_it():
    # RcisTarget lists three people ahead of the same affiliation.
    assert names(
        "Sara Aibar, Gert Hulselmans, Stein Aerts. Laboratory of Computational "
        "Biology.  VIB-KU Leuven Center for Brain & Disease Research. Leuven, Belgium"
    ) == ["Sara Aibar", "Gert Hulselmans", "Stein Aerts"]


def test_people_joined_by_and_are_separate():
    # geNetClassifier: "and" between the last two, then an affiliation.
    assert names(
        "Sara Aibar, Celia Fontanillo and Javier De Las Rivas. Bioinformatics "
        "and Functional Genomics Group. Cancer Research Center "
        "(CiC-IBMCC, CSIC/USAL). Salamanca. Spain."
    ) == ["Sara Aibar", "Celia Fontanillo", "Javier De Las Rivas"]


def test_leading_and_is_not_kept_in_the_name():
    assert names("Ben Bolstad, Crispin Miller, and Rafael Irizarry") == [
        "Ben Bolstad",
        "Crispin Miller",
        "Rafael Irizarry",
    ]


def test_an_initial_is_not_read_as_the_end_of_the_list():
    assert names("B. Ding, R. Gentleman and Vincent Carey") == [
        "B. Ding",
        "R. Gentleman",
        "Vincent Carey",
    ]


def test_unseparated_run_of_names_yields_nothing():
    # CRISPRseek. There is no way to tell where each name ends, so emitting
    # nothing leaves whatever bio.tools already holds in place. Emitting the
    # run would be a 172-character name the registry rejects.
    assert (
        names(
            "Lihua Julie Zhu Paul Scemama Benjamin R. Holmes Hervé Pagès Kai Hu "
            "Hui Mao Michael Lawrence Isana Veksler-Lublinsky Victor Ambros "
            "Neil Aronin Michael Brodsky Devin M Burris"
        )
        == []
    )


def test_a_bracketed_field_is_never_truncated_at_a_full_stop():
    # "Inc. [cph]" looks like an affiliation break, but cutting there would
    # drop a copyright holder. Structured fields are left alone.
    assert names("Aaron Lun [aut, cre], Genentech, Inc. [cph]") == [
        "Aaron Lun",
        "Genentech",
        "Inc.",
    ]


def test_roles_and_orcid_still_parse():
    people = process_authors(
        "Jane Roe [aut, cre] (<https://orcid.org/0000-0002-1825-0097>), John Doe [ctb]"
    )
    assert people[0]["name"] == "Jane Roe"
    assert people[0]["typeEntity"] == "Person"
    assert people[0]["typeRole"] == ["Developer", "Maintainer"]
    assert people[0]["orcid"] == "https://orcid.org/0000-0002-1825-0097"
    assert people[1]["typeRole"] == ["Contributor"]


def test_no_name_exceeds_the_registry_limit():
    for author_str in (
        (
            "Sara Aibar, Stein Aerts. Laboratory of Computational Biology. "
            "VIB-KU Leuven Center for Brain & Disease Research. Leuven, Belgium."
        ),
        "A" * 400,
        "Someone Reasonable [aut], " + "B" * 300 + " [ctb]",
    ):
        assert all(len(n) <= MAX_CREDIT_NAME for n in names(author_str))
