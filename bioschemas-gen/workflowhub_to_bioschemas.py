import os
import glob
import json
import yaml
from pathlib import Path
from rdflib import Graph

# def getBiotoolsId(bioconda_data) -> str:
#     """
#     Get the bio.tools ID from the bioconda data.
#     """
#     if "extra" in bioconda_data.keys():
#         if "identifiers" in bioconda_data["extra"].keys():
#             for id in bioconda_data["extra"]["identifiers"]:
#                 if id.lower().startswith("biotools:"):
#                     return id
#     return None

# def urlExists(url, timeout=5):
#     #"""Check if a biotools ID exists using the bio.tools JSON API (not the front-end URL)."""
#     """Check if a URL exists """
#     #id = biotools_id.lower().split("biotools:", 1)[-1]
#     #print(id)
#     #api_url = f"https://bio.tools/api/tool/{id}/?format=json"
#     try:
#         r = requests.get(url, timeout=timeout)
#         return r.status_code == 200
#     except requests.RequestException:
#         print(f"WARNING: URL {url} does not exist. \n") 
#         return False

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

def rdfize(data) -> Graph:
    prefix = """
@prefix biotools: <https://bio.tools/> .
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix edam: <http://edamontology.org/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix schema: <http://schema.org/> .
@prefix workflowhub: <https://workflowhub.eu/workflows/> .
"""

    triples = ""

    workflow_id = None 
    if "link" in data.keys():
        workflow_id = data["link"]

    try:
        if workflow_id:
            package_uri = f'<{workflow_id}>'
            triples += f'{package_uri} rdf:type schema:ComputationalWorkflow .\n'
            triples += f'{package_uri} dcterms:conformsTo "https://bioschemas.org/profiles/ComputationalWorkflow/1.0-RELEASE" .\n'
        
        if "description" in data.keys(): ## special characters, ex. in workflow 104
                triples += (
                    f"{package_uri} schema:description "
                    + json.dumps(data["description"])
                    + " .\n"
                )
            
        if "name" in data.keys():
            triples += f'{package_uri} schema:name "{data["name"]}" .\n'
        if "link" in data.keys():
            triples += f'{package_uri} schema:url <{data["link"]}> .\n'

        ## Recommended
        if "creators" in data.keys():
            for author in data["creators"]:
                triples += f'{package_uri} schema:author "{author}" .\n'
        if "doi" in data.keys():
            triples += f'{package_uri} schema:publication "{data["doi"]}" .\n'
        if "license" in data.keys():
            triples += f'{package_uri} schema:license "{data["license"]}" .\n'
        if "latest_version" in data.keys():
            triples += f'{package_uri} schema:softwareVersion "{data["latest_version"]}" .\n'
        if "edam_operation" in data.keys():
            operations = getEdamUrisFromLabels(data["edam_operation"])
            for operation in operations:
                triples += f'{package_uri} schema:featureList edam:{operation} .\n'
        if "edam_topic" in data.keys():
            topics = getEdamUrisFromLabels(data["edam_topic"])
            for topic in topics:
                triples += f'{package_uri} schema:applicationSubCategory edam:{topic} .\n'

        ## Optional
        if "create_time" in data.keys():
            triples += f'{package_uri} schema:dateCreated "{data["create_time"]}" .\n'

        if "update_time" in data.keys():
            triples += f'{package_uri} schema:dateModified "{data["update_time"]}" .\n'

        if "id" in data.keys():
            triples += f'{package_uri} schema:identifier "{data["id"]}" .\n'

        if "tags" in data.keys():
            for tag in data["tags"]:
                triples += f'{package_uri} schema:keywords "{tag}" .\n'

        if "mapped_tools" in data.keys():
            for tool in data["mapped_tools"]:
                triples += f'{package_uri} schema:hasPart "{tool}" .\n'


        g = Graph()
        g.parse(data=prefix + "\n" + triples, format="turtle")
        return g

    except Exception as e:
        print("PARSING ERROR for:")
        print(prefix + "\n" + triples)
        print(e)


def get_workflowhub_files_in_repo():
    workflows = []
    for data_file in glob.glob("../../content/imports/workflowhub/*.workflowhub.json"):
        workflows.append(data_file)
    return workflows

def process_workflows_by_id(id="SPROUT"):
    """
    Go through all workflowhub entries and produce an RDF graph representation (BioSchemas / JSON-LD).
    """
    workflow_files = get_workflowhub_files_in_repo()

    for workflow_file in workflow_files:

        workflow_number = os.path.basename(workflow_file)
        workflow_number = workflow_number.removesuffix(".workflowhub.json")

        if id == workflow_number:
            path = Path(workflow_file)
            workflow = yaml.safe_load(path.read_text(encoding="utf-8"))

            workflow_id = None
            if "id" in workflow.keys():
                workflow_id = workflow["id"]

            if workflow_id is None:
                print(f"WARNING: no workflow id found for {workflow_file}!")
                continue

            directory = os.path.join("..", "..", "content", "imports", "workflowhub")

            ## generate workflowhub JSON-LD and TTL files
            temp_graph = rdfize(workflow)
            if temp_graph and os.path.exists(directory):
                temp_graph.serialize(
                    format="json-ld",
                    auto_compact=True,
                    destination=os.path.join(directory, workflow_id + ".workflowhub.jsonld"),
                )
                temp_graph.serialize(
                    format="turtle",
                    destination=os.path.join(directory, workflow_id + ".workflowhub.ttl"),
                )
                print(temp_graph.serialize(format="turtle"))


def clean():
    for data_file in glob.glob(r"../../content/imports/workflowhub/*.workflowhub.jsonld"):
        print(f"removing file {data_file}")
        os.remove(data_file)
    for data_file in glob.glob(r"../../content/imports/workflowhub/*.workflowhub.ttl"):
        print(f"removing file {data_file}")
        os.remove(data_file)


def process_workflows():
    """
    Go through all workflowhub entries and produce an RDF graph representation (BioSchemas / JSON-LD).
    """
    workflow_files = get_workflowhub_files_in_repo()

    for workflow_file in workflow_files:
        path = Path(workflow_file)
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))

        #print(workflow_file)
        workflow_id = None
        if "id" in workflow.keys():
            workflow_id = workflow["id"]

        if workflow_id is None:
            print(f"WARNING: no workflow id found for {workflow_file}!")
            continue

        directory = os.path.join("..", "..", "content", "imports", "workflowhub")

        if not os.path.exists(directory):
            print(f"WARNING: Directory {directory} does not exist for {workflow_id}!")
            continue

        ## generate workflowhub JSON-LD and TTL files
        temp_graph = rdfize(workflow)
        if temp_graph and os.path.exists(directory):
            temp_graph.serialize(
                format="json-ld",
                auto_compact=True,
                destination=os.path.join(directory, workflow_id + ".workflowhub.jsonld"),
            )
            temp_graph.serialize(
                format="turtle",
                destination=os.path.join(directory, workflow_id + ".workflowhub.ttl"),
            )
            print(temp_graph.serialize(format="turtle"))


if __name__ == "__main__":
    clean()

    edam_version = "https://github.com/edamontology/edamontology/raw/main/EDAM_dev.owl"
    edam_kg = Graph()
    edam_kg.parse(edam_version, format="xml")

    process_workflows()
    #process_workflows_by_id("2174")
