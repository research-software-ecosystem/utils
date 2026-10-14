import os
import glob
from token import NAME
import requests
import yaml
from pathlib import Path
from rdflib import Graph

try:
    from tabulate import tabulate
except ImportError:

    def tabulate(rows, headers=()):
        return "\n".join(" | ".join(str(value) for value in row) for row in rows)

def getBiotoolsId(bioconda_data) -> str:
    """
    Get the bio.tools ID from the bioconda data.
    """
    if "extra" in bioconda_data.keys():
        if "identifiers" in bioconda_data["extra"].keys():
            for id in bioconda_data["extra"]["identifiers"]:
                if id.lower().startswith("biotools:"):
                    return id
        else:
            print(f"WARNING: no biotools identifiers found in bioconda data.")
            return None
    if id:
        biotools_name = id.lower().split("biotools:", 1)[-1]
        api_url = f"https://bio.tools/api/tool/{biotools_name}/?format=json"
        if not urlExists(api_url):
            print(f"WARNING: biotools ID {id} does not exist in bio.tools. Biotools identifier will be skipped. \n")

def getCitation(bioconda_data) -> list:
    """
    Get DOIs from the bioconda data.
    """
    res = []
    if "extra" in bioconda_data.keys():
        if "identifiers" in bioconda_data["extra"].keys():
            for id in bioconda_data["extra"]["identifiers"]:
                if id.lower().startswith("doi:"):
                    res.append(id)
    if len(res) > 0:
        return res
    return None

def getDownloadUrl(bioconda_data) -> list:
  """
  Get URLs from the bioconda data.
  """
  res = []
  if 'source' in bioconda_data.keys():
    if isinstance(bioconda_data['source'], dict):
      if 'url' in bioconda_data['source'].keys():
        if isinstance(bioconda_data['source']['url'], list):
          for url in bioconda_data['source']['url']:
            res.append(url)
        elif isinstance(bioconda_data['source']['url'], str):
          res.append(bioconda_data['source']['url'])
        else:
          print(f"WARNING: source URL is not a string or list: {bioconda_data['source']['url']}")
    else:
        print(f"WARNING: source is not a dictionary for package {bioconda_data['package']['name'] if 'package' in bioconda_data.keys() and 'name' in bioconda_data['package'].keys() else 'unknown'}, returning None for download URL.")
    if len(res) > 0:
        return res
    return None
    
def getDependencies(bioconda_data) -> list:
  """
  Get host dependencies from the bioconda data.
  """
  res = []
  if 'requirements' in bioconda_data.keys():
    if 'host' in bioconda_data['requirements'].keys() and bioconda_data['requirements']['host']:
      for pkg in bioconda_data['requirements']['host']:
        # pkg = pkg.split(' ', 1)[0]
        res.append(pkg)
    if 'run' in bioconda_data['requirements'].keys() and bioconda_data['requirements']['run']:
      for pkg in bioconda_data['requirements']['run']:
        # pkg = pkg.split(' ', 1)[0]
        res.append(pkg)
    if 'build' in bioconda_data['requirements'].keys() and bioconda_data['requirements']['build']:
      for pkg in bioconda_data['requirements']['build']:
        # pkg = pkg.split(' ', 1)[0]
        res.append(pkg)
  if len(res) > 0:
      return res
  return None

def getIdentifiers(bioconda_data) -> list:
    """
    Get other identifiers from the bioconda data.
    """
    res = []
    if "extra" in bioconda_data.keys():
        if "identifiers" in bioconda_data["extra"].keys():
            for id in bioconda_data["extra"]["identifiers"]:
                if not id.lower().startswith("biotools:") and not id.lower().startswith("doi:"):
                    res.append(id)
    if len(res) > 0:
        return res
    return None

def getMaintainers(bioconda_data) -> list:
    """
    Get Maintainers from the bioconda data.
    """
    res = []
    if "extra" in bioconda_data.keys():
        if "recipe-maintainers" in bioconda_data["extra"].keys():
            for id in bioconda_data["extra"]["recipe-maintainers"]:
                res.append(id)
    if len(res) > 0:
        return res
    return None

def urlExists(url, timeout=1):
    """Check if a URL exists """
    try:
        r = requests.get(url, timeout=timeout)
        return r.status_code == 200
    except requests.RequestException:
        print(f"WARNING: URL {url} does not exist. \n") 
        return False

def rdfize(data) -> Graph:
    prefix = """
@prefix bioconda: <https://github.com/bioconda/bioconda-recipes/tree/master/recipes/> .
@prefix biotools: <https://bio.tools/> .
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix schema: <http://schema.org/> .
"""

    triples = ""

    ## Mandatory
    description = None
    name = None
    url = None

    ## Recommended
    citation = getCitation(data)
    license = None
    version = None

    ## Optional
    code_repository = url
    download_urls = getDownloadUrl(data)
    biotools_id = getBiotoolsId(data)
    other_identifier = getIdentifiers(data) 
    software_help = None

    ## not in Bioschemas profile, but in schema.org profile
    alternate_name = None
    dependencies = getDependencies(data)
    maintainer = getMaintainers(data) 

    if "about" in data.keys():
        ## Mandatory
        if "description" in data["about"].keys():
            description = data["about"]["description"]
        elif "summary" in data["about"].keys():
            description = data["about"]["summary"]
        if "home" in data["about"].keys():
            url = data["about"]["home"]
        
        ## Recommended
        if "license" in data["about"].keys():
            license = data["about"]["license"]

        ## Optional
        if "software_help" in data["about"].keys():
            software_help = data["about"]["software_help"]

        ## Other
        if "summary" in data["about"].keys():
            alternate_name = data["about"]["summary"]

    if "package" in data.keys():
        ## Mandatory
        if "name" in data["package"].keys():
            name = data["package"]["name"]
        else:
            print(f"WARNING: no name found in bioconda data, using biotools id instead.")
            name = biotools_id if biotools_id else "unknown"

        ## Recommended
        if "version" in data["package"].keys():
            version = data["package"]["version"]

    try:
        if name:
            package_uri = f'bioconda:{name}'
            triples += f'{package_uri} rdf:type schema:SoftwareApplication .\n'
            # triples += f'{package_uri} rdf:type schema:SoftwareSourceCode .\n'

            ## Minimum
            triples += f'{package_uri} schema:conformsTo "https://bioschemas.org/profiles/ComputationalTool/1.0-RELEASE" .\n'
            if description:
                triples += f'{package_uri} schema:description "{description}" .\n'
            triples += f'{package_uri} schema:name "{name}" .\n'
            if url:
                triples += f'{package_uri} schema:url "{url}" .\n'

            ## Recommended

            # applicationCategory

            # applicationSubCategory

            # author ## available: recipe-maintainer in extra 

            if citation:
                for doi in citation:
                    triples += f'{package_uri} schema:citation "{doi}" .\n'    

            # featureList

            if license:
                triples += f'{package_uri} schema:license "{license}" .\n' 

            if version:
                triples += f'{package_uri} schema:softwareVersion "{version}" .\n'

            ## Optional

            # applicationSuite

            if code_repository:
                triples += f'{package_uri} schema:codeRepository "{code_repository}" .\n'

            # contributor ## available: recipe-maintainer in extra
            # discussionUrl

            if download_urls:
                for url in download_urls:
                    #if urlExists(url):
                    triples += f'{package_uri} schema:downloadUrl <{url}> .\n'

            # funder
            # hasPart

            if biotools_id:
                triples += f'{package_uri} schema:identifier <{biotools_id}> .\n'
                #triples += f'{package_uri} schema:isBasedOn biotools:{biotools_id} .\n'

            triples += f'{package_uri} schema:identifier <bioconda:{name}> .\n'

            if other_identifier:
                for id in other_identifier:
                    triples += f'{package_uri} schema:identifier "{id}" .\n'

            # input
            # isAccessibleForFree
            # isPartOf
            # keywords
            # operatingSystem
            # output
            # programmingLanguage
            # provider ## is "bioconda"?
            # softwareAddOn

            if software_help:
                #if urlExists(software_help):
                triples += f'{package_uri} schema:softwareHelp <{software_help}> .\n'

            # thumbnailsUrl

            ## Other properties not in the Bioschemas profile, but in the schema.org profile

            if alternate_name:
                triples += f'{package_uri} schema:alternateName "{alternate_name}" .\n'

            if maintainer:
                for maint in maintainer:
                    triples += f'{package_uri} schema:maintainer "{maint}" .\n'

            if dependencies:
                for dependency in dependencies:
                    triples += f'{package_uri} schema:softwareRequirements "{dependency}" .\n'    


            g = Graph()
            g.parse(data=prefix + "\n" + triples, format="turtle")
            # print(g.serialize(format="turtle"))
            # serialize in compact json ld syntax
            # print(g.serialize(format='json-ld'))
        return g

    except Exception as e:
        print("PARSING ERROR for:")
        print(prefix + "\n" + triples)
        print(e)


def get_bioconda_files_in_repo():
    tools = []
    for data_file in glob.glob("../../content/data/*/bioconda_*.yaml"):
        tools.append(data_file)
    return tools


def process_tools_by_id(rdf_graph, id="SPROUT"):
    """
    Go through all bioconda entries and produce an RDF graph representation (BioSchemas / JSON-LD) for the specified tool.
    """
    tool_files = get_bioconda_files_in_repo()

    for tool_file in tool_files:

        tool_name = os.path.basename(tool_file)
        tool_name = tool_name.removeprefix("bioconda_").removesuffix(".yaml")

        if id == tool_name:

            path = Path(tool_file)
            tool = yaml.safe_load(path.read_text(encoding="utf-8"))

            # print(tool_file)
            # print(json.dumps(tool, indent=2))
            tool_id = None
            if "package" in tool.keys():
                if "name" in tool["package"].keys():
                    tool_id = tool["package"]["name"]

            if tool_id is None:
                print(f"WARNING: no bioconda id found in {tool_file}, using file basename instead.")
                tool_id = tool_name

            biotools_id = getBiotoolsId(tool)
            if biotools_id:
                tpe_id = biotools_id.lower().split("biotools:", 1)[-1]
            else:
                print(f"WARNING: no biotools id found for {tool_file}, using bioconda id to create data directory instead.")
                tpe_id = tool_id                
            directory = os.path.join("..", "..", "content", "data", tpe_id)

            ## generate TTL file
            temp_graph = rdfize(tool)

            if temp_graph:
                rdf_graph += temp_graph
            else:
                tool_warnings.append(tool_id)

    return rdf_graph

def clean():
    for data_file in glob.glob(r"../../content/data/*/*.bioconda.jsonld"):
        print(f"removing file {data_file}")
        os.remove(data_file)
    for data_file in glob.glob(r"../../content/data/*/*.bioconda.ttl"):
        print(f"removing file {data_file}")
        os.remove(data_file)


def process_tools(rdf_graph):
    """
    Go through all bioconda entries and produce an RDF graph representation (BioSchemas / TTL).
    """
    tool_files = get_bioconda_files_in_repo()
    for tool_file in tool_files:
        print(f"processing {tool_file}")
        tool_name = os.path.basename(tool_file)
        tool_name = tool_name.removeprefix("bioconda_").removesuffix(".yaml")
    
        path = Path(tool_file)
        tool = yaml.safe_load(path.read_text(encoding="utf-8"))

        tool_id = None
        if "package" in tool.keys():
            if "name" in tool["package"].keys():
                tool_id = tool["package"]["name"]

        if tool_id is None:
            print(f"WARNING: no bioconda id found in {tool_file}, using file basename instead.")
            tool_id = tool_name

        biotools_id = getBiotoolsId(tool)
        if biotools_id:
            tpe_id = biotools_id.lower().split("biotools:", 1)[-1]
        else:
            print(f"WARNING: no biotools id found for {tool_file}, using bioconda id to create data directory instead.")
            tpe_id = tool_id                
 
        directory = os.path.join("..", "..", "content", "data", tpe_id)

        if not os.path.exists(directory):
            print(f"WARNING: Directory {directory} does not exist for {tool_id}.")
            continue

        ## generate bioconda TTL file

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

    # process_tools_by_id(rdf_graph, "bioconductor-xcms")
    process_tools(rdf_graph)
    rdf_graph.serialize(format="turtle", destination=os.path.join(directory, "bioconda-dump.ttl"))

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
    # tool_warnings = []
    # process_tools()
    # process_tools_by_id("bioconductor-xcms")
    # process_tools_by_id("infernal")
    # process_tools_by_id("diamond")
    # process_tools_by_id("bam2fasta")
    # process_tools_by_id("bowtie2")
