import glob
import json
import os

import pandas as pd
from boltons.iterutils import remap

GALAXY_ALL_TOOLS_METADATA = "https://raw.githubusercontent.com/galaxyproject/galaxy_codex/results/all_tools.tsv"


def clean():
    for data_file in glob.glob(r"data/*/*.galaxy.json"):
        os.remove(data_file)
    for import_file in glob.glob(r"imports/galaxy/*.galaxy.json"):
        os.remove(import_file)


def retrieve():
    """
    Go through all galaxy tools metadata entries using github file and save the JSON files
    in the right folders
    """

    entry = pd.read_csv(GALAXY_ALL_TOOLS_METADATA, sep="\t")
    entry = json.loads(entry.to_json(orient="records"))
    nb_tools = 1

    galaxy_directory = os.path.join("imports", "galaxy")
    os.makedirs(galaxy_directory, exist_ok=True)

    for tool in entry:
        galaxy_tool_id = tool.get("Galaxy wrapper id")

        if not galaxy_tool_id:
            print("No tool id found")
            continue

        galaxy_tool_id = galaxy_tool_id.lower()

        drop_false = lambda path, key, value: bool(value)
        tool_cleaned = remap(tool, visit=drop_false)
        tool_cleaned = {k.replace(" ", "_"): v for k, v in tool_cleaned.items()}
        save_path = os.path.join(galaxy_directory, f"{galaxy_tool_id}.galaxy.json")
        with open(save_path, "w") as write_file:
            json.dump(
                tool_cleaned,
                write_file,
                sort_keys=True,
                indent=4,
                separators=(",", ": "),
            )
        print(f"import tool #{nb_tools}: {galaxy_tool_id}")

        tool_id = tool.get("bio.tool id")
        if tool_id:
            tpe_id = tool_id.lower()
            directory = os.path.join("data", tpe_id)
            if os.path.isdir(directory):
                data_save_path = os.path.join(directory, f"{tpe_id}.galaxy.json")
                with open(save_path, "rb") as f_src, open(
                    data_save_path, "wb"
                ) as f_dst:
                    f_dst.write(f_src.read())
                print(f"copy tool #{nb_tools} to data folder: {tpe_id}")

        nb_tools += 1


if __name__ == "__main__":
    clean()
    retrieve()
