import os
import glob
import yaml
from pathlib import Path
from rdflib import Graph
# from rdflib import ConjunctiveGraph

edam_version = "https://github.com/edamontology/edamontology/raw/main/EDAM_dev.owl"

kg = Graph()
kg.parse(edam_version, format="xml")


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


def getBiotoolsIdFromDebian(debian_data) -> str:
    """
    Get the bio.tools ID from the debian data.
    """
    if "registries" in debian_data.keys():
        for r in debian_data["registries"]:
            if "name" in r.keys() and r["name"] == "bio.tools":
                return r["entry"]
    return None


def getCitationFromDebian(debian_data) -> list:
    """
    Get DOIs from the debian data.
    """
    res = []
    if "bib" in debian_data.keys():
        for entry in debian_data["bib"]:
            if "key" in entry.keys() and "value" in entry.keys():
                res.append(entry["key"] + ":" + entry["value"])
    return res


def getDescriptionFromDebian(debian_data) -> str:
    """
    Get tool descriptions from the debian data.
    """
    if "descr" in debian_data.keys():
        for entry in debian_data["descr"]:
            if (
                "language" in entry.keys()
                and "description" in entry.keys()
                and entry["language"] == "en"
            ):
                return entry["description"]
    # elif 'language' in entry.keys() and 'long_description' in entry.keys() and entry['language'] == "en":
    # return entry['long_description']
    return None


def rdfize(data) -> Graph:
    prefix = """
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix schema: <http://schema.org/> .
@prefix biotools: <https://bio.tools/> .
@prefix scicrunch: <https://scicrunch.org/resolver/> .
@prefix debianmed: <https://salsa.debian.org/med-team/> .
@prefix bioconda: <https://github.com/bioconda/bioconda-recipes/tree/master/recipes/> .
@prefix guix: <https://packages.guix.gnu.org/packages/> .
@prefix edam: <http://edamontology.org/> .
"""

    triples = ""

    dois = getCitationFromDebian(data)
    description = getDescriptionFromDebian(data)

    try:
        if "package" in data.keys():
            package_uri = f"debianmed:{data['package']}"
            triples += f"{package_uri} rdf:type schema:SoftwareApplication .\n"
            triples += f'{package_uri} schema:name "{data["package"]}" .\n'
            # if "description" in data.keys() :
            #   triples += f'{package_uri} schema:description "{data["description"]}" .\n'
        if "license" in data.keys():
            triples += f'{package_uri} schema:license "{data["license"]}" .\n'
        if "version" in data.keys():
            triples += f'{package_uri} schema:softwareVersion "{data["version"]}" .\n'
        if description:
            triples += f'{package_uri} schema:description "{description}" .\n'
        if "homepage" in data.keys():
            triples += f'{package_uri} schema:url "{data["homepage"]}" .\n'
        if "tags" in data.keys():
            for kw in data["tags"]:
                if "tag" in kw.keys():
                    triples += f'{package_uri} schema:keywords "{kw["tag"]}" .\n'
        # process DOIs
        for doi in dois:
            triples += f'{package_uri} schema:citation "{doi}" .\n'

        # process identifiers
        # if "registries" in data.keys():
        #  for e in data["registries"]:
        #   if "name" in e.keys() and "entry" in e.keys():
        #    id = f"{e['name'].lower()}:{e['entry']}"
        #   triples += f'{package_uri} schema:identifier "{id}" .\n'

        # process identifiers
        if "registries" in data.keys():
            for e in data["registries"]:
                if "name" in e.keys() and "entry" in e.keys():
                    if e["entry"] == "atac, meryl" and e["name"] == "conda:bioconda":
                        print("test")
                        for id in e["entry"].split(", "):
                            triples += (
                                f"{package_uri} schema:identifier bioconda:{id} .\n"
                            )
                if e["name"] == "bio.tools":
                    triples += f"{package_uri} schema:identifier biotools:{e['entry'].lower()} .\n"
                # elif e["name"] == "OMICtools":
                # continue
                elif e["name"] == "conda:bioconda" and e["entry"] != "atac, meryl":
                    triples += (
                        f"{package_uri} schema:identifier bioconda:{e['entry']} .\n"
                    )
                elif e["name"] == "SciCrunch":
                    triples += (
                        f"{package_uri} schema:identifier scicrunch:{e['entry']} .\n"
                    )
                elif e["name"] == "guix":
                    triples += f"{package_uri} schema:identifier guix:{e['entry']} .\n"
                else:
                    triples += f'{package_uri} schema:identifier "{e["name"].lower()}:{e["entry"]}" .\n'

        if "topics" in data.keys():
            top = getEdamUrisFromLabels(data["topics"])
            for t in top:
                triples += f"{package_uri} schema:applicationSubCategory edam:{t} .\n"

        if "edam_scopes" in data.keys():
            for edam_scope in data["edam_scopes"]:
                for section in edam_scope.keys():
                    if section == "function":
                        ope = getEdamUrisFromLabels(edam_scope["function"])
                        for o in ope:
                            triples += f"{package_uri} schema:featureList edam:{o} .\n"

                    if section == "input" or section == "output":
                        for item in edam_scope[section]:
                            for element in item.keys():
                                if element == "data":
                                    dat = getEdamUrisFromLabels([item["data"]])
                                    for d in dat:
                                        triples += f"{package_uri} schema:additionalType edam:{d} .\n"
                                if element == "format":
                                    forma = getEdamUrisFromLabels(item["format"])
                                    for f in forma:
                                        triples += f"{package_uri} schema:encodingFormat edam:{f} .\n"

        g = Graph()
        g.parse(data=prefix + "\n" + triples, format="turtle")
        print(g.serialize(format="turtle"))
        return g

    except Exception as e:
        print("PARSING ERROR for:")
        print(prefix + "\n" + triples)
        raise (e)


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
                    destination=os.path.join(directory, tpe_id + ".debian.jsonld"),
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
