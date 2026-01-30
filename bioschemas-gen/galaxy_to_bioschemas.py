import os
import glob
import json
from pathlib import Path
from rdflib import Graph
from rdflib import ConjunctiveGraph

edam_version = 'https://github.com/edamontology/edamontology/raw/main/EDAM_dev.owl'

kg = ConjunctiveGraph()
kg.parse(edam_version, format='xml')

def getEdamUrisFromLabels(edam_labels) -> list :
  """
  Get EDAM URIs from EDAM labels.
  """

  res = []

  for lab in edam_labels:
    query="""
    PREFIX edam: <http://edamontology.org/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

    SELECT ?label ?entity WHERE {
        ?entity rdfs:label '%s' .
    }
    """%(lab)

    q = kg.query(query)
    for r in q:
        # uri = r['entity']
        uri = r['entity'].rsplit('/', 1)[-1]
        res.append(f'{uri}')

  return res

def rdfize(data) -> Graph:
    prefix = """
    @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    @prefix schema: <http://schema.org/> .
    @prefix spdx: <http://spdx.org/rdf/terms/> .
    @prefix biotools: <https://bio.tools/> .
    @prefix bioconda: <https://bioconda.github.io/recipes/> .
    @prefix galaxy: <https://github.com/galaxyproject/tools-iuc/tree/master/tools/> .
    @prefix edam: <http://edamontology.org/> .
    """

    triples = ""

    name = None # OK
    desc = None # OK
    url = None # OK
    #owner = None # Suite_owner -> author, contributor, primaryContact?
    version = None # OK

    biotools_id = None # OK
    #biii_id = None # biii_ID
    bioconda_id = None # OK

    edam_operations = [] # OK
    edam_topics = [] # OK
    keywords = [] # OK
    #help = [] # Related_Tutorials -> many many GTN links
    #workflows = [] # Related_Workflows : 'link' (ex. many WfHub or usegalaxy refs)

    #biotools_name = None
    #biotools_desc = None

    #Tool_ids = [] # see for ex. bedtools suite ++
    #Suite_source

    if "Suite_ID" in data.keys():
        name = data["Suite_ID"]
    if "Description" in data.keys():
        desc = data["Description"]
    if "Homepage" in data.keys():
        url = data["Homepage"]
    if "Suite_version" in data.keys():
        version = data["Suite_version"]
    if "bio.tool_ID" in data.keys():
        biotools_id = "biotools:" + data["bio.tool_ID"]
    if "Suite_conda_package" in data.keys() and data["Suite_conda_package"]:
        bioconda_id = "bioconda:" + data["Suite_conda_package"].strip() # see pharokka package bioconda ID

    if "EDAM_operations" in data.keys():
        #for operation in data["EDAM_operations"]:
            #op = getEdamUrisFromSingleLabel(operation)
        ope = getEdamUrisFromLabels(data["EDAM_operations"])
        for o in ope:
            edam_operations.append("edam:" + o)

    if "EDAM_topics" in data.keys():
        top = getEdamUrisFromLabels(data["EDAM_topics"])
        for t in top:
            edam_topics.append("edam:" + t)

    if "ToolShed_categories" in data.keys():
        for keyword in data["ToolShed_categories"]:
            keywords.append(keyword)

    #if "bio.tool_description" in data.keys():
        #biotools_desc = data["bio.tool_description"]
    #if "bio.tool_name" in data.keys():
        #name = data["bio.tool_name"]

    try:
        if name:
            package_uri = f'galaxy:{name}'
            triples += f'{package_uri} rdf:type schema:SoftwareApplication .\n'
            triples += f'{package_uri} schema:name "{name}" .\n'

            if desc:
                triples += f'''{package_uri} schema:description """{desc}""" .\n''' # see package infernal for ex. of special characters issue
            if url:
                triples += f'{package_uri} schema:url "{url}" .\n'
            if version:
                triples += f'{package_uri} schema:softwareVersion "{version}" .\n'

            if biotools_id:
                triples += f'{package_uri} spdx:builtFrom "{biotools_id}" .\n'
                triples += f'{package_uri} schema:identifier "{biotools_id}" .\n'
            if bioconda_id:
                triples += f'{package_uri} schema:identifier "{bioconda_id}" .\n'

            for ope in edam_operations:
                triples += f'{package_uri} schema:featureList {ope} .\n'
            for top in edam_topics:
                triples += f'{package_uri} schema:applicationSubCategory "{top}" .\n'
            for key in keywords:
                triples += f'{package_uri} schema:keywords "{key}" .\n'

            g = Graph()
            g.parse(data=prefix+"\n"+triples, format="turtle")
            print(g.serialize(format='turtle'))
            return g

    except Exception as e:
        print("PARSING ERROR for:")
        print(prefix+"\n"+triples)
        raise(e)

def get_galaxy_files_in_repo():
    tools = []
    for data_file in glob.glob("../../content/data/*/*.galaxy.json"):
        tools.append(data_file)
    return tools


def process_tools_by_id(id="SPROUT"):
    """
    Go through all galaxy entries and produce an RDF graph representation (BioSchemas / JSON-LD).
    """
    tool_files = get_galaxy_files_in_repo()

    for tool_file in tool_files:
        if id in tool_file:
            path = Path(tool_file)
        #     #tool = yaml.safe_load(path.read_text(encoding="utf-8"))
            tool = json.loads(path.read_text(encoding="utf-8"))

            tool_id = None
            if "Suite_ID" in tool.keys():
                tool_id = tool["Suite_ID"]

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
                    destination=os.path.join(directory, tpe_id + ".galaxy.jsonld"),
                )
                temp_graph.serialize(
                    format="turtle",
                    destination=os.path.join(directory, tpe_id + ".galaxy.ttl"),
                )


def clean():
    for data_file in glob.glob(r"../../content/data/*/*.galaxy.jsonld"):
        print(f"removing file {data_file}")
        os.remove(data_file)
    for data_file in glob.glob(r"../../content/data/*/*.galaxy.ttl"):
        print(f"removing file {data_file}")
        os.remove(data_file)


def process_tools():
    """
    Go through all galaxy entries and produce an RDF graph representation (BioSchemas / JSON-LD).
    """
    tool_files = get_galaxy_files_in_repo()
    for tool_file in tool_files:
        path = Path(tool_file)
        # tool = yaml.safe_load(path.read_text(encoding="utf-8"))
        tool = json.loads(path.read_text(encoding="utf-8"))

        tool_id = None

        if "Suite_ID" in tool.keys():
            tool_id = tool["Suite_ID"]

        if tool_id is None:
            print(f"WARNING: no tool id found for {tool_file}!")
            continue

        tpe_id = tool_id.lower()
        directory = os.path.join("..", "..", "content", "data", tpe_id)

        if not os.path.exists(directory):
            print(f"WARNING: Directory {directory} does not exist for {tool_id}!")
            continue

        ## generate galaxy JSON-LD and TTL files
        temp_graph = rdfize(tool)
        if temp_graph and os.path.exists(directory):
            temp_graph.serialize(
                format="json-ld",
                auto_compact=True,
                destination=os.path.join(directory, tpe_id + ".galaxy.jsonld"),
            )
            temp_graph.serialize(
                format="turtle",
                destination=os.path.join(directory, tpe_id + ".galaxy.ttl"),
            )


if __name__ == "__main__":
    clean()
    process_tools()
    # process_tools_by_id("limma")
