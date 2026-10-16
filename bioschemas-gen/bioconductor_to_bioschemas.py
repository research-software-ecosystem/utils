import json
import os
import glob
import re
import requests
import yaml
from pathlib import Path
from rdflib import Graph

try:
    from tabulate import tabulate
except ImportError:

    def tabulate(rows, headers=()):
        return "\n".join(" | ".join(str(value) for value in row) for row in rows)

## No specific format for authors and maintainers, no pattern to parse
# def getAuthors(bioconductor_data) -> list:
#   """
#   Get Authors from the bioconductor data.
#   """
#   res = []
#   if 'Author' in bioconductor_data.keys():
#     s = bioconductor_data['Author']
#     names = re.split(r'\s*\[.*?\]\s*,\s*', s)
#     res = [re.sub(r'\s*\[.*?\]$', '', n).strip() for n in names]

#   return res

# def getMaintainers(bioconductor_data) -> list:
#   """
#   Get Maintainers from the bioconductor data.
#   """
#   res = []
#   if 'Maintainer' in bioconductor_data.keys():
#     s = bioconductor_data['Maintainer']
#     names = re.split(r'\s*\[.*?\]\s*,\s*', s)
#     res = [re.sub(r'\s*\[.*?\]$', '', n).strip() for n in names]

#   return res

def getDependencies(bioconductor_data) -> list:
  """
  Get package dependencies from the bioconductor data.
  """
  res = []
  if 'Depends' in bioconductor_data.keys():
    for dep in bioconductor_data['Depends']:
      res.append(dep)

#   if 'Imports' in bioconductor_data.keys():
#     for dep in bioconductor_data['Imports']:
#       res.append(dep)

  return res

def getBiocViews(bioconductor_data) -> list:
  """
  Get biocViews terms from bioconductor packages.
  """
  res = []
  if 'biocViews' in bioconductor_data.keys():
    #for term in bioconductor_data['biocViews']:
      #res.append(term)
      #print(dep)
    res = bioconductor_data['biocViews']
    #print(res)

  return res

def rdfize(data) -> Graph:
    prefix = """
@prefix bioconductor: <https://git.bioconductor.org/packages/> . ## Not accessible ATM
@prefix biotools: <https://bio.tools/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix schema: <http://schema.org/> .
"""

    triples = ""

    name = None
    url = None
    desc = None
    license = None
    version = None
    publi = None
    maintainers = None
    title = None
    repo = None
    authors = None
    depen = None
    biocViews = None

    if 'Package' in data.keys():
        name = data['Package']
    if 'Description' in data.keys():
        desc = data['Description']
    if 'URL' in data.keys():
        url = data['URL']

    if 'License' in data.keys():
        license = data['License']
    if 'Version' in data.keys():
        version = data['Version']

    if 'Date/Publication' in data.keys():
        publi = data['Date/Publication']
    if 'Maintainer' in data.keys():
        maintainers = data['Maintainer']
    if 'Title' in data.keys():
        title = data['Title']
    if 'git_url' in data.keys():
        repo = data['git_url']
    if 'Author' in data.keys():
        authors = data['Author']
    if 'Depends' in data.keys():
        depen = getDependencies(data)
    if 'biocViews' in data.keys():
        biocViews = getBiocViews(data)
    # if 'source.ver' in data.keys():   ## lacks base url
    #     download = data['source.ver']

    try:
        ## Minimum properties
        if name :
            package_uri = f"bioconductor:{name}"
            triples += f'{package_uri} rdf:type schema:SoftwareApplication .\n'

            triples += f'{package_uri} schema:conformsTo "https://bioschemas.org/profiles/ComputationalTool/1.0-RELEASE" .\n'

            if desc :
                triples += f'{package_uri} schema:description "{desc}" .\n'

            triples += f'{package_uri} schema:name "{name}" .\n'

            if url :
                triples += f'{package_uri} schema:url <{url}> .\n'

        ## Recommended properties

        # applicationCategory 

        # applicationSubCategory ## EDAM terms not yet available 

        if authors:
            triples += f'{package_uri} schema:author "{authors}" .\n'

        # citation

        # featureList ## EDAM terms not yet available

        if license :
            triples += f'{package_uri} schema:license "{license}" .\n'

        if version :
            triples += f'{package_uri} schema:softwareVersion "{version}" .\n'

        ## Optional properties

        # applicationSuite

        if repo :
            triples += f'{package_uri} schema:codeRepository <{repo}> .\n'

        # contributor
        # discussionUrl

        # if download :
        #     triples += f'{package_uri} schema:downloadUrl <bioconductor:{download}> .\n'

        # funder
        # hasPart
        # identifier
        # input
        # isAccessibleForFree
        # isBasedOn
        # isPartOf

        for term in biocViews:
            triples += f'{package_uri} schema:keywords "{term}" .\n'

        # operatingSystem
        # output
        # programmingLanguage

        # provider
        triples += f'{package_uri} schema:provider <https://bioconductor.org/> .\n'
        triples += f'<https://bioconductor.org/> schema:type "Organization" .\n'

        # softwareAddOn
        # softwareHelp
        # thumbnailUrl

        ## Other properties
        if title :
            triples += f'{package_uri} schema:alternateName "{title}" .\n'
        if publi :
            triples += f'{package_uri} schema:dateModified "{publi}" .\n'
        if maintainers : ## possibly several, can't parse them properly, no pattern to follow
            triples += f'{package_uri} schema:maintainer "{maintainers}" .\n'
        if depen:
                for dependency in depen:
                    triples += f'{package_uri} schema:softwareRequirements "{dependency}" .\n'    

        g = Graph()
        g.parse(data=prefix + "\n" + triples, format="turtle")
        print(g.serialize(format="turtle"))
            # serialize in compact json ld syntax
            # print(g.serialize(format='json-ld'))
        return g

    except Exception as e:
        print("PARSING ERROR for:")
        print(prefix + "\n" + triples)
        print(e)


def get_bioconductor_files_in_repo():
    tools = []
    for data_file in glob.glob("../../content/data/*/*.bioconductor.json"):
        tools.append(data_file)
    return tools


def process_tools_by_id(rdf_graph, id="SPROUT"):
    """
    Go through all bioconductor entries and produce an RDF graph representation (BioSchemas / JSON-LD) for the specified tool.
    """
    tool_files = get_bioconductor_files_in_repo()
    #print(tool_files)

    for tool_file in tool_files:

        tool_name = os.path.basename(tool_file)
        tool_name = tool_name.removesuffix(".bioconductor.json") 

        if id == tool_name:
            
            path = Path(tool_file)
            tool = json.loads(path.read_text(encoding="utf-8"))

            tool_id = None
            if "Package" in tool.keys():
                tool_id = tool["Package"]

            if tool_id is None:
                print(f"WARNING: no tool id found in {tool_file}.")
                tool_id = tool_name

            # if biotools_id:
            #     tpe_id = biotools_id
            # else:
                # print(f"WARNING: no biotools id found for {tool_file}, using bioconductor id to create data directory instead.")
            # tpe_id = tool_id ## assumes bioc package name == biotools ID - biotools ID is not in metadata

            # directory = os.path.join("..", "..", "content", "data", tpe_id)

            ## generate TTL file
            temp_graph = rdfize(tool)

            if temp_graph:
                rdf_graph += temp_graph
            else:
                tool_warnings.append(tool_id)

def clean():
    for data_file in glob.glob(r"../../content/data/*/*.bioconductor.jsonld"):
        print(f"removing file {data_file}")
        os.remove(data_file)
    for data_file in glob.glob(r"../../content/data/*/*.bioconductor.ttl"):
        print(f"removing file {data_file}")
        os.remove(data_file)


def process_tools(rdf_graph):
    """
    Go through all bioconductor entries and produce an RDF graph representation (BioSchemas / TTL).
    """
    tool_files = get_bioconductor_files_in_repo()
    for tool_file in tool_files:
        print(f"processing {tool_file}")

        tool_name = os.path.basename(tool_file)
        tool_name = tool_name.removesuffix(".bioconductor.json")

        path = Path(tool_file)
        tool = json.loads(path.read_text(encoding="utf-8"))

        tool_id = None
        if "Package" in tool.keys():
            tool_id = tool["Package"]

        if tool_id is None:
            print(f"WARNING: no bioconductor id found in {tool_file}, using file basename instead.")
            tool_id = tool_name

        # if biotools_id:
        #     tpe_id = biotools_id.lower().split("biotools:", 1)[-1]
        # else:
            # print(f"WARNING: no biotools id found for {tool_file}, using bioconductor id to create data directory instead.")

        tpe_id = tool_id.lower() ## assumes bioc package name == biotools ID - biotools ID is not in metadata
        directory = os.path.join("..", "..", "content", "data", tpe_id)

        if not os.path.exists(directory):
            print(f"WARNING: Directory {directory} does not exist for {tool_id}.")
            continue

        ## generate bioconductor TTL file
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

    # process_tools_by_id(rdf_graph, "xcms")
    process_tools(rdf_graph)
    rdf_graph.serialize(format="turtle", destination=os.path.join(directory, "bioconductor-dump.ttl"))

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

    tool_warnings = []
    directory = "../../content/datasets"

    generate_dump(directory)

    for tool_id in tool_warnings:
        print(f"WARNING: No graph generated for tool {tool_id}: formatting error.")

    print(f"{len(tool_warnings)} tools could not be processed due to formatting errors.")

    # clean()
    # process_tools()
    #process_tools_by_id("bioconductor-ribocrypt")
    #process_tools_by_id("bam2fasta")
    # process_tools_by_id("deseq2")
