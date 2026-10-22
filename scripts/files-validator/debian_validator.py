import argparse
import os
import sys

import yaml


class readable_dir(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        prospective_dir = values
        if not os.path.isdir(prospective_dir):
            raise argparse.ArgumentTypeError(
                f"readable_dir:{prospective_dir} is not a valid path"
            )
        if os.access(prospective_dir, os.R_OK):
            setattr(namespace, self.dest, prospective_dir)
        else:
            raise argparse.ArgumentTypeError(
                f"readable_dir:{prospective_dir} is not a readable dir"
            )


parser = argparse.ArgumentParser(description="test", fromfile_prefix_chars="@")
parser.add_argument(
    "path",
    help="path to metadata dir, e.g. /content/data/",
    type=str,
    action=readable_dir,
)
args = parser.parse_args()


def validate_debian_files(path):
    dirname = os.path.basename(os.path.normpath(path))
    file = path + "/" + dirname + ".debian.yaml"
    global valid_files_counter

    def parse_yaml(file):
        with open(file, "r") as stream:
            return yaml.safe_load(stream)

    if os.path.exists(file) and file.endswith(".debian.yaml"):
        try:
            parse_yaml(file)
            valid_files_counter += 1
        except yaml.YAMLError:
            print("unable to parse " + file, file=sys.stderr)
            invalid_files.append(file)


invalid_files = []
valid_files_counter = 0
[validate_debian_files(f.path) for f in os.scandir(args.path) if f.is_dir()]

print(valid_files_counter, " files are valid")
if len(invalid_files) > 0:
    print(len(invalid_files), " files are invalid!!!", file=sys.stderr)
    print("Invalid files:", file=sys.stderr)
    for file in invalid_files:
        print(file, file=sys.stderr)
    sys.exit(1)
