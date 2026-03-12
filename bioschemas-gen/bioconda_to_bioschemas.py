import os
import glob
import yaml
from pathlib import Path
from rdflib import Graph


def getBiotoolsId(bioconda_data) -> str:
    """
    Get the bio.tools ID from the bioconda data.
    """
    if "extra" in bioconda_data.keys():
        if "identifiers" in bioconda_data["extra"].keys():
            for id in bioconda_data["extra"]["identifiers"]:
                if id.lower().startswith("biotools:"):
                    return id
    return None


def getCitation(bioconda_data) -> list:
    """
    Get DOIs from the bioconda data.
    """
    res = []
    if "extra" in bioconda_data.keys():
        if "identifiers" in bioconda_data["extra"].keys():
            for id in bioconda_data["extra"]["identifiers"]:
                if id.lower().startswith("doi:"):
                    res.append(id)
    return res


def getMaintainers(bioconda_data) -> list:
    """
    Get Maintainers from the bioconda data.
    """
    res = []
    if "extra" in bioconda_data.keys():
        if "recipe-maintainers" in bioconda_data["extra"].keys():
            for id in bioconda_data["extra"]["recipe-maintainers"]:
                res.append(id)
    return res


def rdfize(data) -> Graph:
    prefix = """
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix schema: <http://schema.org/> .
@prefix spdx: <http://spdx.org/rdf/terms/> .
@prefix biotools: <https://bio.tools/> .
@prefix bioconda: <https://bioconda.github.io/recipes/> .
"""

    triples = ""

    name = None
    desc = None
    license = None
    doc_url = None
    home = None
    version = None
    download_url = []

    if "about" in data.keys():
        if "summary" in data["about"].keys():
            desc = data["about"]["summary"]
        if "license" in data["about"].keys():
            license = data["about"]["license"]
        if "doc_url" in data["about"].keys():
            doc_url = data["about"]["doc_url"]
        if "home" in data["about"].keys():
            home = data["about"]["home"]

    if "package" in data.keys():
        if "name" in data["package"].keys():
            name = data["package"]["name"]
        if "version" in data["package"].keys():
            version = data["package"]["version"]

    if "source" in data.keys():
        if isinstance(data["source"], list):
            for source in data["source"]:
                if not isinstance(source, dict):
                    print(f"WARNING: source is not a dict: {source}")
                    continue
                if "url" in source.keys():
                    download_url.append(source["url"])
        else:
            if not isinstance(data["source"], dict):
                print(f"WARNING: source is not a dict: {data['source']}")
                return Graph()
            if "url" in data["source"].keys():
                download_url.append(data["source"]["url"])

    biotools_id = getBiotoolsId(data)
    dois = getCitation(data)

    try:
        if name:
            package_uri = f"bioconda:{name}"
            triples += f"{package_uri} rdf:type schema:SoftwareApplication .\n"
            triples += f'{package_uri} schema:name "{name}" .\n'
            if desc:
                triples += f'{package_uri} schema:description "{desc}" .\n'
            if license:
                triples += f'{package_uri} schema:license "{license}" .\n'
            if biotools_id:
                triples += f"{package_uri} spdx:builtFrom {biotools_id} .\n"
                triples += f"{package_uri} schema:identifier {biotools_id} .\n"
            if doc_url:
                triples += f'{package_uri} schema:softwareHelp "{doc_url}" .\n'
            if home:
                triples += f'{package_uri} schema:url "{home}" .\n'
            if version:
                triples += f'{package_uri} schema:softwareVersion "{version}" .\n'

            # process DOIs
            for doi in dois:
                triples += f'{package_uri} schema:citation "{doi}" .\n'

            for maintainer in getMaintainers(data):
                # triples += (
                #     f"{package_uri} schema:author <https://github.com/{maintainer}> .\n"
                # )
                # triples += f"{package_uri} schema:maintainer <https://github.com/{maintainer}> .\n"
                triples += f'{package_uri} schema:author "{maintainer}" .\n'
                triples += f'{package_uri} schema:maintainer "{maintainer}" .\n'

            for url in download_url:
                triples += f'{package_uri} schema:downloadUrl "{url}" .\n'

            g = Graph()
            g.parse(data=prefix + "\n" + triples, format="turtle")
            # print(g.serialize(format="turtle"))
            # serialize in compact json ld syntax
            # print(g.serialize(format='json-ld'))
        return g

    except Exception as e:
        print("PARSING ERROR for:")
        print(prefix + "\n" + triples)
        print(e)


def get_biotools_files_in_repo():
    tools = []
    for data_file in glob.glob("../../content/data/*/bioconda_*.yaml"):
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

            # print(tool_file)
            # print(json.dumps(tool, indent=2))
            tool_id = None
            if "package" in tool.keys():
                if "name" in tool["package"].keys():
                    tool_id = tool["package"]["name"]

            if tool_id is None:
                print(f"WARNING: no tool id found for {tool_file}!")
                continue
            tpe_id = tool_id.lower()
            directory = os.path.join("..", "..", "content", "data", tpe_id)

            ## generate bioconda JSON-LD and TTL files
            temp_graph = rdfize(tool)
            if temp_graph and os.path.exists(directory):
                temp_graph.serialize(
                    format="json-ld",
                    auto_compact=True,
                    destination=os.path.join(directory, tpe_id + ".bioconda.jsonld"),
                )
                temp_graph.serialize(
                    format="turtle",
                    destination=os.path.join(directory, tpe_id + ".bioconda.ttl"),
                )


def clean():
    for data_file in glob.glob(r"../../content/data/*/*.bioconda.jsonld"):
        print(f"removing file {data_file}")
        os.remove(data_file)
    for data_file in glob.glob(r"../../content/data/*/*.bioconda.ttl"):
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
        tool_id = None
        if "package" in tool.keys():
            if "name" in tool["package"].keys():
                tool_id = tool["package"]["name"]

        if tool_id is None:
            print(f"WARNING: no tool id found for {tool_file}!")
            continue

        tpe_id = tool_id.lower()
        directory = os.path.join("..", "..", "content", "data", tpe_id)

        if not os.path.exists(directory):
            print(f"WARNING: Directory {directory} does not exist for {tool_id}!")
            continue

        ## generate bioconda JSON-LD and TTL files
        temp_graph = rdfize(tool)
        if temp_graph and os.path.exists(directory):
            temp_graph.serialize(
                format="json-ld",
                auto_compact=True,
                destination=os.path.join(directory, tpe_id + ".bioconda.jsonld"),
            )
            temp_graph.serialize(
                format="turtle",
                destination=os.path.join(directory, tpe_id + ".bioconda.ttl"),
            )


if __name__ == "__main__":
    clean()
    process_tools()
    # process_tools_by_id("macsyfinder")
