import argparse
import glob
import json
import os
import requests
import logging
import yaml

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger()

# Bioconductor URL format
BIOCONDUCTOR_BASE_URL = "https://bioconductor.org/packages/json/{}/bioc/packages.json"


def get_bioconductor_version():
    """
    Query Bioconductor to get the latest version from the config.yaml file.
    """
    config_url = "https://bioconductor.org/config.yaml"
    try:
        # Fetch the config.yaml to extract the release version
        config_response = requests.get(config_url)
        config_response.raise_for_status()
        config = yaml.safe_load(config_response.text)

        # Extract the current release version
        version = config.get("release_version")
        if not version:
            logger.error("Release version not found in the config file.")
            return None

        logger.info(f"Detected latest Bioconductor version: {version}")
        return version
    except requests.RequestException as e:
        logger.error(f"Error fetching Bioconductor config: {e}")
        return None


def clean():
    import_directory = os.path.join("imports", "bioconductor")
    os.makedirs(import_directory, exist_ok=True)

    # Get a list of all package files to be removed
    package_files = glob.glob(r"imports/bioconductor/*.bioconductor.json")

    # Count and remove files
    removed_count = len(package_files)
    for package_file in package_files:
        os.remove(package_file)

    # Log the number of files removed
    logger.info(f"Cleaned up {removed_count} previous package files.")


def retrieve(version, filters=None):
    """
    Go through Bioconductor entries using its API for the provided version
    and save the JSON files in the right folders, but only for packages
    that have 'Software' in the 'biocViews' key.
    """
    if version is None:
        logger.error(
            "Unable to retrieve data because the Bioconductor version is not available."
        )
        return

    logger.info(f"Fetching data for Bioconductor version {version}...")
    endpoint = BIOCONDUCTOR_BASE_URL.format(version)

    try:
        packs = requests.get(endpoint).json()
    except requests.RequestException as e:
        logger.error(f"Error fetching data from Bioconductor API: {e}")
        return

    # Filter packages with 'Software' in the 'biocViews' key
    software_packs = [
        pack
        for pack in packs.values()
        if "biocViews" in pack and "Software" in pack["biocViews"]
    ]

    if not software_packs:
        logger.warning("No packages with 'Software' in 'biocViews' found.")
        return

    logger.info(f"Found {len(software_packs)} packages with 'Software' in 'biocViews'.")
    total_packs = len(software_packs)

    # Save the packages and log the progress
    for idx, pack in enumerate(software_packs, start=1):
        package_name = pack["Package"].lower()
        path = os.path.join(
            "imports", "bioconductor", f"{package_name}.bioconductor.json"
        )

        try:
            with open(path, "w") as write_file:
                json.dump(
                    pack, write_file, sort_keys=True, indent=4, separators=(",", ": ")
                )
            logger.info(f"Saved {idx}/{total_packs} - {package_name}")
            try:
                citation_html = requests.get(
                    f"https://www.bioconductor.org/packages/release/bioc/citations/{pack['Package']}/citation.html"
                ).text
                citation_path = os.path.join(
                    "imports",
                    "bioconductor",
                    f"{package_name}.bioconductor.citation.html",
                )
                with open(citation_path, "w") as write_file:
                    write_file.write(citation_html)
            except Exception as e:
                logger.error(f"Error fetching citation for {package_name}: {e}")
        except IOError as e:
            logger.error(f"Error saving package {package_name}: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bioconductor import script")
    args = parser.parse_args()

    # Clean old data
    clean()

    # Get the latest Bioconductor version
    version = get_bioconductor_version()

    # Retrieve new data based on the latest version
    retrieve(version)
