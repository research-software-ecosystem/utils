
#from pathlib import Path
from urllib import response

#from matplotlib.pylab import rint
from rdflib import Graph
#from rdflib import ConjunctiveGraph
import requests
#import yaml
import json


edam_version = "https://github.com/edamontology/edamontology/raw/main/EDAM_dev.owl"

kg = Graph()
kg.parse(edam_version, format="xml")


def getEdamUrisFromLabels(edam_labels) -> list :
  """
  Get EDAM URIs from EDAM labels.
  """

  res = []

  for lab in edam_labels:
    query="""
    PREFIX edam: <http://edamontology.org/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

    SELECT ?label ?entity WHERE {
        ?entity rdfs:label '%s' .
    }
    """%(lab)

    q = kg.query(query)
    for r in q:
        uri = r['entity'].rsplit('/', 1)[-1]
        #url.rsplit('/', 1)
        res.append(f'{uri}')

  return res

def get_metadata(url):
    
    response = requests.get(url)
    response.raise_for_status() 

    data = json.loads(response.text)
    return data

def rdfize(data) -> Graph:

    prefix = """
    @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    @prefix schema: <http://schema.org/> .
    @prefix spdx: <http://spdx.org/rdf/terms/> .
    @prefix biotools: <https://bio.tools/> .
    """

    triples = ""

    #edam_operations = []
    #edam_topics = []
    #keywords = []

    try:

        for entry in data:

            ## Minimum
            if "link" in entry.keys():
                package_uri = f'<{entry["link"]}>'
                triples += f'{package_uri} rdf:type schema:ComputationalWorkflow .\n'
                triples += f'{package_uri} schema:url "{entry["link"]}" .\n'
            
            if "name" in entry.keys():
                triples += f"{package_uri} schema:name " + json.dumps(entry["name"]) + " .\n"

            if "description" in entry.keys():
                triples += f"{package_uri} schema:description " + json.dumps(entry["description"]) + " .\n"


            ## Recommended
            if "id" in entry.keys():
                triples += f'{package_uri} schema:identifier "{entry["id"]}" .\n'
                print(entry["id"])
            
            if "doi" in entry.keys():
                triples += f'{package_uri} schema:citation "{entry["doi"]}" .\n'
        
            if "latest_version" in entry.keys():
                triples += f'{package_uri} schema:softwareVersion "{entry["latest_version"]}" .\n'

            if "license" in entry.keys():
                triples += f'{package_uri} schema:license "{entry["license"]}" .\n'

            if "creators" in entry.keys():
                for creator in entry["creators"]:
                    triples += f'{package_uri} schema:author "{creator}" .\n'

            if "edam_operation" in entry.keys():
                ope = getEdamUrisFromLabels(entry["edam_operation"])
                for o in ope:
                    #edam_operations.append("edam:" + o)
                    triples += f'{package_uri} schema:featureList "{o}" .\n'

            if "edam_topic" in entry.keys():
                top = getEdamUrisFromLabels(entry["edam_topic"])
                for t in top:
                    #edam_topics.append("edam:" + t)
                    triples += f'{package_uri} schema:applicationSubCategory "{t}" .\n'

            ## Optional
            if "create_time" in entry.keys():
                triples += f'{package_uri} schema:dateCreated "{entry["create_time"]}" .\n'

            if "update_time" in entry.keys():
                triples += f'{package_uri} schema:dateModified "{entry["update_time"]}" .\n'

            if "tags" in entry.keys():
                for tag in entry["tags"]:
                    triples += f'{package_uri} schema:keywords "{tag}" .\n'
        
    
        g = Graph()
        g.parse(data=prefix+"\n"+triples, format="turtle")
        print(g.serialize(format='turtle'))
        g.serialize(
            format="turtle",
            destination="../../content/datasets/galaxyworkflow-dump.ttl",
        )



    except Exception as e:
        print("PARSING ERROR for:")
        print(prefix+"\n"+triples)
        raise(e)

if __name__ == "__main__":
    url = "https://raw.githubusercontent.com/galaxyproject/galaxy_codex/refs/heads/main/communities/all/resources/workflows.json"
    data = get_metadata(url)
    rdfize(data)
    #rdfize(data[1:1000])