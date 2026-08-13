import os
import glob
import json
from pathlib import Path
from rdflib import Graph
import pandas as pd



def getEdamUrisFromLabels(edam_labels) -> list:
    """
    Get EDAM URIs from EDAM labels.
    """

    res = []

    for lab in edam_labels:
        query = """
    PREFIX edam: <http://edamontology.org/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

    SELECT ?label ?entity WHERE {
        ?entity rdfs:label '%s' .
    }
    """ % (lab)

        q = kg.query(query)
        for r in q:
            # uri = r['entity']
            uri = r["entity"].rsplit("/", 1)[-1]
            res.append(f"{uri}")

    return res

def getGalaxyServers(tool_data) -> list:
    """
    Get Galaxy servers list where given tool is available.
    """

    res = []
    keystart = "Number_of_tools_on_"

    for k in tool_data.keys():
        if k.startswith(keystart) and tool_data[k] > 0:
            server = k.split(keystart)[-1]
            if server_dict[server]:
                if server not in res:
                    res.append(server_dict[server])
            else:
                print(f"WARNING: Galaxy instance {server} not found in servers list.")

    return res

def rdfize(data) -> Graph:
    prefix = """
    @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    @prefix schema: <http://schema.org/> .
    @prefix biotools: <https://bio.tools/> .
    @prefix bioschemas: <http://bioschemas.org/> .
    @prefix bioconda: <https://github.com/bioconda/bioconda-recipes/tree/master/recipes/> .
    @prefix galaxytool: <https://github.com/galaxyproject/tools-iuc/tree/master/tools/> .
    @prefix workflowhub: <https://workflowhub.eu/workflows/> .
    @prefix edam: <http://edamontology.org/> .
    """

    triples = ""

    ## Mandatory
    name = None
    description = None
    url = None

    ## Recommended
    edam_topics = [] # applicationSubCategory
    edam_operations = [] #featureList
    version = None

    ## Optional
    code_repository = None
    date_created = None
    output_format = [] # encodingFormat, biochemas:output
    tool_ids = []  # hasPart
    biotools_id = None # identifier
    # biii_id = None # identifier
    bioconda_id = None # identifier
    galaxywf_ids = [] # isPartOf
    keywords = []

    ## Mandatory
    if "Suite_ID" in data.keys():
        name = data["Suite_ID"]
    if "Description" in data.keys():
        description = data["Description"]
    if "Suite_source" in data.keys():
        url = data["Suite_source"]

    ## Recommended  
    if "EDAM_topics" in data.keys():
        top = getEdamUrisFromLabels(data["EDAM_topics"])
        for t in top:
            edam_topics.append("edam:" + t)  
    if "EDAM_operations" in data.keys():
        ope = getEdamUrisFromLabels(data["EDAM_operations"])
        for o in ope:
            edam_operations.append("edam:" + o)        
    if "Suite_version" in data.keys():
        version = data["Suite_version"]

    ## Optional  
    if "Homepage" in data.keys():
        code_repository = data["Homepage"]
    if "Suite_first_commit_date" in data.keys():
        date_created = data["Suite_first_commit_date"]
    if "Tool_output_formats" in data.keys():
        for of in data["Tool_output_formats"]:
            output_format.append(of)
    if "Tool_IDs" in data.keys():
        for tid in data["Tool_IDs"]:
            tool_ids.append(tid)
    if "bio.tool_ID" in data.keys():
        biotools_id = "biotools:" + data["bio.tool_ID"]
    if "Suite_conda_package" in data.keys() and data["Suite_conda_package"]:
        bioconda_id = (
            "bioconda:" + data["Suite_conda_package"].strip()
        )  # see pharokka package bioconda ID

    if "Related_Workflows" in data.keys():
        for workflow in data["Related_Workflows"]:
            for wf in workflow.keys():
                if wf == "link":
                    galaxywf_ids.append(workflow[wf])

    if "ToolShed_categories" in data.keys():
        for keyword in data["ToolShed_categories"]:
            keywords.append(keyword)

    try:
        if name:
            ## Mandatory
            package_uri = f"galaxytool:{name}"
            triples += f"{package_uri} rdf:type schema:SoftwareApplication .\n"
            triples += f'{package_uri} schema:name "{name}" .\n'
            if description:
                triples += f'''{package_uri} schema:description """{description}""" .\n'''  # see package infernal for ex. of special characters issue
            if url:
                triples += f'{package_uri} schema:url <{url}> .\n'

            ## Recommended
            for top in edam_topics:
                triples += f"{package_uri} schema:applicationSubCategory {top} .\n"
            for ope in edam_operations:
                triples += f"{package_uri} schema:featureList {ope} .\n"
            if version:
                triples += f'{package_uri} schema:softwareVersion "{version}" .\n'

            ## Optional
            if code_repository:
                triples += f'{package_uri} schema:codeRepository <{code_repository}> .\n'
            if date_created:
                triples += f'{package_uri} schema:dateCreated "{date_created}" .\n'
            for of in output_format:
                triples += f'{package_uri} schema:encodingFormat "{of}" .\n'
                triples += f'{package_uri} bioschemas:output "{of}" .\n'
#            for tid in tool_ids: 
#                triples += f"{package_uri} schema:hasPart galaxytool:{tid} .\n"
            if biotools_id:
                triples += f"{package_uri} schema:identifier {biotools_id} .\n"
            if bioconda_id:
                triples += f"{package_uri} schema:identifier {bioconda_id} .\n"

            for galaxywf_id in galaxywf_ids:
                triples += f'{package_uri} schema:isPartOf <{galaxywf_id}> .\n'

            for galaxy_server in getGalaxyServers(data):
                triples += f'{package_uri} schema:isPartOf <{galaxy_server}> .\n'
                triples += f'<{galaxy_server}> rdf:type schema:WebSite .\n'

            # for server in server_dict.values():
            for key in keywords:
                triples += f'{package_uri} schema:keywords "{key}" .\n'


            g = Graph()
            g.parse(data=prefix + "\n" + triples, format="turtle")
            print(g.serialize(format="turtle"))
            return g

    except Exception as e:
        print("PARSING ERROR for:")
        print(prefix + "\n" + triples)
        raise (e)


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

    edam_version = "https://github.com/edamontology/edamontology/raw/main/EDAM_dev.owl"
    kg = Graph()
    kg.parse(edam_version, format="xml")

    server_table = "https://raw.githubusercontent.com/galaxyproject/galaxy_codex/refs/heads/main/sources/data/available_public_servers.csv"
    df = pd.read_table(server_table)

    server_dict = pd.Series(df.url.values,index=df.name).to_dict()
    server_dict = {k.replace(' ','_'):v for k,v in server_dict.items()}

    clean()
    process_tools()
