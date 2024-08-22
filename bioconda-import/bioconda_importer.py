#!/usr/bin/env python

import json
import os
import yaml

import argparse
from pathlib import Path

import jinja2

from collections import defaultdict


def clean(content_path):
    import_directory = os.path.join(content_path, "imports", "bioconda")
    os.makedirs(import_directory, exist_ok=True)
    for data_file in Path(content_path).glob("imports/bioconda/bioconda_*.yaml"):
        os.remove(data_file)
    for data_file in Path(content_path).glob("data/*/bioconda_*.yaml"):
        os.remove(data_file)


def fake(foo, **args):
    pass


def parse_bioconda(directory):
    """
    Function to get bioconda content data into memory.
    """
    data = dict()
    for p in Path(directory).glob("./*/meta.yaml"):
        template = jinja2.Template(p.read_text())
        conda = yaml.safe_load(
            template.render(
                {
                    "os": os,
                    "compiler": fake,
                    "environ": "",
                    "cdt": fake,
                    "pin_compatible": fake,
                    "pin_subpackage": fake,
                    "exact": fake,
                    "stdlib": fake,
                }
            )
        )
        data[str(p.absolute())] = conda

    return data


def merge(conda, content_path):
    bioconda_import_path = os.path.join(content_path, 'imports', 'bioconda')
    biotools_data_path = os.path.join(content_path, 'data')
    for name, data in conda.items():
        package_name = data['package']['name']
        import_file_path = os.path.join(bioconda_import_path, f"bioconda_{package_name}.yaml")
        with open(import_file_path, "w") as out:
            yaml.dump(data, out)
        if 'extra' not in data or 'identifiers' not in data['extra']:
            continue
        biotools_ids = [ident.split(':')[1].lower() for ident in data['extra']['identifiers'] if ident.startswith('biotools:')]
        for biotools_id in biotools_ids:
            biotools_file_path = os.path.join(content_path, 'data', biotools_id, f"bioconda_{package_name}.yaml")
            try:
                with open(biotools_file_path, "w") as out:
                    yaml.dump(data, out)
            except FileNotFoundError:
                print(f"Error trying to create the file {biotools_file_path}")
                pass

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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="test", fromfile_prefix_chars="@")
    parser.add_argument(
        "biotools",
        help="path to RSEc content dir, e.g. content/",
        type=str,
        action=readable_dir,
    )
    parser.add_argument(
        "bioconda",
        help="path to bioconda recipes, e.g. bioconda-recipes/recipes",
        type=str,
        action=readable_dir,
    )
    args = parser.parse_args()
    clean(args.biotools)
    conda = parse_bioconda(args.bioconda)
    merge(conda, args.biotools)
