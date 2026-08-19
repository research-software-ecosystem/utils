import json
import os
import glob
import re
import requests
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

def urlExists(url, timeout=5):
    #"""Check if a biotools ID exists using the bio.tools JSON API (not the front-end URL)."""
    """Check if a URL exists """
    #id = biotools_id.lower().split("biotools:", 1)[-1]
    #print(id)
    #api_url = f"https://bio.tools/api/tool/{id}/?format=json"
    try:
        r = requests.get(url, timeout=timeout)
        return r.status_code == 200
    except requests.RequestException:
        print(f"WARNING: URL {url} does not exist. \n") 
        return False

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
      #print(dep)
    #res = bioconductor_data['Depends']
    #print(res)

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
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix schema: <http://schema.org/> .
@prefix biotools: <https://bio.tools/> .
@prefix bioconductor: <https://git.bioconductor.org/packages/> .
"""

    triples = ""

    name = None
    url = None

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

    try:
        ## Minimum properties
        if name :
            package_uri = f"bioconductor:{name}"
            triples += f'{package_uri} rdf:type schema:SoftwareApplication .\n'
            triples += f'{package_uri} schema:name "{name}" .\n'
        if desc :
            triples += f'{package_uri} schema:description "{desc}" .\n'
        if url :
            triples += f'{package_uri} schema:url <{url}> .\n'

        ## Recommended properties
        if license :
            triples += f'{package_uri} schema:license "{license}" .\n'
        if version :
            triples += f'{package_uri} schema:softwareVersion "{version}" .\n'

        ## Optional properties
        if publi :
            triples += f'{package_uri} schema:dateModified "{publi}" .\n'
        if maintainers : ## possibly several, can't parse them properly, no pattern to follow
            triples += f'{package_uri} schema:maintainer "{maintainers}" .\n'
        if title :
            triples += f'{package_uri} schema:alternateName "{title}" .\n'
        if repo :
            triples += f'{package_uri} schema:codeRepository <{repo}> .\n'

        #for author in authors:
        if authors:
            triples += f'{package_uri} schema:author "{authors}" .\n'
        for dep in depen:
            triples += f'{package_uri} schema:hasPart "{dep}" .\n'

        for term in biocViews:
            triples += f'{package_uri} schema:keywords "{term}" .\n'



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


def process_tools_by_id(id="SPROUT"):
    """
    Go through all bioconductor entries and produce an RDF graph representation (BioSchemas / JSON-LD).
    """
    tool_files = get_bioconductor_files_in_repo()
    #print(tool_files)

    for tool_file in tool_files:
        #tool_name = os.path.basename(tool_file).split('.')[0]

        tool_id = os.path.basename(tool_file)
        tool_id = tool_id.removesuffix(".bioconductor.json") 

        # tool_name = None
        # if "Package" in tool.keys():
        #     tool_name = tool["Package"]
        #tool_id = Path(tool_file).stem.removesuffix(".bioconductor")
        #print(tool_id)
        #print(tool_name)
        if id == tool_id:# or id == tool_id:

    #for tool_file in tool_files:
        #if id in tool_file:
            path = Path(tool_file)
            #tool = yaml.safe_load(path.read_text(encoding="utf-8"))
            tool = json.loads(path.read_text(encoding="utf-8"))

            #print(tool_file)
            # print(json.dumps(tool, indent=2))
            #tool_id = None
            #tool_id = id
            #if "Package" in tool.keys():
                #tool_id = tool["Package"]

            if tool_id is None:
                print(f"WARNING: no tool id found for {tool_file}!")
                continue
            tpe_id = tool_id.lower()
            #print("test" +tpe_id)
            directory = os.path.join("..", "..", "content", "data", tpe_id)

            ## generate bioconductor JSON-LD and TTL files
            temp_graph = rdfize(tool)
            #print(temp_graph.serialize(format="turtle"))
            if temp_graph and os.path.exists(directory):
                temp_graph.serialize(
                    format="json-ld",
                    auto_compact=True,
                    destination=os.path.join(directory, tpe_id + ".bioconductor.jsonld"),
                )
                temp_graph.serialize(
                    format="turtle",
                    destination=os.path.join(directory, tpe_id + ".bioconductor.ttl"),
                )

def clean():
    for data_file in glob.glob(r"../../content/data/*/*.bioconductor.jsonld"):
        print(f"removing file {data_file}")
        os.remove(data_file)
    for data_file in glob.glob(r"../../content/data/*/*.bioconductor.ttl"):
        print(f"removing file {data_file}")
        os.remove(data_file)


def process_tools():
    """
    Go through all bioconductor entries and produce an RDF graph representation (BioSchemas / JSON-LD).
    """
    tool_files = get_bioconductor_files_in_repo()
    for tool_file in tool_files:
        path = Path(tool_file)
        tool = json.loads(path.read_text(encoding="utf-8"))


        #print(tool_file)
        tool_id = os.path.basename(tool_file)
        tool_id = tool_id.removesuffix(".bioconductor.json") 
        # if "Package" in tool.keys():
        #     tool_id = tool["Package"]
        # tool_id = os.path.basename(tool_file)
        # tool_id = tool_id.removesuffix(".bioconductor.json")

        if tool_id is None:
            print(f"WARNING: no tool id found for {tool_file}!")
            continue

        tpe_id = tool_id.lower()
        directory = os.path.join("..", "..", "content", "data", tpe_id)

        if not os.path.exists(directory):
            print(f"WARNING: Directory {directory} does not exist for {tool_id}!")
            continue

        ## generate bioconductor JSON-LD and TTL files
        temp_graph = rdfize(tool)
        if temp_graph and os.path.exists(directory):
            temp_graph.serialize(
                format="json-ld",
                auto_compact=True,
                destination=os.path.join(directory, tpe_id + ".bioconductor.jsonld"),
            )
            temp_graph.serialize(
                format="turtle",
                destination=os.path.join(directory, tpe_id + ".bioconductor.ttl"),
            )
            print(temp_graph.serialize(format="turtle"))


if __name__ == "__main__":
    clean()
    process_tools()
    #process_tools_by_id("bioconductor-ribocrypt")
    #process_tools_by_id("bam2fasta")
    # process_tools_by_id("bowtie2")
