import os
import json
import argparse
import glob
from tqdm import tqdm

def load_json(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return None

def identity_name(json_data):
    """
    Extracts the 'name' key for identity comparison.
    """
    return json_data.get("name")

def identity_doi(json_data):
    """
    Extracts the DOIs from the 'publication' field for identity comparison.
    """
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
}

def compare_files(pattern1, pattern2, identity_methods):
    files1 = glob.glob(pattern1)
    files2 = glob.glob(pattern2)
    
    json_data1 = {file1: load_json(file1) for file1 in files1}
    json_data2 = {file2: load_json(file2) for file2 in files2}
    
    mapped_files = {}
    only_in_files1 = []
    only_in_files2 = set(files2)
    
    for file1, json1 in tqdm(json_data1.items(), desc="Processing files", unit="file"):
        if not json1:
            continue
        
        matched = False
        
        for file2, json2 in json_data2.items():
            if not json2:
                continue
            
            # Check identity functions
            for method in identity_methods:
                id_func = IDENTITY_FUNCTIONS[method]
                id1 = id_func(json1)
                id2 = id_func(json2)
                
                if isinstance(id1, set) and isinstance(id2, set):
                    match_found = not id1.isdisjoint(id2)
                else:
                    match_found = id1 == id2
                
                if match_found:
                    mapped_files[file1] = file2
                    only_in_files2.discard(file2)
                    matched = True
                    break  # Stop checking once matched
        
        if not matched:
            only_in_files1.append(file1)
    
    result = {
        "matched_files": mapped_files,
        "only_in_files1": only_in_files1,
        "only_in_files2": list(only_in_files2)
    }
    
    print("Summary:")
    print(f"Matched files: {len(mapped_files)}")
    print(f"Unmatched files in {pattern1}: {len(only_in_files1)}")
    print(f"Unmatched files in {pattern2}: {len(only_in_files2)}")
    
    return result

def main():
    parser = argparse.ArgumentParser(description="Compare two sets of JSON files based on configurable identity functions.")
    parser.add_argument("pattern1", help="File pattern for the first set of JSON files.")
    parser.add_argument("pattern2", help="File pattern for the second set of JSON files.")
    parser.add_argument("output", help="Path to save the comparison results JSON file.")
    parser.add_argument("--methods", nargs="*", choices=IDENTITY_FUNCTIONS.keys(), default=list(IDENTITY_FUNCTIONS.keys()),
                        help="Identity methods to use for comparison. Defaults to all available methods.")
    
    args = parser.parse_args()
    
    comparison_result = compare_files(args.pattern1, args.pattern2, args.methods)
    
    with open(args.output, "w", encoding="utf-8") as outfile:
        json.dump(comparison_result, outfile, indent=4)
    
    print("Comparison complete. Results saved to", args.output)

if __name__ == "__main__":
    main()
