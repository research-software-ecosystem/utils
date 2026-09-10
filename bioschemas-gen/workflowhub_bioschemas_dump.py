import os
import glob
from rdflib import Graph

try:
    from tabulate import tabulate
except ImportError:

    def tabulate(rows, headers=()):
        return "\n".join(" | ".join(str(value) for value in row) for row in rows)


def get_workflowhub_files_in_repo():
    workflows = []
    for data_file in glob.glob(r"../../content/imports/workflowhub/*.workflowhub.jsonld"):
        filename_ext = os.path.basename(data_file).split(".")
        if len(filename_ext) == 3 and filename_ext[2] == "jsonld":
            workflows.append(data_file)
    print(f"found {len(workflows)} workflowhub descriptors")
    with open(
        "../../content/datasets/workflowhub_bioschemas_files_list.txt",
        "w",
        encoding="utf-8",
    ) as f:
        for workflow in workflows:
            f.write(f"{workflow}\n")
    return workflows


def process_workflows():
    """
    Go through all workflowhub entries in bioschemas JSON-LD and produce an single RDF file.
    """
    workflow_files = get_workflowhub_files_in_repo()
    rdf_graph = Graph()

    for workflow_file in workflow_files:
        rdf_graph.parse(workflow_file, format="json-ld")

    rdf_graph.serialize(
        format="turtle",
        destination="../../content/datasets/workflowhub-dump.ttl",
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
    process_workflows()
