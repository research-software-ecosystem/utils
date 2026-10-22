import glob
import json
import os
from pathlib import Path

import requests
import yaml
from rdflib import Graph

try:
    from tabulate import tabulate
except ImportError:

    def tabulate(rows, headers=()):
        return "\n".join(" | ".join(str(value) for value in row) for row in rows)


def getBiotoolsIdFromBioContainers(biocontainers_data) -> str:
    """
    Get the bio.tools ID from the biocontainers data.
    """
    if "identifiers" in biocontainers_data:
        for id in biocontainers_data["identifiers"]:
            if isinstance(id, str) and id.lower().startswith("biotools:"):
                return id
            elif isinstance(id, str) and not id.lower().startswith("biotools:"):
                continue
            ## Fixing error from yaml where there's an extra space (ex. package spectra-cluster-cli)
            elif isinstance(id, dict) and "biotools" in id:
                id = "biotools:" + id["biotools"]
                return id
            elif isinstance(id, dict) and "biotools" not in id:
                continue
            else:
                print(f"WARNING: identifier is not a string: {id}")
    return None


def urlExists(url, timeout=1):
    # """Check if a biotools ID exists using the bio.tools JSON API (not the front-end URL)."""
    """Check if a URL exists"""
    # id = biotools_id.lower().split("biotools:", 1)[-1]
    # print(id)
    # api_url = f"https://bio.tools/api/tool/{id}/?format=json"
    try:
        r = requests.get(url, timeout=timeout)
        return r.status_code == 200
    except requests.RequestException:
        print(f"WARNING: URL {url} does not exist. \n")
        return False


def getCitationFromBioContainers(biocontainers_data) -> list:
    """
    Get DOIs from the biocontainers data.
    """
    res = []
    if (
        "identifiers" in biocontainers_data
        and len(biocontainers_data["identifiers"]) > 0
    ):
        for id in biocontainers_data["identifiers"]:
            if isinstance(id, str) and id.lower().startswith("doi:"):
                res.append(id)
            elif isinstance(id, str) and not id.lower().startswith("doi:"):
                continue
            ## Fixing error from yaml where there's an extra space (ex. package spectra-cluster-cli)
            ## Fixing error from yaml where doi value is null (case porechop)
            elif isinstance(id, dict) and "doi" in id and isinstance(id["doi"], str):
                id = "doi:" + id["doi"]
                res.append(id)
            elif isinstance(id, dict) and "doi" not in id:
                continue
            else:
                print(f"WARNING: identifier is not a string: {id}")
                continue
    if len(res) > 0:
        return res
    return None


def rdfize(data) -> Graph:
    prefix = """
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix schema: <http://schema.org/> .
@prefix biotools: <https://bio.tools/> .
@prefix biocontainers: <https://biocontainers.pro/tools/> .
"""

    triples = ""

    biotools_id = getBiotoolsIdFromBioContainers(data)

    # if biotools_id:
    #     biotools_name = biotools_id.lower().split("biotools:", 1)[-1]
    #     api_url = f"https://bio.tools/api/tool/{biotools_name}/?format=json"
    #     print(api_url)
    #     if not urlExists(api_url):
    #         print(f"WARNING: biotools ID {biotools_id} does not exist in bio.tools. Biotools identifier will be skipped. \n")
    #         biotools_id = None

    dois = getCitationFromBioContainers(data)

    try:
        if "name" in data:
            package_uri = f"biocontainers:{data['name']}"
            triples += f"{package_uri} rdf:type schema:SoftwareApplication .\n"
            # triples += f"{package_uri} rdf:type schema:SoftwareSourceCode .\n"

            ## Minimum
            triples += f'{package_uri} schema:conformsTo "https://bioschemas.org/profiles/ComputationalTool/1.0-RELEASE" .\n'

            if "description" in data:
                triples += (
                    f"{package_uri} schema:description "
                    + json.dumps(data["description"])
                    + " .\n"
                )

            triples += f'{package_uri} schema:name "{data["name"]}" .\n'

            if "home_url" in data and data["home_url"] != "Not available":
                triples += f'{package_uri} schema:url "{data["home_url"]}" .\n'

            ## Recommended

            # applicationCategory

            # applicationSubCategory

            # author

            if dois:
                for doi in dois:
                    triples += f'{package_uri} schema:citation "{doi}" .\n'

            # featureList

            if "license" in data:
                # triples += f'{package_uri} schema:license "{data["license"]}" .\n'
                triples += (
                    f"{package_uri} schema:license "
                    + json.dumps(data["license"])
                    + " .\n"
                )

            # softwareVersion

            ## Optional

            # applicationSuite
            # codeRepository
            # contributor
            # discussionUrl
            # downloadUrl
            # funder
            # hasPart

            if biotools_id:
                triples += f"{package_uri} schema:identifier {biotools_id} .\n"
                # triples += f'{package_uri} schema:isBasedOn "{biotools_id}" .\n'

            # input
            # isAccessibleForFree
            # isBasedOn
            # isPartOf

            if "keywords" in data:
                for keyword in data["keywords"]:
                    triples += f'{package_uri} schema:keywords "{keyword}" .\n'

            # operatingSystem
            # output
            # programmingLanguage

            # provider
            triples += f"{package_uri} schema:provider <https://biocontainers.pro> .\n"
            triples += '<https://biocontainers.pro> schema:type "Organization" .\n'

            # softwareAddOn
            # softwareHelp
            # thumbnailUrl

            g = Graph()
            g.parse(data=prefix + "\n" + triples, format="turtle")
            return g

    except Exception as e:
        print("PARSING ERROR for:")
        print(prefix + "\n" + triples)
        print(e)


def get_biocontainers_files_in_repo():
    tools = []
    tools.extend(glob.glob("../../content/data/*/*.biocontainers.yaml"))
    return tools


def process_tools_by_id(rdf_graph, id="SPROUT"):
    """
    Go through all biocontainers entries and produce an RDF graph representation (BioSchemas / TTL).
    """
    tool_files = get_biocontainers_files_in_repo()

    for tool_file in tool_files:
        tool_name = os.path.basename(tool_file).split(".")[0]
        tool_id = Path(tool_file).stem

        if id == tool_name:
            path = Path(tool_file)
            tool = yaml.safe_load(path.read_text(encoding="utf-8"))

            tool_id = None
            if "name" in tool:
                tool_id = tool["name"]

            if tool_id is None:
                print(
                    f"WARNING: no biocontainers id found in {tool_file}, using file basename instead."
                )
                tool_id = tool_name

            ## generate TTL file
            temp_graph = rdfize(tool)

            if temp_graph:
                rdf_graph += temp_graph
            else:
                tool_warnings.append(tool_id)

    return rdf_graph


def clean():
    for data_file in glob.glob(r"../../content/data/*/*.biocontainers.jsonld"):
        print(f"removing file {data_file}")
        os.remove(data_file)
    for data_file in glob.glob(r"../../content/data/*/*.biocontainers.ttl"):
        print(f"removing file {data_file}")
        os.remove(data_file)


def process_tools(rdf_graph):
    """
    Go through all biocontainers entries and produce an RDF graph representation (BioSchemas / TTL).
    """
    tool_files = get_biocontainers_files_in_repo()
    for tool_file in tool_files:
        print(f"processing {tool_file}")
        path = Path(tool_file)
        tool = yaml.safe_load(path.read_text(encoding="utf-8"))

        tool_id = tool["name"]
        tpe_id = tool_id.lower()
        directory = os.path.join("..", "..", "content", "data", tpe_id)

        if not os.path.exists(directory):
            print(f"WARNING: Directory {directory} does not exist for {tool_id}!")
            continue

        ## generate bioconda TTL file

        temp_graph = rdfize(tool)

        if temp_graph:
            rdf_graph += temp_graph
        else:
            tool_warnings.append(tool_id)

    return rdf_graph


def generate_dump(directory):
    """
    Produce an single RDF file for all imported tools.
    """
    rdf_graph = Graph()

    # process_tools_by_id(rdf_graph, "ucsc-bigwigcat")
    process_tools(rdf_graph)
    rdf_graph.serialize(
        format="turtle", destination=os.path.join(directory, "biocontainers-dump.ttl")
    )

    show_stats(rdf_graph)


def show_stats(rdf_graph):
    """
    Display Bioschemas classes and properties counts.
    """

    ### display used classes
    classes_counts = """
    SELECT ?c (count(?c) as ?count) WHERE {
        ?s rdf:type ?c .
    }
    GROUP BY ?c
    ORDER BY DESC(?count)
    """

    res = rdf_graph.query(classes_counts)
    print()
    print("Used classes")
    print(tabulate(res))

    ### display used properties
    property_counts = """
    SELECT ?p (count(?p) as ?count) WHERE {
        ?s ?p ?o .
    }
    GROUP BY ?p
    ORDER BY DESC(?count)
    """

    res = rdf_graph.query(property_counts)
    print()
    print("Used properties")
    print(tabulate(res))


if __name__ == "__main__":
    tool_warnings = []
    directory = "../../content/datasets"

    generate_dump(directory)

    for tool_id in tool_warnings:
        print(f"WARNING: No graph generated for tool {tool_id}: formatting error.")

    print(
        f"{len(tool_warnings)} tools could not be processed due to formatting errors."
    )

    # clean()
    # process_tools()
    # tool = "bam2fasta"

    # process_tools_by_id(tool)
