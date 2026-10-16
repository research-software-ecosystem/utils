import os
import glob
import yaml
from pathlib import Path
from rdflib import Graph
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
    """ % (lab)

        q = edam_kg.query(query)
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
@prefix bioschemas: <http://bioschemas.org/> .
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
        if "package" in data.keys() and data['package'] != "ncbi-blast+": ## not handling this exception right now
            package_uri = f"debianmed:{data['package']}"
            triples += f'{package_uri} rdf:type schema:SoftwareApplication .\n'

            ## Minimum
            # dc:conformsTo
            triples += f'{package_uri} schema:conformsTo "https://bioschemas.org/profiles/ComputationalTool/1.0-RELEASE" .\n'

            # description 
            if description:
                triples += f'{package_uri} schema:description "{description}" .\n'

            # name
            triples += f'{package_uri} schema:name "{data["package"]}" .\n'

            # url
            if "homepage" in data.keys():  
                triples += f'{package_uri} schema:url <{data["homepage"]}> .\n'
            
            ## Recommended

            # applicationCategory

            # applicationSubCategory
            if "topics" in data.keys():
                top = getEdamUrisFromLabels(data["topics"]) ## ideally EDAM terms would already be URIs rather than labels
                for t in top:
                    triples += f'{package_uri} schema:applicationSubCategory edam:{t} .\n'

            # author

            # citation
            for doi in dois:
                triples += f'{package_uri} schema:citation "{doi}" .\n'

            # featureList, input, output
            if "edam_scopes" in data.keys():
                for edam_scope in data["edam_scopes"]:
                    for section in edam_scope.keys():
                        if section == "function":
                            ope = getEdamUrisFromLabels(edam_scope["function"])
                            for o in ope:
                                triples += f'{package_uri} schema:featureList edam:{o} .\n'

                        if section == "input":
                            for item in edam_scope[section]:
                                for element in item.keys():
                                    if element == "data":
                                        dat = getEdamUrisFromLabels([item["data"]])
                                        for d in dat:
                                            triples += f'{package_uri} schema:additionalType edam:{d} .\n'
                                            triples += f'{package_uri} bioschemas:input edam:{d} .\n'
                                    if element == "format":
                                        forma = getEdamUrisFromLabels(item["format"])
                                        for f in forma:
                                            triples += f'{package_uri} schema:encodingFormat edam:{f} .\n'
                                            triples += f'{package_uri} bioschemas:input edam:{f} .\n'

                        if section == "output":
                            for item in edam_scope[section]:
                                for element in item.keys():
                                    if element == "data":
                                        dat = getEdamUrisFromLabels([item["data"]])
                                        for d in dat:
                                            triples += f'{package_uri} schema:additionalType edam:{d} .\n'
                                            triples += f'{package_uri} bioschemas:output edam:{d} .\n'
                                    if element == "format":
                                        forma = getEdamUrisFromLabels(item["format"])
                                        for f in forma:
                                            triples += f'{package_uri} schema:encodingFormat edam:{f} .\n'
                                            triples += f'{package_uri} bioschemas:output edam:{f} .\n'
            # license
            if "license" in data.keys():
                triples += f'{package_uri} schema:license "{data["license"]}" .\n'

            # softwareVersion
            if "version" in data.keys():
                triples += f'{package_uri} schema:softwareVersion "{data["version"]}" .\n'

            ## Optional

            # applicationSuite
            # codeRepository
            # contributor
            # discussionUrl
            # downloadUrl
            # funder
            # hasPart

            # identifier

            if "registries" in data.keys():
                for e in data["registries"]:
                    if "name" in e.keys() and "entry" in e.keys():
                        if e["entry"] == "atac, meryl": ## not handling this exception right now
                            continue
                            # for id in e["entry"].split(", "):
                                # triples += (
                                #     f'{package_uri} schema:identifier bioconda:{id} .\n'
                                # # )
                        if e["name"] == "bio.tools":
                            triples += f'{package_uri} schema:identifier biotools:{e["entry"].lower()} .\n'
                        # elif e["name"] == "OMICtools": ## prefix/URIs do not exist anymore
                        #     triples += f'{package_uri} schema:identifier omictools:{e["entry"].lower()} .\n'
                        elif e["name"] == "conda:bioconda":
                            triples += (
                                f'{package_uri} schema:identifier bioconda:{e["entry"]} .\n'
                            )
                        elif e["name"] == "SciCrunch":
                            triples += (
                                f'{package_uri} schema:identifier scicrunch:{e["entry"]} .\n'
                            )
                        elif e["name"] == "guix":
                            triples += f'{package_uri} schema:identifier guix:{e["entry"]} .\n'
                        else:
                            triples += f'{package_uri} schema:identifier "{e["name"].lower()}:{e["entry"]}" .\n' ## keep scicrunch or other IDs as a string

            # input
            ## see above with featureList

            # isAccessibleForFree
            # isBasedOn
            # isPartOf

            # keywords
            if "tags" in data.keys():
                for kw in data["tags"]:
                    if "tag" in kw.keys():
                        triples += f'{package_uri} schema:keywords "{kw["tag"]}" .\n'

            # operatingSystem

            # output
            ## See above with featureList

            # programmingLanguage
            # provider
            # sowtwareAddOn
            # softwareHelp
            # thumbnailUrl

        g = Graph()
        g.parse(data=prefix + "\n" + triples, format="turtle")
        print(g.serialize(format="turtle"))
        return g

    except Exception as e:
        print("PARSING ERROR for:")
        print(prefix + "\n" + triples)
        raise (e)


def get_debian_files_in_repo():
    tools = []
    for data_file in glob.glob("../../content/data/*/*.debian.yaml"):
        tools.append(data_file)
    return tools


def process_tools_by_id(rdf_graph, id="SPROUT"):
    """
    Go through all debian entries and produce an RDF graph representation (BioSchemas / TTL).
    """
    tool_files = get_debian_files_in_repo()

    for tool_file in tool_files:

        tool_name = os.path.basename(tool_file)
        tool_name = tool_name.removesuffix(".debian.yaml")
    
        if id == tool_name:
            
            path = Path(tool_file)
            tool = yaml.safe_load(path.read_text(encoding="utf-8"))

            tool_id = None
            if "Package" in tool.keys():
                tool_id = tool["Package"]

            if tool_id is None:
                print(f"WARNING: no tool id found in {tool_file}.")
                tool_id = tool_name

            ## generate graph for specified tool
            temp_graph = rdfize(tool)

            if temp_graph:
                rdf_graph += temp_graph
            else:
                tool_warnings.append(tool_id)

    return rdf_graph


def clean():
    for data_file in glob.glob(r"../../content/data/*/*.debian.jsonld"):
        print(f"removing file {data_file}")
        os.remove(data_file)
    for data_file in glob.glob(r"../../content/data/*/*.debian.ttl"):
        print(f"removing file {data_file}")
        os.remove(data_file)


def process_tools(rdf_graph):
    """
    Go through all bio.tools entries and produce an RDF graph representation (BioSchemas / JSON-LD).
    """
    tool_files = get_debian_files_in_repo()
    for tool_file in tool_files:
        print(f"processing {tool_file}")
        tool_name = os.path.basename(tool_file)
        tool_name = tool_name.removeprefix("bioconda_").removesuffix(".yaml")

        path = Path(tool_file)
        tool = yaml.safe_load(path.read_text(encoding="utf-8"))

        tool_id = None
        if "package" in tool.keys():
            tool_id = tool["package"]

        if tool_id is None:
            print(f"WARNING: no bioconda id found in {tool_file}, using file basename instead.")
            tool_id = tool_name

        biotools_id = getBiotoolsIdFromDebian(tool)
        if biotools_id:
            tpe_id = biotools_id.lower().split("biotools:", 1)[-1]
        else:
            print(f"WARNING: no biotools id found for {tool_file}, using debian id to create data directory instead.")
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

    # process_tools_by_id(rdf_graph, "r-bioc-limma")
    process_tools(rdf_graph)
    rdf_graph.serialize(format="turtle", destination=os.path.join(directory, "debian-dump.ttl"))

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

    # clean()
    # process_tools()
    # #process_tools_by_id("bowtie2")

    tool_warnings = []
    directory = "../../content/datasets"

    generate_dump(directory)

    for tool_id in tool_warnings:
        print(f"WARNING: No graph generated for tool {tool_id}: formatting error.")

    print(f"{len(tool_warnings)} tools could not be processed due to formatting errors.")
