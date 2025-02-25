import os
import json
import argparse
import glob
from tqdm import tqdm
from collections import defaultdict
import pandas as pd
from upsetplot import from_indicators, UpSet
import matplotlib.pyplot as plt
import tempfile
import logging

# configure logging
log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
levels = {
    'CRITICAL': logging.CRITICAL,
    'ERROR': logging.ERROR,
    'WARNING': logging.WARNING,
    'INFO': logging.INFO,
    'DEBUG': logging.DEBUG,
    'NOTSET': logging.NOTSET
}
logging.basicConfig(level=levels.get(log_level, logging.INFO))

def load_json(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return None

def identity_name(json_data):
    return json_data.get("name")

def identity_name_insensitive(json_data):
    return json_data.get("name").lower()

def identity_homepage(json_data):
    return json_data.get("homepage")

def identity_biotoolsID_unprefixed(json_data):
    return json_data.get("biotoolsID").removeprefix("bioconductor-")


def identity_doi(json_data):
    dois = set()
    publications = json_data.get("publication", [])
    for pub in publications:
        doi = pub.get("doi")
        if doi:
            dois.add(doi)
    return dois

IDENTITY_FUNCTIONS = {
    "name": identity_name,
    "doi": identity_doi,
    "name_insensitive": identity_name_insensitive,
    "homepage": identity_homepage,
    "biotoolsID_unprefixed": identity_biotoolsID_unprefixed
}

def create_match_upsetplot(data, filename, pattern):
    data = {method:list(files.values()) for method, files in data.items()}
    df = pd.DataFrame(data)
    data = from_indicators(list(IDENTITY_FUNCTIONS.keys()), df)
    upset = UpSet(data,show_counts="%d", show_percentages=True)
    upset.plot()
    title = f"Matching bio.tools files from {pattern}"
    plt.suptitle(title)
    plt.savefig(filename, dpi=300, bbox_inches="tight")
    logging.info(f"Upset plot {title} saved to {filename}")

def compare_files(pattern1, pattern2, identity_methods, upset1_path, upset2_path):
    files1 = glob.glob(pattern1)
    files2 = glob.glob(pattern2)
    
    json_data1 = {file1: load_json(file1) for file1 in files1}
    json_data2 = {file2: load_json(file2) for file2 in files2}
    
    match_results = defaultdict(lambda: defaultdict(set))
    only_in_files1 = set(files1)
    only_in_files2 = set(files2)
        
    match_registry = {'json_data1':{}, 'json_data2':{}}
    for method in identity_methods:
        match_registry['json_data1'][method] = {f: False for f in set(files1)}
        match_registry['json_data2'][method] = {f: False for f in set(files2)}

    for file1, json1 in tqdm(json_data1.items(), desc="Processing dataset", unit="file"):
        if not json1:
            continue
        
        for file2, json2 in json_data2.items():
            if not json2:
                continue
            match_found = {}
            for method in identity_methods:
                id_func = IDENTITY_FUNCTIONS[method]
                id1 = id_func(json1)
                id2 = id_func(json2)
                
                if isinstance(id1, set) and isinstance(id2, set):
                    match_found[method] = bool(not id1.isdisjoint(id2))
                else:
                    match_found[method] = bool(id1 == id2)
                if match_found[method]:
                    match_registry['json_data1'][method][file1] = True
                    match_registry['json_data2'][method][file2] = True
            if any(match_found.values()):
                for method in identity_methods:
                    if match_found[method]:
                        match_results[method][file1].add(file2)
                        only_in_files1.discard(file1)
                        only_in_files2.discard(file2)
                break
            
    result = {
        "match_results": {k: {f: list(v) for f, v in v.items()} for k, v in match_results.items()},
        "only_in_files1": list(only_in_files1),
        "only_in_files2": list(only_in_files2)
    }

    for method, matches in match_results.items():
        print(f"{method} matched: {len(matches)} files")
    print(f"Unmatched files in {pattern1}: {len(only_in_files1)}")
    print(f"Unmatched files in {pattern2}: {len(only_in_files2)}")

    create_match_upsetplot(match_registry['json_data1'], upset1_path, pattern1)
    create_match_upsetplot(match_registry['json_data2'], upset2_path, pattern2)

    return result

def main():
    parser = argparse.ArgumentParser(description="Compare two sets of JSON files based on configurable identity functions.")
    parser.add_argument("pattern1", help="File pattern for the first set of JSON files.")
    parser.add_argument("pattern2", help="File pattern for the second set of JSON files.")
    parser.add_argument("--results", help="Path to save the comparison results JSON file.", default=tempfile.NamedTemporaryFile(delete=False, suffix='.json').name)
    parser.add_argument("--upset1", help="Path to save the Upset plot summarising matches in the first set.", default=tempfile.NamedTemporaryFile(delete=False, suffix='.png').name)
    parser.add_argument("--upset2", help="Path to save the Upset plot summarising matches in the second set.", default=tempfile.NamedTemporaryFile(delete=False, suffix='.png').name)
    parser.add_argument("--methods", nargs="*", choices=IDENTITY_FUNCTIONS.keys(), default=list(IDENTITY_FUNCTIONS.keys()),
                        help="Identity methods to use for comparison. Defaults to all available methods.")
    
    args = parser.parse_args()
    
    comparison_result = compare_files(args.pattern1, args.pattern2, args.methods, args.upset1, args.upset2)
    
    with open(args.results, "w", encoding="utf-8") as outfile:
        json.dump(comparison_result, outfile, indent=4)
        logging.info(f"Matching results for {args.pattern1} against {args.pattern2} saved to {args.results}")

if __name__ == "__main__":
    main()
