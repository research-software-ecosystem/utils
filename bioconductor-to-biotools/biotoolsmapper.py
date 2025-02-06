import os
import json
import argparse
import glob

def load_json(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return None

def identity_key(json_data):
    """
    Extracts the key used for identity comparison from the JSON document.
    """
    return json_data.get("name")

def compare_files(pattern1, pattern2):
    files1 = glob.glob(pattern1)
    files2 = glob.glob(pattern2)
    
    json_data1 = {file1: load_json(file1) for file1 in files1}
    json_data2 = {file2: load_json(file2) for file2 in files2}
    
    mapped_files = {}
    only_in_files1 = []
    only_in_files2 = set(files2)
    
    for file1, json1 in json_data1.items():
        if not json1:
            continue
        
        id1 = identity_key(json1)
        matched = False
        
        for file2, json2 in json_data2.items():
            if json2 and identity_key(json2) == id1:
                mapped_files[file1] = file2
                only_in_files2.discard(file2)
                matched = True
                break
        
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
    parser = argparse.ArgumentParser(description="Compare two sets of bio.tools JSON files based on exact name matching.")
    parser.add_argument("pattern1", help="File pattern for the first set of JSON files.")
    parser.add_argument("pattern2", help="File pattern for the second set of JSON files.")
    parser.add_argument("output", help="Path to save the comparison results JSON file.")
    args = parser.parse_args()
    
    comparison_result = compare_files(args.pattern1, args.pattern2)
    
    with open(args.output, "w", encoding="utf-8") as outfile:
        json.dump(comparison_result, outfile, indent=4)
    
    print("Comparison complete. Results saved to", args.output)

if __name__ == "__main__":
    main()
