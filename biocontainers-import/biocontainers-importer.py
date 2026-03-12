import argparse
import os

import requests
import yaml


def import_biocontainers_annotations(url, content_data_path):
    r = requests.get(url, stream=True)

    if r.encoding is None:
        r.encoding = "utf-8"

    annotations = yaml.safe_load(r.text)
    valid_tools = []
    for key, value in annotations.items():
        tool_annotation_yaml = f"{content_data_path}/{key}/{key}.biocontainers.yaml"
        os.makedirs(os.path.dirname(tool_annotation_yaml), exist_ok=True)
        valid_tools.append(key)
        with open(tool_annotation_yaml, "w") as f:
            yaml.dump(value, f)
    return valid_tools


def clean_biocontainers_tools(valid_tools, content_data_path):
    for root, dirs, files in os.walk(content_data_path):
        for file in files:
            #  traverse directories and find `.biocontainers.yaml` files
            if file.endswith(".biocontainers.yaml"):
                existing_tool = file.replace(".biocontainers.yaml", "")
                if existing_tool not in valid_tools:
                    # delete files that are not defined in biocontainers url
                    os.remove(os.path.join(root, file))


class readable_dir(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        prospective_dir = values
        if not os.path.isdir(prospective_dir):
            raise argparse.ArgumentTypeError(
                "readable_dir:{0} is not a valid path".format(prospective_dir)
            )
        if os.access(prospective_dir, os.R_OK):
            setattr(namespace, self.dest, prospective_dir)
        else:
            raise argparse.ArgumentTypeError(
                "readable_dir:{0} is not a readable dir".format(prospective_dir)
            )


parser = argparse.ArgumentParser(description="test", fromfile_prefix_chars="@")
parser.add_argument(
    "biotools",
    help="path to metadata dir, e.g. content/data/",
    type=str,
    action=readable_dir,
)
parser.add_argument("url", help="url to biocontainers annotations", type=str)

args = parser.parse_args()
print(args)

valid_tools = import_biocontainers_annotations(args.url, args.biotools)
clean_biocontainers_tools(valid_tools, args.biotools)
