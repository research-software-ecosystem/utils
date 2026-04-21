from rdflib import ConjunctiveGraph
import xml.etree.ElementTree as ET
import requests

#from tqdm.notebook import tqdm

# Get all workflow URLs from the sitemap https://workflowhub.eu/sitemaps/workflows.xml
# fetch the sitemap and parse it to extract workflow URLs
response = requests.get("https://workflowhub.eu/sitemaps/workflows.xml")
sitemap_data = response.text
# write file on disk
with open("workflows_sitemap.xml", "w") as f:
    f.write(sitemap_data)


def parse_sitemap(xml_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()

    # Detect namespace if present
    ns_uri = root.tag.split("}")[0].strip("{") if "}" in root.tag else ""
    ns = {"sm": ns_uri} if ns_uri else {}

    urls = []

    # Case 1: regular sitemap (<urlset>)
    if root.tag.endswith("urlset"):
        for u in root.findall("sm:url" if ns else "url", ns):
            loc = u.find("sm:loc" if ns else "loc", ns)
            lastmod = u.find("sm:lastmod" if ns else "lastmod", ns)
            urls.append(
                {
                    "loc": loc.text.strip() if loc is not None and loc.text else None,
                    "lastmod": (
                        lastmod.text.strip()
                        if lastmod is not None and lastmod.text
                        else None
                    ),
                }
            )

    # Case 2: sitemap index (<sitemapindex>)
    elif root.tag.endswith("sitemapindex"):
        for s in root.findall("sm:sitemap" if ns else "sitemap", ns):
            loc = s.find("sm:loc" if ns else "loc", ns)
            lastmod = s.find("sm:lastmod" if ns else "lastmod", ns)
            urls.append(
                {
                    "sitemap": (
                        loc.text.strip() if loc is not None and loc.text else None
                    ),
                    "lastmod": (
                        lastmod.text.strip()
                        if lastmod is not None and lastmod.text
                        else None
                    ),
                }
            )

    return urls




def retrieve_rdf(url):
    FC_get_md = (
        "https://fair-checker.france-bioinformatique.fr/api/inspect/get_rdf_metadata"
    )
    kg = ConjunctiveGraph()
    res = requests.get(url=FC_get_md, params={"url": url})
    try:
        kg.parse(data=res.text, format="json-ld")
    except Exception as e:
        print(e)
    print(f"Loaded {len(kg)} RDF triples from {url}")
    return kg


if __name__ == "__main__":
    data = parse_sitemap("workflows_sitemap.xml")
    print("entries:", len(data))
    #print(data[:3])

    merged_kg = ConjunctiveGraph()
    counter = 0
    for url in data[1:500]:
        #print(url)
        kg = retrieve_rdf(url["loc"])
        #print(f"KG has {len(kg)} triples")
        merged_kg += kg
        counter += 1
        print(counter)

    print(f"Final merged KG has {len(merged_kg)} triples")

    merged_kg.serialize(destination="content/datasets/workflowhub-dump.ttl", format="turtle")

