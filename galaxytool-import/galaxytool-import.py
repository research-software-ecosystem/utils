import json
import os
import glob
import pandas as pd

from boltons.iterutils import remap

GALAXY_ALL_TOOLS_METADATA = "https://raw.githubusercontent.com/galaxyproject/galaxy_tool_metadata_extractor/main/results/all_tools.tsv"


def clean():
    for data_file in glob.glob(r"data/*/*.galaxy.json"):
        os.remove(data_file)


def retrieve():
    """
    Go through all galaxy tools metadata entries using github file and save the JSON files
    in the right folders
    """

    entry = pd.read_csv(GALAXY_ALL_TOOLS_METADATA, sep="\t")
    entry = json.loads(entry.to_json(orient="records"))
    nb_tools = 1
    for tool in entry:
        tool_id = tool["bio.tool id"]
        if not tool_id:
            continue
        tpe_id = tool_id.lower()
        directory = os.path.join("data", tpe_id)
        drop_false = lambda path, key, value: bool(value)
        tool_cleaned = remap(tool, visit=drop_false)
        if not os.path.isdir(directory):
            continue
        with open(os.path.join(directory, tpe_id + ".galaxy.json"), "w") as write_file:
            json.dump(
                tool_cleaned,
                write_file,
                sort_keys=True,
                indent=4,
                separators=(",", ": "),
            )
        print(f"import tool #{nb_tools}: {tool_id}")
        nb_tools += 1


if __name__ == "__main__":
    clean()
    retrieve()
