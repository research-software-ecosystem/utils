import dateutil.parser
import requests
import logging

logger = logging.getLogger(__name__)


def get_publication_metadata(doi):
    """
    Fetch publication metadata based on DOI using CrossRef API.

    Args:
        doi (str): Digital Object Identifier (with or without 'doi:' prefix)

    Returns:
        dict: Publication metadata with keys: abstract, authors, citationCount,
              date, journal, title. Returns None if metadata not found.
    """
    try:
        # Remove 'doi:' prefix if present
        clean_doi = doi.replace("doi:", "").strip() if doi else None

        if not clean_doi:
            logger.error("No DOI provided")
            return None

        # Fetch data from CrossRef API
        url = f"https://api.crossref.org/works/{clean_doi}"
        headers = {"Accept": "application/json"}
        response = requests.get(url, headers=headers)

        if response.status_code != 200:
            logger.error(
                f"Failed to fetch metadata for DOI {clean_doi}: HTTP {response.status_code}"
            )
            return None

        data = response.json().get("message", {})

        if not data:
            logger.error(f"No metadata found for DOI {clean_doi}")
            return None

        # Extract metadata
        title = data.get("title", [""])[0] if data.get("title") else ""
        abstract = data.get("abstract", "")
        journal = ""
        authors = []
        date = None
        citation_count = data.get("is-referenced-by-count", None)

        # Extract journal
        if "container-title" in data and data["container-title"]:
            journal = data["container-title"][0]
        elif "short-container-title" in data and data["short-container-title"]:
            journal = data["short-container-title"][0]

        # Extract date
        try:
            if "published-print" in data and "date-parts" in data["published-print"]:
                date_parts = data["published-print"]["date-parts"][0]
            elif (
                "published-online" in data and "date-parts" in data["published-online"]
            ):
                date_parts = data["published-online"]["date-parts"][0]
            elif "published" in data and "date-parts" in data["published"]:
                date_parts = data["published"]["date-parts"][0]
            else:
                date_parts = None

            if date_parts:
                # date_parts is [year, month, day] but may have fewer elements
                date_str = "-".join(
                    str(p).zfill(2) if i > 0 else str(p)
                    for i, p in enumerate(date_parts)
                )
                date = dateutil.parser.parse(date_str).isoformat()
        except (KeyError, TypeError, ValueError) as e:
            logger.warning(f"Publication date not available for DOI {clean_doi}: {e}")

        # Extract authors
        try:
            for author in data.get("author", []):
                if "family" in author:
                    given = author.get("given", "")
                    family = author.get("family", "")
                    name = f"{given} {family}".strip() if given else family
                    authors.append({"name": name})
                elif "name" in author:
                    authors.append({"name": author["name"]})
        except (KeyError, TypeError) as e:
            logger.warning(f"Authors not available for DOI {clean_doi}: {e}")

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
