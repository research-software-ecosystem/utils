import argparse
import glob
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.metadata import normalize_version_fields

TESS_BASE = "https://tess.elixir-europe.org"
PER_PAGE = 100


def clean(data_base="."):
    data_glob = os.path.join(data_base, "data/*/*.tess.json")
    for data_file in glob.glob(data_glob):
        os.remove(data_file)
    import_glob = os.path.join(data_base, "imports/tess/*.tess.json")
    for import_file in glob.glob(import_glob):
        os.remove(import_file)


def fetch_page(page):
    url = f"{TESS_BASE}/materials.json?per_page={PER_PAGE}&page={page}"
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            if attempt == 2:
                raise
            print(f"  retrying list fetch page {page} ({e})")
            time.sleep(2 * (attempt + 1))
    return []


def fetch_all_materials(max_items=None):
    materials = []
    page = 1

    while True:
        print(f"  fetching page {page}")
        items = fetch_page(page)
        if not items:
            break
        materials.extend(items)
        page += 1
        time.sleep(0.3)

        if max_items and len(materials) >= max_items:
            materials = materials[:max_items]
            break

    return materials


def fetch_detail(material_id):
    url = f"{TESS_BASE}/materials/{material_id}"
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=30, headers={"Accept": "application/json"})
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            if attempt == 2:
                raise
            print(f"  retrying detail fetch for material {material_id} ({e})")
            time.sleep(2 * (attempt + 1))
    return None


def extract_tool_uri(url):
    """Extract the bio.tools URL from a TeSS external_resource URL.

    TeSS classifies both legacy (https://bio.tools/tool/<name>) and direct
    (https://bio.tools/<name>) URLs as tool resources. Return the canonical
    bio.tools entry URL, or None if the URL does not point to bio.tools.
    """
    parsed = urlparse(url)
    if parsed.netloc not in ("bio.tools", "www.bio.tools"):
        return None
    path = parsed.path.rstrip("/")
    if path.startswith("/tool/"):
        name = path[len("/tool/") :]
    else:
        name = path.lstrip("/")
    if not name:
        return None
    return f"https://bio.tools/{name}"


def extract_tools(item):
    tools = set()
    for res in item.get("external_resources", []):
        if res.get("type") == "tool":
            uri = extract_tool_uri(res.get("url", ""))
            if uri:
                tools.add(uri)
    return sorted(tools)


def name_from_tool_uri(uri):
    """Derive the bio.tools entry name (directory key) from a tool URI."""
    return uri.rstrip("/").rsplit("/", 1)[-1].lower()


def material_slug(url):
    """Derive the material slug (last URL path segment) used as entry id."""
    return url.rstrip("/").rsplit("/", 1)[-1] if url else ""


def build_entry(list_item, detail):
    tools = extract_tools(list_item)
    topics = [
        t.get("preferred_label", "")
        for t in list_item.get("scientific_topics", [])
        if t.get("preferred_label")
    ]
    ops = [
        op.get("preferred_label", "")
        for op in list_item.get("operations", [])
        if op.get("preferred_label")
    ]

    detail_fields = detail or {}

    return {
        "source": "TESS",
        "id": material_slug(list_item.get("url", "")),
        "url": list_item.get("url", ""),
        "title": list_item.get("title", ""),
        "description": list_item.get("description", ""),
        "doi": list_item.get("doi", ""),
        "tools": tools,
        "scientific_topics": topics,
        "operations": ops,
        "resource_type": detail_fields.get("resource_type", []),
        "nodes": detail_fields.get("nodes", []),
        "keywords": detail_fields.get("keywords", []),
        "authors": detail_fields.get("authors", []),
        "contributors": detail_fields.get("contributors", []),
        "licence": detail_fields.get("licence", ""),
        "difficulty_level": detail_fields.get("difficulty_level", ""),
        "target_audience": detail_fields.get("target_audience", []),
        "prerequisites": detail_fields.get("prerequisites", ""),
        "contact": detail_fields.get("contact", ""),
        "date_published": detail_fields.get("date_published", ""),
        "status": detail_fields.get("status", ""),
        "syllabus": detail_fields.get("syllabus", ""),
        "learning_objectives": detail_fields.get("learning_objectives", ""),
        "date_created": list_item.get("remote_created_date", ""),
        "date_updated": list_item.get("remote_updated_date", ""),
    }


def retrieve(max_items=None, data_base="."):
    tess_directory = os.path.join(data_base, "imports", "tess")
    os.makedirs(tess_directory, exist_ok=True)

    print("Fetching training materials from TESS API...")
    all_items = fetch_all_materials(max_items)
    limit_msg = f" (limited to {max_items})" if max_items else ""
    print(f"Found {len(all_items)} training materials{limit_msg}")

    all_entries = []
    tool_uri_to_material_urls = {}
    stat_unique_tools = set()
    stat_resource_types = {}
    stat_nodes = {}

    print("Fetching details...")
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_map = {
            executor.submit(fetch_detail, item["id"]): item for item in all_items
        }
        for future in as_completed(future_map):
            list_item = future_map[future]
            detail = future.result()

            entry = build_entry(list_item, detail)
            all_entries.append(entry)
            material_url = entry.get("url", "")

            wf_cleaned = normalize_version_fields(entry, [])
            save_path = os.path.join(tess_directory, f"{entry['id']}.tess.json")
            with open(save_path, "w") as f:
                json.dump(
                    wf_cleaned, f, sort_keys=True, indent=4, separators=(",", ": ")
                )

            for tool_uri in entry.get("tools", []):
                stat_unique_tools.add(tool_uri)
                tool_uri_to_material_urls.setdefault(tool_uri, []).append(material_url)

            # Stats: resource type
            rt_list = detail.get("resource_type", []) if detail else []
            for rt in rt_list:
                rt_str = str(rt)
                stat_resource_types[rt_str] = stat_resource_types.get(rt_str, 0) + 1

            # Stats: source node
            node_list = detail.get("nodes", []) if detail else []
            for node in node_list:
                node_name = node.get("name", "unknown")
                stat_nodes[node_name] = stat_nodes.get(node_name, 0) + 1

    print(f"\nSaved {len(all_entries)} training material files to imports/tess/")

    matched_count = 0
    material_url_to_tool_uris = {}
    for tool_uri in sorted(tool_uri_to_material_urls.keys()):
        bt_id = name_from_tool_uri(tool_uri)
        directory = os.path.join(data_base, "data", bt_id)
        if not os.path.isdir(directory):
            continue

        material_urls = sorted(set(tool_uri_to_material_urls[tool_uri]))

        for material_url in material_urls:
            material_url_to_tool_uris.setdefault(material_url, []).append(tool_uri)

        data_save_path = os.path.join(directory, f"{bt_id}.tess.json")
        with open(data_save_path, "w") as f:
            json.dump(
                material_urls, f, sort_keys=True, indent=4, separators=(",", ": ")
            )
        print(
            f"matched tool #{matched_count + 1}: {bt_id} ({len(material_urls)} trainings)"
        )
        matched_count += 1

    for entry in all_entries:
        entry["mapped_tools"] = sorted(
            material_url_to_tool_uris.get(entry.get("url", ""), [])
        )
        save_path = os.path.join(tess_directory, f"{entry['id']}.tess.json")
        with open(save_path, "w") as f:
            json.dump(entry, f, sort_keys=True, indent=4, separators=(",", ": "))

    print(f"\nTotal tools matched in RSEc content: {matched_count}")
    print("\nStats:")
    print(f"  training materials processed: {len(all_entries)}")
    print(f"  unique tool URIs found: {len(stat_unique_tools)}")
    print(f"  unique tools that hit data/ dir: {matched_count}")
    print("\n  Resource type distribution:")
    for rt in sorted(
        stat_resource_types.keys(),
        key=lambda r: stat_resource_types[r],
        reverse=True,
    ):
        count = stat_resource_types[rt]
        pct = count / len(all_entries) * 100
        print(f"    {rt}: {count} ({pct:.0f}%)")
    print("\n  Source node distribution:")
    for node in sorted(
        stat_nodes.keys(),
        key=lambda n: stat_nodes[n],
        reverse=True,
    ):
        count = stat_nodes[node]
        pct = count / len(all_entries) * 100
        print(f"    {node}: {count} ({pct:.0f}%)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Import training materials from TESS API"
    )
    parser.add_argument(
        "--test",
        type=int,
        nargs="?",
        const=100,
        default=None,
        help="Run with a limited number of materials (default: 100)",
    )
    parser.add_argument(
        "--content-dir",
        type=str,
        default=".",
        help="Path to the content directory containing a data/ subfolder (default: current dir)",
    )
    args = parser.parse_args()

    clean(data_base=args.content_dir)
    retrieve(max_items=args.test, data_base=args.content_dir)
