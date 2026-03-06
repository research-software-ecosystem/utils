import dateutil.parser
import requests
import requests_cache
import logging
from bs4 import BeautifulSoup
import re

logger = logging.getLogger(__name__)

# Install cache for requests to doi.org
# Cache expires after 30 days
requests_cache.install_cache(
    cache_name="doi_cache",
    backend="sqlite",
    expire_after=2592000,  # 30 days in seconds
)


def clean_jats_abstract(jats_text):
    """
    Convert JATS XML formatted abstract to plain text.

    Args:
        jats_text (str): Abstract text in JATS XML format

    Returns:
        str: Plain text version of the abstract
    """
    if not jats_text:
        return ""

    try:
        # Parse the JATS XML
        soup = BeautifulSoup(jats_text, "html.parser")

        # Get plain text, which automatically strips tags
        text = soup.get_text()

        # Clean up whitespace
        # Replace multiple spaces with single space
        text = re.sub(r"\s+", " ", text)

        # Strip leading/trailing whitespace
        text = text.strip()

        # Remove "Abstract" prefix if it's at the start
        if text.startswith("Abstract "):
            text = text[9:].strip()

        return text

    except Exception as e:
        logger.warning(f"Error parsing JATS abstract: {e}")
        # Fallback to simple regex tag removal
        text = re.sub(r"<[^>]+>", "", jats_text)
        text = re.sub(r"\s+", " ", text).strip()
        if text.startswith("Abstract "):
            text = text[9:].strip()
        return text


def get_publication_metadata(doi):
    """
    Fetch publication metadata based on DOI using doi.org content negotiation.
    Results are cached for 30 days to avoid repeated requests.

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

        # Fetch data from doi.org using content negotiation
        # Using CSL-JSON format which is well-structured for citation data
        url = f"https://doi.org/{clean_doi}"
        headers = {"Accept": "application/vnd.citationstyles.csl+json"}
        response = requests.get(url, headers=headers)

        # Log if response came from cache
        if hasattr(response, "from_cache") and response.from_cache:
            logger.debug(f"Retrieved metadata for DOI {clean_doi} from cache")

        if response.status_code != 200:
            logger.error(
                f"Failed to fetch metadata for DOI {clean_doi}: HTTP {response.status_code}"
            )
            return None

        data = response.json()

        if not data:
            logger.error(f"No metadata found for DOI {clean_doi}")
            return None

        # Extract metadata from CSL-JSON format
        title = data.get("title", "")
        abstract = clean_jats_abstract(data.get("abstract", ""))
        journal = ""
        authors = []
        date = None
        citation_count = None  # doi.org doesn't provide citation counts

        # Extract journal
        if "container-title" in data:
            journal = data["container-title"]
        elif "container-title-short" in data:
            journal = data["container-title-short"]

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
            elif "issued" in data and "date-parts" in data["issued"]:
                date_parts = data["issued"]["date-parts"][0]
            else:
                date_parts = None

            if date_parts:
                # date_parts is [year, month, day] but may have fewer elements
                if len(date_parts) == 1:
                    date_str = f"{date_parts[0]}-01-01"
                elif len(date_parts) == 2:
                    date_str = f"{date_parts[0]}-{str(date_parts[1]).zfill(2)}-01"
                else:
                    date_str = f"{date_parts[0]}-{str(date_parts[1]).zfill(2)}-{str(date_parts[2]).zfill(2)}"
                date = dateutil.parser.parse(date_str).isoformat()
        except (KeyError, TypeError, ValueError, IndexError) as e:
            logger.warning(f"Publication date not available for DOI {clean_doi}: {e}")

        # Extract authors
        try:
            for author in data.get("author", []):
                if "family" in author:
                    given = author.get("given", "")
                    family = author.get("family", "")
                    name = f"{given} {family}".strip() if given else family
                    authors.append({"name": name})
                elif "literal" in author:
                    authors.append({"name": author["literal"]})
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
