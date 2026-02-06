import glob
import json
import os

import requests

GALAXY_ALL_TOOLS_METADATA = "https://raw.githubusercontent.com/galaxyproject/galaxy_codex/refs/heads/main/communities/all/resources/tools.json"
GALAXY_ALL_WORKFLOWS_METADATA = "https://raw.githubusercontent.com/galaxyproject/galaxy_codex/refs/heads/main/communities/all/resources/workflows.json"


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

    response = requests.get(GALAXY_ALL_WORKFLOWS_METADATA)
    workflow_entry = json.loads(response.text)

    response = requests.get(GALAXY_ALL_TOOLS_METADATA)
    entry = json.loads(response.text)
    nb_tools = 1

    galaxy_directory = os.path.join("imports", "galaxy")
    os.makedirs(galaxy_directory, exist_ok=True)

    for tool in entry:
        galaxy_tool_id = tool.get("Suite ID")

        if not galaxy_tool_id:
            print("No tool id found")
            continue

        # create full path for tutorials
        if "Related Tutorials" in tool:
            updated_tutorials = []
            for tutorial in tool["Related Tutorials"]:
                if (
                    "https://training.galaxyproject.org/training-material/"
                    not in tutorial
                ):
                    topic = tutorial.split("/")[0]
                    name = tutorial.split("/")[1]
                    new_tutorials = f"https://training.galaxyproject.org/training-material/topics/{topic}/tutorials/{name}/tutorial.html"
                    updated_tutorials.append(new_tutorials)
            tool["Related Tutorials"] = updated_tutorials

        # add workflow metadata
        if "Related Workflows" in tool:
            related_links = set(
                tool["Related Workflows"]
            )  # Convert to set for faster lookup
            matched_workflows = []
            for wf in workflow_entry:
                if wf.get("link") in related_links:
                    subset = {
                        "link": wf.get("link"),
                        "latest_version": wf.get("latest_version"),
                        "name": wf.get("name"),
                        "create_time": wf.get("create_time"),
                    }
                    matched_workflows.append(subset)
            tool["Related Workflows"] = matched_workflows

        # store tool json in galaxy import folder
        galaxy_tool_id = galaxy_tool_id.lower()
        tool_cleaned = {k.replace(" ", "_"): v for k, v in tool.items()}
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

        # store tool json also matching RSEc folder (match on bio.tool ID)
        tool_id = tool.get("bio.tool ID")
        if tool_id:
            tpe_id = tool_id.lower()
            directory = os.path.join("data", tpe_id)
            if os.path.isdir(directory):
                data_save_path = os.path.join(directory, f"{tpe_id}.galaxy.json")
                with (
                    open(save_path, "rb") as f_src,
                    open(data_save_path, "wb") as f_dst,
                ):
                    f_dst.write(f_src.read())
                print(f"copy tool #{nb_tools} to data folder: {tpe_id}")

        nb_tools += 1


if __name__ == "__main__":
    clean()
    retrieve()
