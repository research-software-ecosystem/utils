import os
import glob
import yaml
from pathlib import Path
from rdflib import Graph


def getBiotoolsIdFromBioContainers(biocontainers_data) -> str:
    """
    Get the bio.tools ID from the biocontainers data.
    """
    if "identifiers" in biocontainers_data.keys():
        for id in biocontainers_data["identifiers"]:
            if id.lower().startswith("biotools:"):
                return id
    return None


def getCitationFromBioContainers(biocontainers_data) -> list:
    """
    Get DOIs from the biocontainers data.
    """
    res = []
    if "identifiers" in biocontainers_data.keys():
        for id in biocontainers_data["identifiers"]:
            if id.lower().startswith("doi:"):
                res.append(id)
    return res


def rdfize(data) -> Graph:
    prefix = """
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix schema: <http://schema.org/> .
@prefix spdx: <http://spdx.org/rdf/terms/> .
@prefix biotools: <https://bio.tools/> .
@prefix biocontainers: <https://biocontainers.pro/tools/> .
"""

    triples = ""

    biotools_id = getBiotoolsIdFromBioContainers(data)
    dois = getCitationFromBioContainers(data)

    try:
        if "name" in data.keys():
            package_uri = f"biocontainers:{data['name']}"
            triples += f"{package_uri} rdf:type schema:SoftwareApplication .\n"
            if "description" in data.keys():
                triples += (
                    f'{package_uri} schema:description "{data["description"]}" .\n'
                )
            if "license" in data.keys():
                triples += f'{package_uri} schema:license "{data["license"]}" .\n'
            if biotools_id:
                triples += f"{package_uri} spdx:builtFrom {biotools_id} .\n"
                triples += f"{package_uri} schema:identifier {biotools_id} .\n"
            if "home_url" in data.keys():
                triples += f'{package_uri} schema:url "{data["home_url"]}" .\n'
            if "keywords" in data.keys():
                for keyword in data["keywords"]:
                    triples += f'{package_uri} schema:keywords "{keyword}" .\n'
            # process DOIs
            for doi in dois:
                triples += f'{package_uri} schema:citation "{doi}" .\n'

            g = Graph()
            g.parse(data=prefix + "\n" + triples, format="turtle")
            return g

    except Exception as e:
        print("PARSING ERROR for:")
        print(prefix + "\n" + triples)


def get_biotools_files_in_repo():
    tools = []
    for data_file in glob.glob("../../content/data/*/*.biocontainers.yaml"):
        tools.append(data_file)
    return tools


def process_tools_by_id(id="SPROUT"):
    """
    Go through all bio.tools entries and produce an RDF graph representation (BioSchemas / JSON-LD).
    """
    tool_files = get_biotools_files_in_repo()

    for tool_file in tool_files:
        if id in tool_file:
            path = Path(tool_file)
            tool = yaml.safe_load(path.read_text(encoding="utf-8"))

            print(tool_file)
            tool_id = tool["name"]
            tpe_id = tool_id.lower()
            directory = os.path.join("..", "..", "content", "data", tpe_id)

            ## generate biocontainers JSON-LD and TTL files
            temp_graph = rdfize(tool)

            temp_graph.serialize(
                format="json-ld",
                auto_compact=True,
                destination=os.path.join(directory, tpe_id + ".biocontainers.jsonld"),
            )
            temp_graph.serialize(
                format="turtle",
                destination=os.path.join(directory, tpe_id + ".biocontainers.ttl"),
            )


def clean():
    for data_file in glob.glob(r"../../content/data/*/*.biocontainers.jsonld"):
        print(f"removing file {data_file}")
        os.remove(data_file)
    for data_file in glob.glob(r"../../content/data/*/*.biocontainers.ttl"):
        print(f"removing file {data_file}")
        os.remove(data_file)


def process_tools():
    """
    Go through all bio.tools entries and produce an RDF graph representation (BioSchemas / JSON-LD).
    """
    tool_files = get_biotools_files_in_repo()
    for tool_file in tool_files:
        path = Path(tool_file)
        tool = yaml.safe_load(path.read_text(encoding="utf-8"))

        print(tool_file)
        tool_id = tool["name"]
        tpe_id = tool_id.lower()
        directory = os.path.join("..", "..", "content", "data", tpe_id)

        if not os.path.exists(directory):
            raise Exception(f"Directory {directory} does not exist for {tool_id}!")
            continue

        ## generate biocontainers JSON-LD and TTL files
        temp_graph = rdfize(tool)
        if temp_graph and os.path.exists(directory):
            temp_graph.serialize(
                format="json-ld",
                auto_compact=True,
                destination=os.path.join(directory, tpe_id + ".biocontainers.jsonld"),
            )
            temp_graph.serialize(
                format="turtle",
                destination=os.path.join(directory, tpe_id + ".biocontainers.ttl"),
            )


if __name__ == "__main__":
    clean()
    process_tools()
    # process_tools_by_id("macsyfinder")
