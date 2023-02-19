#!/usr/bin/env python

import json
import os
import yaml

import argparse
from pathlib import Path

import jinja2

from collections import defaultdict


def fake(foo, **args):
    pass


def parse_biotools(directory):
    """
    Function to get biotools content data into memory.
    """
    data = dict()
    for root, dirs, files in os.walk(directory):
        for filename in files:
            if filename.endswith("biotools.json"):
                filepath = os.path.join(root, filename)
                with open(filepath, "r") as f:
                    biotools = json.load(f)
                    bio_id = biotools["biotoolsID"].lower()
                    data[bio_id] = {"data": biotools, "path": filepath}
    return data


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
                }
            )
        )
        extras = conda.get("extra", None)
        identifiers = defaultdict(list)
        if extras:
            ids = extras.get("identifiers", None)
            if ids:
                for id in ids:
                    n, c = id.split(":", 1)
                    identifiers[n].append(c)
        data[str(p.absolute())] = dict({"recipe": conda, "ids": identifiers})

    return data


def create_metadata(conda, path, biotools_id):
    data = conda["recipe"]["package"]
    data.update(conda["recipe"]["about"])
    extra = conda["recipe"].get("extra", None)
    if extra:
        identifiers = extra.get("identifiers", None)
        if extra.get("identifiers", None):
            data.update({"identifiers": extra["identifiers"]})
    data.update({"biotools_id": biotools_id})
        print(f"updating {path}...")
        print(data)
        yaml.dump(data, out)


def merge(tools, conda, content_path):
    for name, data in conda.items():
        ids = data["ids"]
        if ids:
            bio = ids.get("biotools", None)
            if bio:
                # fix me ... recipes with multiple biotools, ids
                # assert len(bio) == 1
                bio = bio[0].lower()
                path = os.path.join(content_path, bio)
                print(f"bioconda file {path} bio.tools entry {bio}")
                if not tools.get(bio, None):
                    print("None bio.tools entry", bio)
                    # if not os.path.exists(path):
                    #    os.mkdir(path)
                    # create_metadata(data, '%s/bioconda_%s.yaml' % (path, bio), bio)
                    continue
                create_metadata(data, "%s/bioconda_%s.yaml" % (path, bio), bio)
                # print(bio, name, tools[bio]['path'])
                continue


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
        help="path to metadata dir, e.g. content/data/",
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
    content_path = args.biotools
    tools = parse_biotools(args.biotools)
    conda = parse_bioconda(args.bioconda)
    merge(tools, conda, content_path)
