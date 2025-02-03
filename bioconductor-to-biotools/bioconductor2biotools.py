"""
Script to process Bioconductor JSON data and convert it into bio.tools JSON format.

This script extracts author details, processes Bioconductor citation files, and optionally updates the bio.tools data using a previous version.

Mermaid.js diagram illustrating the workflow:

```mermaid
graph TD
    BF[fa:fa-file Bioconductor JSON]
    BT[fa:fa-file bio.tools JSON]
    BCF[fa:fa-file Bioconductor Citation HTML JSON]
    EBT[fa:fa-file Existing bio.tools JSON]
    PBP[fa:fa-cogs 1. process bioconductor package] 
    EP[fa:fa-cogs 2. extract publications]
    UPBT[fa:fa-cogs 3. update with previous data]
    BF --> PBP
    PBP --> BT
    BT --> EP
    BCF --> EP
    EP --> BT
    BT --> UPBT
    EBT --> UPBT
    UPBT --> BT
```

"""

import re
import json
import argparse
from bs4 import BeautifulSoup

def process_authors(author_str):
    """
    Processes the author field, extracting names, roles, and ORCIDs, and filters only relevant authors.
    
    Parameters:
        author_str (str): The raw author string from Bioconductor.
    
    Returns:
        list: A list of dictionaries with author details formatted for bio.tools.
    """

    authors = []
    author_entries = re.split(r',(?![^\[]*\])', author_str)  # Split on commas outside square brackets
    
    for entry in author_entries:
        entry = entry.strip()
        
        roles_match = re.findall(r'\[([^\]]+)\]', entry)
        roles = [role.strip() for group in roles_match for role in group.split(',')]
        
        orcid_match = re.search(r'\(<(https://orcid\.org/\d{4}-\d{4}-\d{4}-\d{4})>\)', entry)
        orcid = orcid_match.group(1) if orcid_match else None
        
        name_match = re.match(r'^[^\[\(<]+', entry)
        if name_match:
            type_role = []
            author_entry = {"name": name_match.group(0).strip()}
            if 'aut' in roles or 'cre' in roles or 'ctb' in roles:
                author_entry["typeEntity"] = "Person"
            elif 'fnd' in roles:
                author_entry["typeEntity"] = "Funding agency"
            if 'ctb' in roles or 'fnd' in roles:
                type_role.append("Contributor")
            if 'aut' in roles:
                type_role.append("Developer")
            if 'cre' in roles:
                type_role.append("Maintainer")
            if orcid:
                author_entry["orcid"] = orcid
            if type_role:
                author_entry["typeRole"] = type_role
            authors.append(author_entry)
    
    return authors


def process_bioconductor_package(data):
    """
    Converts a Bioconductor JSON entry into a bio.tools formatted dictionary.
    
    Parameters:
        data (dict): The input JSON data from Bioconductor.
    
    Returns:
        dict: A dictionary formatted for bio.tools.
    """
    return {
        "biotoolsCURIE": f"biotools:bioconductor-{data['Package']}",
        "biotoolsID": f"bioconductor{data['Package']}",
        "collectionID": ["BioConductor"],
        "credit": process_authors(data.get("Author", "")),
        "description": data.get("Description", ""),
        "documentation": [
            {
                "type": ["User manual"],
                "url": f"http://bioconductor.org/packages/release/bioc/html/{data['Package']}.html"
            }
        ],
        "download": [
            {
                "type": "Source code",
                "url": f"http://bioconductor/packages/release/bioc/src/{data.get('source.ver', '')}"
            }
        ],
        "homepage": f"http://bioconductor.org/packages/release/bioc/html/{data['Package']}.html",
        "language": ["R"],
        "license": data.get("License", ""),
        "name": data.get("Package", ""),
        "operatingSystem": ["Linux", "Mac", "Windows"],
        "owner": "bioconductor_import",
        "toolType": ["Command-line tool", "Library"],
        "version": [data.get("Version", "")]
    }

def extract_publications(citation_html):
    """
    Extracts publication information from a Bioconductor citation HTML file.
    
    Parameters:
        citation_html (str): The HTML content of the Bioconductor citation page.
    
    Returns:
        list: A list of publication dictionaries formatted for bio.tools.
    """
    publications = []
    soup = BeautifulSoup(citation_html, "html.parser")
    
    for link in soup.find_all("a", href=True):
        href = link["href"].strip()
        if "doi.org" in href:
            publications.append({"doi": href.split("doi.org/")[-1]})
        else:
            print(f"Error: Non-DOI publication URL found: {href}")
    
    return publications

def update_with_previous_data(new_data, previous_data):
    """
    Updates the newly generated bio.tools data with select fields from a previous bio.tools JSON file.
    
    Parameters:
        new_data (dict): The newly generated bio.tools JSON data.
        previous_data (dict): The previous bio.tools JSON data.
    
    Returns:
        dict: The updated bio.tools JSON data.
    """
    keys_to_copy = ["additionDate", "biotoolsCURIE", "biotoolsID", "collectionID", "editPermission", "function"]
    for key in keys_to_copy:
        if key in previous_data:
            new_data[key] = previous_data[key]
    return new_data

def main():
    """
    Main function to parse command-line arguments and process JSON files for bio.tools formatting.
    """
    parser = argparse.ArgumentParser(description="Process Bioconductor JSON and convert it to bio.tools JSON format.")
    parser.add_argument("bioconductor_json_file", help="Path to the input Bioconductor JSON file.")
    parser.add_argument("bioconductor_citation_file", help="Path to the Bioconductor citation HTML file.")
    parser.add_argument("biotools_json_file", help="Path to the output bio.tools JSON file.")
    parser.add_argument("--previous-biotools-json-file", help="Path to the previous bio.tools JSON file.", required=False)
    args = parser.parse_args()
    
    with open(args.bioconductor_json_file, "r") as infile:
        data = json.load(infile)
    
    processed_data = process_bioconductor_package(data)
    
    with open(args.bioconductor_citation_file, "r", encoding="utf-8") as citation_file:
        citation_html = citation_file.read()
        processed_data["publications"] = extract_publications(citation_html)
    
    if args.previous_biotools_json_file:
        with open(args.previous_biotools_json_file, "r") as prevfile:
            previous_data = json.load(prevfile)
        processed_data = update_with_previous_data(processed_data, previous_data)
    
    with open(args.biotools_json_file, "w") as outfile:
        json.dump(processed_data, outfile, indent=4)
    
if __name__ == "__main__":
    main()
