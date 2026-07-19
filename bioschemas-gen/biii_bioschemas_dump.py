"""Build BIII RDF dumps from the records versioned in metadata-commons."""

import importlib.util
import json
from pathlib import Path

from rdflib import Graph


def find_metadata_commons_root():
    workspace = Path(__file__).resolve().parents[2]
    candidates = (
        workspace / "metadata-commons",
        workspace / "content",
        workspace,
    )
    for candidate in candidates:
        if (candidate / "data").is_dir():
            return candidate
    raise FileNotFoundError("Could not locate the metadata-commons data directory")


def load_biii_importer():
    importer_path = (
        Path(__file__).resolve().parents[1]
        / "biii-import"
        / "biseEU_LD_export.py"
    )
    spec = importlib.util.spec_from_file_location("biii_importer", importer_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def add_jsonld_files(graph, files):
    for data_file in files:
        graph.parse(data_file, format="json-ld")


def build_bioschemas_dump(data_dir):
    files = sorted(data_dir.glob("*/*.neubias.bioschemas.jsonld"))
    print(f"found {len(files)} BIII Bioschemas descriptors")
    graph = Graph()
    add_jsonld_files(graph, files)
    return graph


def build_legacy_ontology_dump(data_dir):
    files = sorted(data_dir.glob("*/*.neubias.raw.json"))
    print(f"found {len(files)} raw BIII descriptors")
    importer = load_biii_importer()
    graph = Graph()
    for data_file in files:
        with data_file.open(encoding="utf-8") as source:
            graph.parse(data=importer.rdfize(json.load(source)), format="json-ld")
    return graph


def process_tools():
    repository = find_metadata_commons_root()
    data_dir = repository / "data"
    dataset_dir = repository / "datasets"
    dataset_dir.mkdir(exist_ok=True)

    build_bioschemas_dump(data_dir).serialize(
        format="turtle",
        destination=dataset_dir / "bioschemas-biii-dump.ttl",
    )
    build_legacy_ontology_dump(data_dir).serialize(
        format="turtle",
        destination=dataset_dir / "bise-ontology-biii-dump.ttl",
    )


if __name__ == "__main__":
    process_tools()
