import argparse
import glob
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

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
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()


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
    resp = requests.get(url, timeout=30, headers={"Accept": "application/json"})
    if resp.status_code != 200:
        return None
    return resp.json()


def extract_tools(item):
    tools = set()
    for res in item.get("external_resources", []):
        if res.get("type") == "tool":
            url = res.get("url", "")
            if url.startswith("https://bio.tools/tool/"):
                bt = url.replace("https://bio.tools/tool/", "").strip()
                if bt:
                    tools.add(bt.lower())
    return list(tools)


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

    resource_type = detail.get("resource_type", []) if detail else []
    nodes = detail.get("nodes", []) if detail else []
    keywords = detail.get("keywords", []) if detail else []

    return {
        "source": "TESS",
        "id": list_item["id"],
        "url": list_item.get("url", ""),
        "title": list_item.get("title", ""),
        "description": list_item.get("description", ""),
        "doi": list_item.get("doi", ""),
        "tools": tools,
        "scientific_topics": topics,
        "operations": ops,
        "resource_type": resource_type,
        "nodes": nodes,
        "keywords": keywords,
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
    tool_to_mids = {}
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
            mid = list_item["id"]
            detail = future.result()

            entry = build_entry(list_item, detail)
            all_entries.append(entry)

            wf_cleaned = normalize_version_fields(entry, [])
            save_path = os.path.join(tess_directory, f"{mid}.tess.json")
            with open(save_path, "w") as f:
                json.dump(
                    wf_cleaned, f, sort_keys=True, indent=4, separators=(",", ": ")
                )

            for tool_name in entry.get("tools", []):
                stat_unique_tools.add(tool_name)
                if tool_name not in tool_to_mids:
                    tool_to_mids[tool_name] = []
                tool_to_mids[tool_name].append(mid)

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
    mid_to_data_tools = {}
    for bt_id in sorted(tool_to_mids.keys()):
        directory = os.path.join(data_base, "data", bt_id)
        if not os.path.isdir(directory):
            continue

        mids = sorted(set(tool_to_mids[bt_id]))

        for mid in mids:
            mid_to_data_tools.setdefault(mid, []).append(bt_id)

        data_save_path = os.path.join(directory, f"{bt_id}.tess.json")
        with open(data_save_path, "w") as f:
            json.dump(mids, f, sort_keys=True, indent=4, separators=(",", ": "))
        print(f"matched tool #{matched_count + 1}: {bt_id} ({len(mids)} trainings)")
        matched_count += 1

    for entry in all_entries:
        mid = entry["id"]
        if mid in mid_to_data_tools:
            entry["mapped_tools"] = sorted(mid_to_data_tools[mid])
            save_path = os.path.join(tess_directory, f"{mid}.tess.json")
            with open(save_path, "w") as f:
                json.dump(
                    entry, f, sort_keys=True, indent=4, separators=(",", ": ")
                )

    print(f"\nTotal tools matched in RSEc content: {matched_count}")
    print("\nStats:")
    print(f"  training materials processed: {len(all_entries)}")
    print(f"  unique tool names found: {len(stat_unique_tools)}")
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
