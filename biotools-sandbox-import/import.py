import json
import os
import sys
import glob
import argparse

import requests
from boltons.iterutils import remap

def clean():
    for data_file in glob.glob(r"data/*/*.biotools.json"):
        os.remove(data_file)


def retrieve(filters=None, sandbox=False):
    """
    Go through bio.tools entries using its API and save the JSON files
    in the right folders
    """
    api_endpoint = 'https://bio.tools/api/tool/'

    if sandbox: 
        api_endpoint = 'https://ecosystem.bio.tools/api/tool/'
        print('Using bio.tools sandbox server!')

    i = 1
    nb_tools = 1
    has_next_page = True
    filters = filters or {}
    
    while has_next_page:
        parameters = {**filters, **{"page": i}}
        response = requests.get(
            api_endpoint,
            params=parameters,
            headers={"Accept": "application/json"},
        )
        try:
            entry = response.json()
        except JSONDecodeError as e:
            print("Json decode error for " + str(req.data.decode("utf-8")))
            break
        has_next_page = entry["next"] != None

        for tool in entry["list"]:
            tool_id = tool["biotoolsID"]
            tpe_id = tool_id.lower()
            directory = os.path.join("data", tpe_id)
            if not os.path.isdir(directory):
                os.mkdir(directory)
            with open(os.path.join(directory, tpe_id + ".biotools.json"), "w") as write_file:
                drop_false = lambda path, key, value: bool(value)
                tool_cleaned = remap(tool, visit=drop_false)
                json.dump(
                    tool_cleaned, write_file, sort_keys=True, indent=4, separators=(",", ": ")
                )
            nb_tools += 1
            print(f"import tool #{nb_tools}: {tool_id} in folder {directory}")
        i += 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="biotools import script", allow_abbrev=False)
    parser.add_argument(
        "collection", type=str, default="*", nargs="?", help="collection name filter"
    )

    # sandbox flag for importing from ecosystem.bio.tools, by default is False
    parser.add_argument('--sandbox', action='store_true')

    args = parser.parse_args()
    clean()
    if args.collection == "*":
        retrieve(sandbox=args.sandbox)
    else:
        retrieve(filters={"collection": args.collection}, sandbox=args.sandbox)