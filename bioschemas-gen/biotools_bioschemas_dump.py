"""Build datasets/bioschemas-dump.ttl straight from the data/<id>/<id>.biotools.json
files: each entry is turned into Bioschemas JSON-LD in memory (rdfize, recovered from
the retired biotools_to_bioschemas.py, which wrote one .bioschemas.jsonld per tool)
and parsed into one graph. Exits non-zero rather than write an empty dump."""

import glob
import json
import sys

from rdflib import Graph
from tabulate import tabulate


def rdfize(json_entry):
    """
    Transforms a biotools json entry into RDF, and returns a JSON-LD serialization. The following fields
    are covered: contact, publication, EDAM topic, EDAM operation, EDAM inputs & outputs.
    """

    entry = json_entry

    try:
        ctx = {
            "@context": {
                "@base": "https://bio.tools/",
                "biotools": "https://bio.tools/ontology/",
                "edam": "http://edamontology.org/",
                "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
                "sc": "http://schema.org/",
                "dct": "http://purl.org/dc/terms/",
                "bsc": "http://bioschemas.org/",
                "bsct": "http://bioschemas.org/types/",
                "description": "sc:description",
                "name": "sc:name",
                "identifier": "sc:identifier",
                "sameAs": "sc:sameAs",
                "homepage": "sc:url",
                "toolType": "sc:additionalType",
                "primaryContact": "biotools:primaryContact",
                "author": "sc:author",
                "provider": "sc:provider",
                "contributor": "sc:contributor",
                "funder": "sc:funder",
                "hasPublication": "sc:citation",
                "hasTopic": "sc:applicationSubCategory",
                "hasOperation": "sc:featureList",
                "hasInputData": "bsc:input",
                "hasOutputData": "bsc:output",
                "license": "sc:license",
                "version": "sc:softwareVersion",
                "isAccessibleForFree": "sc:isAccessibleForFree",
                "operatingSystem": "sc:operatingSystem",
                "hasApiDoc": "sc:softwareHelp",
                "hasGenDoc": "sc:softwareHelp",
                "hasTermsOfUse": "sc:termsOfService",
                "conformsTo": "dct:conformsTo",
                "additionalType": "sc:additionalType",
                "encodingFormat": "sc:encodingFormat",
            }
        }
        entry.update(ctx)

        entry["@id"] = str(entry["biotoolsID"])
        # entry['@type'] = ['bsc:Tool','sc:SoftwareApplication']
        entry["@type"] = ["sc:SoftwareApplication"]
        entry["applicationCategory"] = "Computational science tool"
        entry["primaryContact"] = []
        entry["author"] = []
        entry["contributor"] = []
        entry["provider"] = []
        entry["funder"] = []
        entry["conformsTo"] = (
            "https://bioschemas.org/profiles/ComputationalTool/0.6-DRAFT"
        )

        if entry.get("credit"):
            for credit in entry["credit"]:
                # print(credit)
                ## Retrieving FUNDERS
                if (
                    credit.get("typeEntity")
                    and "Funding agency" in credit["typeEntity"]
                ):
                    sType = "sc:Organization"
                    if "orcidid" in credit and credit["orcidid"] is not None:
                        if "funder" not in entry:
                            entry["funder"] = {
                                "@id": credit["orcidid"],
                                "@type": sType,
                            }
                        else:
                            entry["funder"].append(
                                {
                                    "@id": credit["orcidid"],
                                    "@type": sType,
                                }
                            )
                    elif "name" in credit and credit["name"] is not None:
                        if "funder" not in entry:
                            entry["funder"] = [credit["name"]]
                        else:
                            entry["funder"].append(credit["name"])

                # Retrieving CONTRIBUTORS, PROVIDERS, DEVELOPERS
                if credit.get("typeRole"):
                    if "Developer" in credit["typeRole"]:
                        # print("**** DEVELOPER ****")
                        # print(credit['name'])
                        if credit.get("typeEntity"):
                            if "Person" in credit["typeEntity"]:
                                sType = "sc:Person"
                            else:
                                sType = "sc:Organization"
                            if "orcidid" in credit and credit["orcidid"] is not None:
                                if "author" not in entry:
                                    entry["author"] = {
                                        "@id": credit["orcidid"],
                                        "@type": sType,
                                    }
                                else:
                                    entry["author"].append(
                                        {
                                            "@id": credit["orcidid"],
                                            "@type": sType,
                                        }
                                    )
                            elif "name" in credit and credit["name"] is not None:
                                if "author" not in entry:
                                    entry["author"] = [credit["name"]]
                                else:
                                    entry["author"].append(credit["name"])
                        else:
                            if "name" in credit and credit["name"] is not None:
                                if "author" not in entry:
                                    entry["author"] = [credit["name"]]
                                else:
                                    entry["author"].append(credit["name"])

                    if "Provider" in credit["typeRole"]:
                        # print("**** PROVIDER ****")
                        # print(credit['name'])
                        if credit.get("typeEntity"):
                            if "Person" in credit["typeEntity"]:
                                sType = "sc:Person"
                            else:
                                sType = "sc:Organization"

                            if "orcidid" in credit and credit["orcidid"] is not None:
                                if "provider" not in entry:
                                    entry["provider"] = {
                                        "@id": credit["orcidid"],
                                        "@type": sType,
                                    }
                                    # if 'name' in credit.keys() and credit['name'] != None:
                                    #    entry['author_person']['name'] = credit['name']
                                else:
                                    entry["provider"].append(
                                        {
                                            "@id": credit["orcidid"],
                                            "@type": sType,
                                        }
                                    )
                            elif "name" in credit and credit["name"] is not None:
                                if "provider" not in entry:
                                    entry["provider"] = [credit["name"]]
                                else:
                                    entry["provider"].append(credit["name"])
                        else:
                            if "name" in credit and credit["name"] is not None:
                                if "provider" not in entry:
                                    entry["provider"] = [credit["name"]]
                                else:
                                    entry["provider"].append(credit["name"])

                    if "Contributor" in credit["typeRole"]:
                        # print("**** CONTRIBUTOR ****")
                        # print(credit['name'])

                        if credit.get("typeEntity"):
                            if "Person" in credit["typeEntity"]:
                                sType = "sc:Person"
                            else:
                                sType = "sc:Organization"

                            if "orcidid" in credit and credit["orcidid"] is not None:
                                if "contributor" not in entry:
                                    entry["contributor"] = {
                                        "@id": credit["orcidid"],
                                        "@type": sType,
                                    }
                                else:
                                    entry["contributor"].append(
                                        {
                                            "@id": credit["orcidid"],
                                            "@type": sType,
                                        }
                                    )
                            elif "name" in credit and credit["name"] is not None:
                                if "contributor" not in entry:
                                    entry["contributor"] = [credit["name"]]
                                else:
                                    entry["contributor"].append(credit["name"])
                        else:
                            if "name" in credit and credit["name"] is not None:
                                if "contributor" not in entry:
                                    entry["contributor"] = [credit["name"]]
                                else:
                                    entry["contributor"].append(credit["name"])

                    if "Primary contact" in credit["typeRole"]:
                        # print("**** CONTRIBUTOR ****")
                        # print(credit['name'])

                        if credit.get("typeEntity"):
                            if "Person" in credit["typeEntity"]:
                                sType = "sc:Person"
                            else:
                                sType = "sc:Organization"

                            if "orcidid" in credit and credit["orcidid"] is not None:
                                if "primaryContact" not in entry:
                                    entry["primaryContact"] = {
                                        "@id": credit["orcidid"],
                                        "@type": sType,
                                    }
                                else:
                                    entry["primaryContact"].append(
                                        {
                                            "@id": credit["orcidid"],
                                            "@type": sType,
                                        }
                                    )
                            elif "name" in credit and credit["name"] is not None:
                                if "primaryContact" not in entry:
                                    entry["primaryContact"] = [credit["name"]]
                                else:
                                    entry["primaryContact"].append(credit["name"])
                        else:
                            if "name" in credit and credit["name"] is not None:
                                if "primaryContact" not in entry:
                                    entry["primaryContact"] = [credit["name"]]
                                else:
                                    entry["primaryContact"].append(credit["name"])

        if entry.get("publication"):
            for publication in entry["publication"]:
                if publication.get("pmid"):
                    if "hasPublication" not in entry:
                        # entry['hasPublication'] = [{"@id": 'pubmed:' + publication['pmid']}]
                        entry["hasPublication"] = ["pubmed:" + publication["pmid"]]
                    else:
                        # entry['hasPublication'].append({"@id": 'pubmed:' + publication['pmid']})
                        entry["hasPublication"].append("pubmed:" + publication["pmid"])
                if publication.get("pmcid"):
                    if "hasPublication" not in entry:
                        entry["hasPublication"] = ["pmcid:" + publication["pmcid"]]
                    else:
                        entry["hasPublication"].append("pmcid:" + publication["pmcid"])
                if publication.get("doi") and not (
                    "<" in publication["doi"] or ">" in publication["doi"]
                ):
                    publication["doi"] = publication["doi"].replace("[", "%5B")
                    publication["doi"] = publication["doi"].replace("]", "%5D")
                    if "hasPublication" not in entry:
                        entry["hasPublication"] = [
                            {
                                "@id": "https://doi.org/" + publication["doi"],
                                "@type": "sc:CreativeWork",
                            }
                        ]
                    else:
                        entry["hasPublication"].append(
                            {
                                "@id": "https://doi.org/" + publication["doi"],
                                "@type": "sc:CreativeWork",
                            }
                        )

        if entry.get("function"):
            for item in entry["function"]:
                if item.get("operation"):
                    for op in item["operation"]:
                        if "hasOperation" not in entry:
                            entry["hasOperation"] = [{"@id": op["uri"]}]
                        else:
                            entry["hasOperation"].append({"@id": op["uri"]})

                if item.get("input"):
                    for input in item["input"]:
                        input_object = {
                            "@type": "bsct:FormalParameter",
                            "name": input["data"]["term"],
                            "additionalType": {"@id": input["data"]["uri"]},
                            "encodingFormat": [],
                        }
                        if input.get("format"):
                            for f in input["format"]:
                                input_object["encodingFormat"].append({"@id": f["uri"]})
                        if "hasInputData" not in entry:
                            entry["hasInputData"] = [input_object]
                        else:
                            entry["hasInputData"].append(input_object)

                if item.get("output"):
                    for output in item["output"]:
                        output_object = {
                            "@type": "bsct:FormalParameter",
                            "name": output["data"]["term"],
                            "additionalType": {"@id": output["data"]["uri"]},
                            "encodingFormat": [],
                        }
                        if output.get("format"):
                            for f in output["format"]:
                                output_object["encodingFormat"].append(
                                    {"@id": f["uri"]}
                                )
                        if "hasOutputData" not in entry:
                            entry["hasOutputData"] = [output_object]
                        else:
                            entry["hasOutputData"].append(output_object)

        if entry.get("topic"):
            for item in entry["topic"]:
                if "hasTopic" not in entry:
                    entry["hasTopic"] = [{"@id": item["uri"]}]
                else:
                    entry["hasTopic"].append({"@id": item["uri"]})

        if entry.get("cost"):
            for item in entry["cost"]:
                if "isAccessibleForFree" not in entry:
                    if "Free" in entry["cost"]:
                        entry["isAccessibleForFree"] = True
                    else:
                        entry["isAccessibleForFree"] = False

        if entry.get("documentation"):
            for item in entry["documentation"]:
                if item.get("type"):
                    item["url"] = item["url"].replace("|", "%7C")
                    if "app.gitter.im" in item["url"]:
                        continue
                    if "API" in item["type"]:
                        if "hasApiDoc" not in entry:
                            entry["hasApiDoc"] = [{"@id": item["url"]}]
                        else:
                            entry["hasApiDoc"].append({"@id": item["url"]})
                    elif "Terms" in item["type"]:
                        if "hasTermsOfUse" not in entry:
                            entry["hasTermsOfUse"] = [{"@id": item["url"]}]
                        else:
                            entry["hasTermsOfUse"].append({"@id": item["url"]})
                    else:
                        if "hasGenDoc" not in entry:
                            entry["hasGenDoc"] = [{"@id": item["url"]}]
                        else:
                            entry["hasGenDoc"].append({"@id": item["url"]})

    except KeyError as e:
        print(e)
    raw_jld = json.dumps(entry, indent=4, sort_keys=True)
    return raw_jld


def get_biotools_files_in_repo():
    tools = sorted(glob.glob(r"../../content/data/*/*.biotools.json"))
    print(f"found {len(tools)} bio.tools descriptors")
    with open(
        "../../content/datasets/biotools_bioschemas_files_list.txt",
        "w",
        encoding="utf-8",
    ) as f:
        f.writelines(f"{tool}\n" for tool in tools)
    return tools


def process_tools():
    """
    Go through all bio.tools entries and produce a single RDF file.
    """
    tool_files = get_biotools_files_in_repo()
    rdf_graph = Graph()

    for tool_file in tool_files:
        with open(tool_file, encoding="utf-8") as fh:
            tool = json.load(fh)
        rdf_graph.parse(data=rdfize(tool), format="json-ld")

    if not tool_files or len(rdf_graph) == 0:
        sys.exit(
            "error: no bio.tools entries converted "
            f"({len(tool_files)} files, {len(rdf_graph)} triples); "
            "refusing to write an empty bioschemas-dump.ttl"
        )

    rdf_graph.serialize(
        format="turtle",
        destination="../../content/datasets/bioschemas-dump.ttl",
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
    process_tools()
