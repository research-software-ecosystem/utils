import os
import glob
import json
import yaml
from pathlib import Path
from rdflib import Graph

try:
    from tabulate import tabulate
except ImportError:
    def tabulate(rows, headers=()):
        return "\n".join(" | ".join(str(value) for value in row) for row in rows)

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

        ## Minimum
        
        if "creators" in data.keys():
            for author in data["creators"]:
                triples += f'{package_uri} schema:creator "{author}" .\n' # formatting error for wf 1738, 1739, 1740, 1741 

        if "create_time" in data.keys():
            triples += f'{package_uri} schema:dateCreated "{data["create_time"]}" .\n'

        if "license" in data.keys():
            triples += f'{package_uri} schema:license "{data["license"]}" .\n'
            
        if "name" in data.keys():
            triples += (
                f"{package_uri} schema:name "
                + json.dumps(data["name"])
                + " .\n"
            )

        # programmingLanguage 

        # sdPublisher: "source" or "workflow_class"? i.e. WorkflowHub or Galaxy
    
        if "link" in data.keys():
            triples += f'{package_uri} schema:url <{data["link"]}> .\n'

        if "latest_version" in data.keys():
            triples += f'{package_uri} schema:version "{data["latest_version"]}" .\n'

        ## Recommended

        if "edam_topic" in data.keys():
            for topic in data["edam_topic"]:
                triples += f'{package_uri} schema:applicationSubCategory <{topic}> .\n'

        if "doi" in data.keys():
            triples += f'{package_uri} schema:citation "{data["doi"]}" .\n'

        # contributor: a secondary contributor to the CreativeWork or Event

        # creativeWorkStatus: "active" or "inactive" or "deprecated" or "retired" or "archived"

        if "description" in data.keys():
                triples += (
                    f"{package_uri} schema:description "
                    + json.dumps(data["description"])
                    + " .\n"
                )        

        # documentation: A link to the documentation of the workflow, eg. a GitHub repository or a Zenodo DOI

        if "edam_operation" in data.keys():
            for operation in data["edam_operation"]:
                triples += f'{package_uri} schema:featureList <{operation}> .\n'

        # funding

        if "mapped_tools" in data.keys():
            for tool in data["mapped_tools"]:
                triples += f'{package_uri} schema:hasPart "{tool}" .\n'

        # input
        # isBasedOn

        if "tags" in data.keys():
            for tag in data["tags"]:
                triples += f'{package_uri} schema:keywords "{tag}" .\n'

        # maintainer
        # output
        # producer
        # publisher
        # runtimePlatform
        # sameAs
        # softwareRequirements
        # targetProduct

        ## Optional
 
        if "update_time" in data.keys():
            triples += f'{package_uri} schema:dateModified "{data["update_time"]}" .\n'

        if "id" in data.keys():
            triples += f'{package_uri} schema:identifier "{data["id"]}" .\n'


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

def process_workflows_by_id(rdf_graph, id="SPROUT"):
    """
    Produce an RDF graph representation for a given workflow ID.
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

            ## generate TTL file
            temp_graph = rdfize(workflow)

            if temp_graph:
                rdf_graph += temp_graph
            else:
                wf_warnings.append(workflow_id)

    return rdf_graph

def process_workflows(rdf_graph):
    """
    Go through all workflowhub entries and produce an RDF/Turtle graph representation.
    """
    workflow_files = get_workflowhub_files_in_repo()

    for workflow_file in workflow_files:
        path = Path(workflow_file)
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))

        workflow_id = None
        if "id" in workflow.keys():
            workflow_id = workflow["id"]

        if workflow_id is None:
            print(f"WARNING: no workflow id found for {workflow_file}!")
            continue

        temp_graph = rdfize(workflow)

        if temp_graph:
            rdf_graph += temp_graph
        else:
            wf_warnings.append(workflow_id)

    return rdf_graph

def generate_dump(directory):
    """
    Produce an single RDF file for all imported workflows.
    """
    rdf_graph = Graph()

    # process_workflows_by_id(rdf_graph, "1104")
    process_workflows(rdf_graph)
    rdf_graph.serialize(format="turtle", destination=os.path.join(directory, "workflowhub-dump.ttl"))

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
    wf_warnings = []
    directory = "../../content/datasets"

    generate_dump(directory)

    for wf_id in wf_warnings:
        print(f"WARNING: No graph generated for workflow {wf_id}: formatting error.")