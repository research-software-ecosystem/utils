import json
import os
import sys
import glob
import argparse

import requests
from boltons.iterutils import remap

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.metadata import normalize_version_fields

BIOTOOLS_DOMAIN = "https://bio.tools"
SSL_VERIFY = True

def clean():
    for data_file in glob.glob(r"data/*/*.biotools.json"):
        os.remove(data_file)


def retrieve(filters=None):
    """
    Go through bio.tools entries using its API and save the JSON files
    in the right folders
    """

    i = 1
    nb_tools = 1
    has_next_page = True
    filters = filters or {}
    while has_next_page:
        parameters = {**filters, **{"page": i}}
        response = requests.get(
            f"{BIOTOOLS_DOMAIN}/api/tool/",
            params=parameters,
            headers={"Accept": "application/json"},
            verify=SSL_VERIFY
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
                tool_cleaned = normalize_version_fields(
                    tool_cleaned, ["version", "version[].version"]
                )

                json.dump(
                    tool_cleaned, write_file, sort_keys=True, indent=4, separators=(",", ": ")
                )
            nb_tools += 1
            print(f"import tool #{nb_tools}: {tool_id} in folder {directory}")
        i += 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="biotools import script")
    parser.add_argument(
        "collection", type=str, default="*", nargs="?", help="collection name filter"
    )
    args = parser.parse_args()
    clean()
    if args.collection == "*":
        retrieve()
    else:
        retrieve(filters={"collection": args.collection})
