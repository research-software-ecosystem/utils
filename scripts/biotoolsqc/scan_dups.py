import os
import json
import pandas as pd
import argparse
import glob
from Bio import Entrez
import logging
from tqdm import tqdm


# PMID->DOI cache

CACHE_FILE = "pmid_doi_cache.json"


def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as file:
            return json.load(file)
    else:
        return {}


def save_cache(cache):
    with open(CACHE_FILE, "w") as file:
        json.dump(cache, file)


cache = load_cache()

# Define the command-line arguments
parser = argparse.ArgumentParser(
    description="Extract biotoolsID and publication.doi from JSON files"
)
parser.add_argument(
    "directory", type=str, help="path to the directory containing the JSON files"
)
parser.add_argument("name_pattern", type=str, help="name pattern of the JSON files")
parser.add_argument(
    "--output",
    type=str,
    help="optional: name of the output CSV file (default: output.csv)",
    default="output.csv",
)
parser.add_argument(
    "--duplicate_output",
    type=str,
    help="optional: name of the output CSV file for duplicate DOIs (default: duplicate_output.csv)",
    default="duplicate_output.csv",
)
parser.add_argument(
    "--log-level",
    choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    default="INFO",
    help="Set the logging level (default: INFO)",
)
parser.add_argument(
    "--email", type=str, help="User email used for Entrez calls", default=None
)

# Parse the command-line arguments
args = parser.parse_args()

if args.email:
    Entrez.email = args.email  # Set your email address


def get_doi_from_pubmed_id(pubmed_id):
    if pubmed_id in cache:
        return cache[pubmed_id]
    handle = Entrez.efetch(db="pubmed", id=str(pubmed_id), retmode="xml")
    records = Entrez.read(handle)
    handle.close()
    logging.info(f"Retrieving DOI for PMID {pubmed_id}")
    try:
        article = records["PubmedArticle"][0]["PubmedData"]["ArticleIdList"]
        for identifier in article:
            if identifier.attributes["IdType"] == "doi":
                cache[pubmed_id] = identifier
                save_cache(cache)
                logging.info(f"Found DOI for PMID {pubmed_id}: {identifier}")
                return identifier
    except (KeyError, IndexError):
        pass
    cache[pubmed_id] = None
    save_cache(cache)
    logging.warning(f"Didn't find DOI for PMID {pubmed_id}")
    return None


# Configure logging based on the provided log level
logging.basicConfig(level=args.log_level)

# Initialize an empty list to store the extracted data
data = []

# Initialize a list to store publication DOIs
publication_dois = []

# Get the total number of files for the progress bar
total_files = len(glob.glob(os.path.join(args.directory, args.name_pattern)))

# Loop through each JSON file in the directory with tqdm for progress bar
for filename in tqdm(
    glob.glob(os.path.join(args.directory, args.name_pattern)),
    total=total_files,
    desc="Processing files",
):
    try:
        # Load the JSON file
        with open(filename, "r") as f:
            json_data = json.load(f)

        # Extract the desired keys with error handling
        biotoolsID = json_data.get("biotoolsID", None)

        # Extract publication DOIs from the array using list comprehension
        publication_list = []
        for item in json_data.get("publication", []):
            doi = item.get("doi", None)
            if doi is not None:
                publication_list.append(doi)
                continue
            pmid = item.get("pmid", None)
            if pmid is not None:
                doi = get_doi_from_pubmed_id(pmid)
                publication_list.append(doi)
        publication_list = [
            item.get("doi", None) for item in json_data.get("publication", [])
        ]

        # Filter out None values
        publication_list = [doi for doi in publication_list if doi is not None]

        # Extend publication_dois with the extracted DOIs
        publication_dois.extend(publication_list)

        # Check if biotoolsID is present before appending to the list
        if biotoolsID is not None:
            data.append({"biotoolsID": biotoolsID, "publication.doi": publication_list})
        else:
            print(f"Skipping {filename} - Missing required key 'biotoolsID'.")
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON in {filename}: {e}")
    except KeyError as e:
        print(f"KeyError in {filename}: {e}")

# Create a pandas dataframe from the extracted data
df = pd.DataFrame(data)

# Flatten the 'publication.doi' lists before checking for duplicates
flat_dois = [doi for sublist in df["publication.doi"] for doi in sublist]

# Check for duplicate DOIs and create a new dataframe with corresponding biotoolsIDs
duplicate_df = df[df.duplicated(subset="publication.doi", keep=False)]
duplicate_dois = duplicate_df.explode("publication.doi")["publication.doi"].unique()

if len(duplicate_dois) > 0:
    print("\nDuplicate DOIs:")
    print(duplicate_dois)

    # Create a new DataFrame to store duplicate DOI information
    duplicate_info = []
    for doi in duplicate_dois:
        biotools_ids = duplicate_df[
            duplicate_df["publication.doi"].apply(lambda x: doi in x)
        ]["biotoolsID"].tolist()
        duplicate_info.append({"DOI": doi, "BiotoolsID": biotools_ids})

    # Create a DataFrame from the duplicate_info list
    duplicate_df_final = pd.DataFrame(duplicate_info)

    # Save the duplicate DataFrame to a CSV file
    duplicate_df_final.to_csv(args.duplicate_output, index=False)

    print("\nDuplicate DOIs and Corresponding BiotoolsIDs:")
    print(duplicate_df_final)
else:
    print("\nNo duplicate DOIs found.")

# Save the original dataframe to a CSV file
df.to_csv(args.output, index=False)
