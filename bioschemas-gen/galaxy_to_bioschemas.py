import os
import glob
import json
from pathlib import Path
from rdflib import Graph
import pandas as pd
from tabulate import tabulate


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
    """ %(lab)

        q = edam_kg.query(query)
        for r in q:
            # uri = r['entity']
            uri = r["entity"].rsplit("/", 1)[-1]
            res.append(f"{uri}")

    return res

def getBiotoolsIdFromGalaxy(tool_data) -> str:
    """
    Get the bio.tools ID from the galaxy data.
    """
    if "bio.tool_ID" in tool_data.keys() and tool_data["bio.tool_ID"]:
        biotools_id = "biotools:" + tool_data["bio.tool_ID"]
        # biotools_id = tool_data["bio.tool_ID"]
        return biotools_id
    return None



def getGalaxyServers(tool_data) -> list:
    """
    Get Galaxy servers list where given tool is available.
    """

    res = []
    keystart = "Number_of_tools_on_"

    for k in tool_data.keys():
        if k.startswith(keystart) and tool_data[k] > 0:
            server = k.split(keystart)[-1]
            if server in server_dict.keys():
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
    @prefix biii: <https://biii.eu/> .
    """

    triples = ""

    ## Minimum
    description = None
    name = None
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
    biii_id = None # identifier
    bioconda_id = None # identifier
    galaxywf_ids = [] # isPartOf
    keywords = []

    ## Minimum
    if "Description" in data.keys():
        description = data["Description"]
    if "Suite_ID" in data.keys():
        name = data["Suite_ID"]
    if "Suite_source" in data.keys():
        url = data["Suite_source"]

    ## Recommended  
    if "EDAM_topics" in data.keys():
        top = getEdamUrisFromLabels(data["EDAM_topics"]) ## Only labels are available atm, should be URis, see https://github.com/galaxyproject/galaxy_codex/issues/709
        for t in top:
            edam_topics.append("edam:" + t)  
    if "EDAM_operations" in data.keys(): ## Only labels are available atm, should be URis, see https://github.com/galaxyproject/galaxy_codex/issues/709
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
    if "bio.tool_ID" in data.keys() and data["bio.tool_ID"]:
        biotools_id = "biotools:" + data["bio.tool_ID"]
    if "biii_ID" in data.keys() and data["biii_ID"]:
        biii_id = "biii:" + data["biii_ID"]
    if "Suite_conda_package" in data.keys() and data["Suite_conda_package"]:
        bioconda_id = (
            "bioconda:" + data["Suite_conda_package"].strip()
        )  # see pharokka package bioconda ID -> exception

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

            ## Minimum

            # dc:conformsTo
            triples += f'{package_uri} schema:conformsTo "https://bioschemas.org/profiles/ComputationalTool/1.0-RELEASE" .\n'
            
            # description
            if description:
                triples += f'''{package_uri} schema:description """{description}""" .\n'''  # see package infernal for ex. of special characters issue
            
            # name
            triples += f'{package_uri} schema:name "{name}" .\n'

            # url
            if url:
                triples += f'{package_uri} schema:url <{url}> .\n'

            ## Recommended

            # applicationCategory

            # applicationSubCategory
            for top in edam_topics:
                triples += f"{package_uri} schema:applicationSubCategory {top} .\n"

            # author

            # citation

            # featureList
            for ope in edam_operations:
                triples += f"{package_uri} schema:featureList {ope} .\n"

            # license

            # softwareVersion
            if version:
                triples += f'{package_uri} schema:softwareVersion "{version}" .\n'

            ## Optional

            # applicationSuite

            # codeRepository
            if code_repository:
                triples += f'{package_uri} schema:codeRepository <{code_repository}> .\n'

            # contributor
            # discussionUrl
            # downloadUrl
            # funder

            # hasPart
            # for tid in tool_ids: 
            #   triples += f"{package_uri} schema:hasPart galaxytool:{tid} .\n"  
          
            # identifier
            if biotools_id:
                triples += f"{package_uri} schema:identifier {biotools_id} .\n"
            if bioconda_id:
                triples += f"{package_uri} schema:identifier {bioconda_id} .\n"
            if biii_id:
                triples += f"{package_uri} schema:identifier {biii_id} .\n"

            # input
            # isAccessibleForFree
            # isBasedOn

            # isPartOf
            for galaxywf_id in galaxywf_ids:
                triples += f'{package_uri} schema:isPartOf <{galaxywf_id}> .\n'
                #if galaxywf_id.startswith("https://workflowhub.eu/"):
                    #triples += f'<https://workflowhub.eu/> rdf:type schema:Website .\n'

            for galaxy_server in getGalaxyServers(data):
                triples += f'{package_uri} schema:isPartOf <{galaxy_server}> .\n'
                triples += f'<{galaxy_server}> rdf:type schema:WebSite .\n'
                
            # keywords
            # for server in server_dict.values():
            for key in keywords:
                triples += f'{package_uri} schema:keywords "{key}" .\n'

            # operatingSystem

            # output
            for of in output_format:
                triples += f'{package_uri} schema:encodingFormat "{of}" .\n'
                triples += f'{package_uri} bioschemas:output "{of}" .\n'

            # programmingLanguage

            # provider
            triples += f'{package_uri} schema:provider <https://galaxyproject.org/> .\n'
            triples += f'<https://galaxyproject.org/> schema:type "Organization" .\n'

            # softwareAddOn
            # softwareHelp
            # thumbnailUrl

            ## Other

            if date_created:
                triples += f'{package_uri} schema:dateCreated "{date_created}" .\n'


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


def process_tools_by_id(rdf_graph, id="SPROUT"):
    """
    Go through all galaxy entries and produce an RDF graph representation (BioSchemas / TTL).
    """
    tool_files = get_galaxy_files_in_repo()

    for tool_file in tool_files:
        tool_name = os.path.basename(tool_file)
        tool_name = tool_name.removesuffix(".galaxy.json")

        if id == tool_name:
            path = Path(tool_file)
            tool = json.loads(path.read_text(encoding="utf-8"))

            tool_id = None
            if "Suite_ID" in tool.keys():
                tool_id = tool["Suite_ID"]

            if tool_id is None:
                print(f"WARNING: no tool id found for {tool_file}!")
                continue

            # tpe_id = tool_id.lower()
            # directory = os.path.join("..", "..", "content", "data", tpe_id)

            ## generate graph for specified tool
            temp_graph = rdfize(tool)

            if temp_graph:
                rdf_graph += temp_graph
            else:
                tool_warnings.append(tool_id)

    return rdf_graph


def clean():
    for data_file in glob.glob(r"../../content/data/*/*.galaxy.jsonld"):
        print(f"removing file {data_file}")
        os.remove(data_file)
    for data_file in glob.glob(r"../../content/data/*/*.galaxy.ttl"):
        print(f"removing file {data_file}")
        os.remove(data_file)


def process_tools(rdf_graph):
    """
    Go through all galaxy entries and produce an RDF graph representation (BioSchemas / TTL).
    """
    tool_files = get_galaxy_files_in_repo()

    for tool_file in tool_files:
        print(f"processing {tool_file}")
        tool_name = os.path.basename(tool_file)
        tool_name = tool_name.removeprefix("bioconda_").removesuffix(".yaml")

        path = Path(tool_file)
        tool = json.loads(path.read_text(encoding="utf-8"))

        tool_id = None
        if "package" in tool.keys():
            tool_id = tool["package"]

        if tool_id is None:
            print(f"WARNING: no bioconda id found in {tool_file}, using file basename instead.")
            tool_id = tool_name

        biotools_id = getBiotoolsIdFromGalaxy(tool)
        if biotools_id:
            tpe_id = biotools_id.lower().split("biotools:", 1)[-1]
        else:
            print(f"WARNING: no biotools id found for {tool_file}, using galaxy id to create data directory instead.")
            tpe_id = tool_id                
 
        directory = os.path.join("..", "..", "content", "data", tpe_id)

        if not os.path.exists(directory):
            print(f"WARNING: Directory {directory} does not exist for {tool_id}!")
            continue

        ## generate debian TTL file

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

    # process_tools_by_id(rdf_graph, "bowtie2")
    process_tools(rdf_graph)
    rdf_graph.serialize(format="turtle", destination=os.path.join(directory, "galaxy-dump.ttl"))

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

    edam_version = "https://github.com/edamontology/edamontology/raw/main/EDAM_dev.owl"
    edam_kg = Graph()
    edam_kg.parse(edam_version, format="xml")

    server_table = "https://raw.githubusercontent.com/galaxyproject/galaxy_codex/refs/heads/main/sources/data/available_public_servers.csv"
    df = pd.read_table(server_table)

    server_dict = pd.Series(df.url.values,index=df.name).to_dict()
    server_dict = {k.replace(' ','_'):v for k,v in server_dict.items()}

    tool_warnings = []
    directory = "../../content/datasets"

    generate_dump(directory)

    for tool_id in tool_warnings:
        print(f"WARNING: No graph generated for tool {tool_id}: formatting error.")

    print(f"{len(tool_warnings)} tools could not be processed due to formatting errors.")


    # clean()
    # process_tools()
    #process_tools_by_id("jbrowse_2")
