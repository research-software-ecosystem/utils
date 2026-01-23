import os
import glob
import yaml
from pathlib import Path
from rdflib import Graph


def getBiotoolsIdFromDebian(debian_data) -> str:
    """
    Get the bio.tools ID from the debian data.
    """
    if 'registries' in debian_data.keys():
        for r in debian_data['registries']:
            if 'name' in r.keys() and r['name'] == 'bio.tools':
                return r['entry']
    return None

def getCitationFromDebian(debian_data) -> list:
    """
    Get DOIs from the debian data.
    """
    res = []
    if 'bib' in debian_data.keys():
        for entry in debian_data['bib']:
            if 'key' in entry.keys() and 'value' in entry.keys():
                res.append(entry['key'] + ":" + entry['value'])
    return res

def getDescriptionFromDebian(debian_data) -> list:
  res = []
  if 'descr' in debian_data.keys():
    for entry in debian_data['descr']:
      if 'language' in entry.keys() and 'description' in entry.keys() and entry['language'] == "en":
        return entry['description']
      # elif 'language' in entry.keys() and 'long_description' in entry.keys() and entry['language'] == "en":
        # return entry['long_description']
  return None

def rdfize(data) -> Graph:
    prefix = """
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix schema: <http://schema.org/> .
@prefix spdx: <http://spdx.org/rdf/terms/> .
@prefix biotools: <https://bio.tools/> .
@prefix debianmed: <https://salsa.debian.org/med-team/> .
"""

    triples = ""

    biotools_id = getBiotoolsIdFromDebian(data)
    dois = getCitationFromDebian(data)
    description = getDescriptionFromDebian(data)

    try:
        if "package" in data.keys() :
            package_uri = f"debianmed:{data["package"]}"
            triples += f'{package_uri} rdf:type schema:SoftwareApplication .\n'
            triples += f'{package_uri} schema:name "{data["package"]}" .\n'
            # if "description" in data.keys() :
            #   triples += f'{package_uri} schema:description "{data["description"]}" .\n'
        if "license" in data.keys() :
            triples += f'{package_uri} schema:license "{data["license"]}" .\n'
        if "version" in data.keys() :
            triples += f'{package_uri} schema:softwareVersion "{data["version"]}" .\n'
        if biotools_id :
            triples += f'{package_uri} spdx:builtFrom "{biotools_id}" .\n'
        if description :
            triples += f'{package_uri} schema:description "{description}" .\n'
        if "homepage" in data.keys():
            triples += f'{package_uri} schema:url "{data["homepage"]}" .\n'
        if "tags" in data.keys():
            for kw in data["tags"]:
                if 'tag' in kw.keys():
                    triples += f'{package_uri} schema:keywords "{kw["tag"]}" .\n'
        # process DOIs
        for doi in dois:
            triples += f'{package_uri} schema:citation "{doi}" .\n'

        # process identifiers
        if 'registries' in data.keys():
            for e in data['registries']:
                if 'name' in e.keys() and "entry" in e.keys():
                    id = f"{e['name'].lower()}:{e['entry']}"
                    triples += f'{package_uri} schema:identifier "{id}" .\n'

            g = Graph()
            g.parse(data=prefix+"\n"+triples, format="turtle")
            print(g.serialize(format='turtle'))
        return g

    except Exception as e:
        print("PARSING ERROR for:")
        print(prefix+"\n"+triples)
        raise(e)

def get_biotools_files_in_repo():
    tools = []
    for data_file in glob.glob("../../content/data/*/*.debian.yaml"):
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
            tool_id = tool["package"]
            tpe_id = tool_id.lower()
            directory = os.path.join("..", "..", "content", "data", tpe_id)

            ## generate debian JSON-LD and TTL files
            temp_graph = rdfize(tool)
            if temp_graph and os.path.exists(directory):
                temp_graph.serialize(
                    format="json-ld",
                    auto_compact=True,
                    destination=os.path.join(
                        directory, tpe_id + ".debian.jsonld"
                    ),
                )
                temp_graph.serialize(
                    format="turtle",
                    destination=os.path.join(directory, tpe_id + ".debian.ttl"),
                )

def clean():
    for data_file in glob.glob(r"../../content/data/*/*.debian.jsonld"):
        print(f"removing file {data_file}")
        os.remove(data_file)
    for data_file in glob.glob(r"../../content/data/*/*.debian.ttl"):
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
        tool_id = tool["package"]
        tpe_id = tool_id.lower()
        directory = os.path.join("..", "..", "content", "data", tpe_id)

        if not os.path.exists(directory):
            print(f"WARNING: Directory {directory} does not exist for {tool_id}!")
            continue

        ## generate debian JSON-LD and TTL files
        temp_graph = rdfize(tool)
        if temp_graph and os.path.exists(directory):
            temp_graph.serialize(
                format="json-ld",
                auto_compact=True,
                destination=os.path.join(directory, tpe_id + ".debian.jsonld"),
            )
            temp_graph.serialize(
                format="turtle",
                destination=os.path.join(directory, tpe_id + ".debian.ttl"),
            )


if __name__ == "__main__":
    clean()
    process_tools()
    # process_tools_by_id("macsyfinder")
