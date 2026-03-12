import dateutil.parser
import requests
import logging

logger = logging.getLogger(__name__)


def get_publication_metadata(doi):
    """
    Fetch publication metadata based on DOI.

    Args:
        doi (str): Digital Object Identifier (with or without 'doi:' prefix)

    Returns:
        dict: Publication metadata with keys: abstract, authors, citationCount,
              date, journal, title. Returns None if metadata not found.
    """
    try:
        # Remove 'doi:' prefix if present
        clean_doi = doi.replace("doi:", "") if doi else None

        if not clean_doi:
            logger.error("No DOI provided")
            return None

        # Fetch data from Europe PMC
        url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:{clean_doi}&format=json&resultType=core"
        headers = {"Accept": "application/json"}
        response = requests.get(url, headers=headers)

        if response.status_code != 200:
            logger.error(
                f"Failed to fetch metadata for DOI {clean_doi}: HTTP {response.status_code}"
            )
            return None

        results = response.json().get("resultList", {}).get("result", [])

        if not results:
            logger.error(f"No metadata found for DOI {clean_doi}")
            return None

        data = results[0]

        # Extract metadata
        title = data.get("title", "")
        abstract = data.get("abstractText", "")
        journal = ""
        authors = []
        date = None
        citation_count = None

        try:
            journal = data["journalInfo"]["journal"]["title"]
        except (KeyError, TypeError):
            logger.warning(f"Journal not available for DOI {clean_doi}")

        try:
            date = dateutil.parser.parse(data["journalInfo"]["printPublicationDate"])
            date = date.isoformat()
        except (KeyError, TypeError, ValueError):
            logger.warning(f"Publication date not available for DOI {clean_doi}")

        try:
            for author in data["authorList"]["author"]:
                authors.append({"name": author["fullName"]})
        except (KeyError, TypeError):
            logger.warning(f"Authors not available for DOI {clean_doi}")

        try:
            citation_count = data["citedByCount"]
        except KeyError:
            logger.warning(f"Citation count not available for DOI {clean_doi}")

        return {
            "abstract": abstract,
            "authors": authors,
            "citationCount": citation_count,
            "date": date,
            "journal": journal,
            "title": title,
        }

    except Exception as e:
        logger.error(f"Error fetching metadata for DOI {doi}: {str(e)}")
        return None
