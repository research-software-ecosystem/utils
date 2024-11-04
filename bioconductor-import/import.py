import argparse
import glob
import json
import os

import requests

BIOCONDUCTOR_ENDPOINT = "https://bioconductor.org/packages/json/3.20/bioc/packages.json"

def clean():
    import_directory = os.path.join("imports", "bioconductor")
    os.makedirs(import_directory, exist_ok=True)
    for package_file in glob.glob(r"imports/bioconductor/*.bioconductor.json"):
        os.remove(package_file)
    #for package_file in glob.glob(r"data/*/*.bioconductor.json"):
    #    os.remove(package_file)

def retrieve(filters=None):
    """
    Go through bioconductor entries using its API and save the JSON files
    in the right folders
    """
    packs = requests.get(BIOCONDUCTOR_ENDPOINT).json()
    for pack in list(packs.values()):
        path = os.path.join("imports", "bioconductor", f"{pack['Package'].lower()}.bioconductor.json")
        with open(path, "w") as write_file:
            json.dump(pack, write_file, sort_keys=True, indent=4, separators=(",", ": "))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="bioconductor import script")
    args = parser.parse_args()
    clean()
    retrieve()
