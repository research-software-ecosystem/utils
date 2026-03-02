#!/usr/bin/env python

import os
import yaml
import argparse
from pathlib import Path
import jinja2


def clean(content_path):
    import_directory = os.path.join(content_path, "imports", "bioconda")
    os.makedirs(import_directory, exist_ok=True)
    for data_file in Path(content_path).glob("imports/bioconda/bioconda_*.yaml"):
        os.remove(data_file)
    for data_file in Path(content_path).glob("data/*/bioconda_*.yaml"):
        os.remove(data_file)


def parse_bioconda(directory):
    """
    Get bioconda content data into memory.
    """
    data = dict()

    # Create a custom Undefined class that treats undefined variables in conda jinja template as empty strings
    class SilentUndefined(jinja2.Undefined):
        def __str__(self):
            return ""

        __repr__ = __str__

        def __bool__(self):
            return False

        __getattr__ = __getitem__ = lambda self, *a, **kw: self

        def __iter__(self):
            return iter(())

        def __call__(self, *a, **kw):
            return self

    # load custom Undefined class in custom environment
    env = jinja2.Environment(undefined=SilentUndefined)

    for p in Path(directory).glob("./*/meta.yaml"):
        print(f"processing {p}...")
        try:
            template = env.from_string(p.read_text())
            conda = yaml.safe_load(
                template.render(
                    {
                        "os": os,
                    }
                )
            )
            data[str(p.absolute())] = conda
        except Exception as e:
            print(f"Error processing {p}: {type(e).__name__}: {str(e)}")
            continue

    return data


def merge(conda, content_path):
    bioconda_import_path = os.path.join(content_path, "imports", "bioconda")
    biotools_data_path = os.path.join(content_path, "data")
    for name, data in conda.items():
        try:
            package_name = data["package"]["name"]
            import_file_path = os.path.join(
                bioconda_import_path, f"bioconda_{package_name}.yaml"
            )
            with open(import_file_path, "w") as out:
                yaml.dump(data, out)
            extra = data.get("extra")  # safely returns None if 'extra' not in data
            if not extra or "identifiers" not in extra:
                continue
            biotools_ids = [
                ident.split(":")[1].lower()
                for ident in data["extra"]["identifiers"]
                if ident.startswith("biotools:")
            ]
            for biotools_id in biotools_ids:
                biotools_file_path = os.path.join(
                    biotools_data_path, biotools_id, f"bioconda_{package_name}.yaml"
                )
                try:
                    with open(biotools_file_path, "w") as out:
                        yaml.dump(data, out)
                except FileNotFoundError:
                    print(f"Error trying to create the file {biotools_file_path}")
        except (KeyError, TypeError) as e:
            print(
                f"Error processing {name}: missing or invalid package structure ({type(e).__name__}: {e})"
            )
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
    parser = argparse.ArgumentParser(
        description="bioconda import script", fromfile_prefix_chars="@"
    )
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
