import argparse
import glob
import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.metadata import normalize_version_fields

TESS_BASE = "https://tess.elixir-europe.org"
PER_PAGE = 100


def clean():
    for data_file in glob.glob(r"data/*/*.tess.json"):
        os.remove(data_file)
    for import_file in glob.glob(r"imports/tess/*.tess.json"):
        os.remove(import_file)


def fetch_all_materials(max_items=None):
    materials = []
    page = 1

    while True:
        url = f"{TESS_BASE}/materials.json?per_page={PER_PAGE}&page={page}"
        print(f"  fetching page {page}")
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        items = resp.json()
        if not items:
            break
        materials.extend(items)
        page += 1
        time.sleep(0.3)

        if max_items and len(materials) >= max_items:
            materials = materials[:max_items]
            break

    return materials


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


def build_entry(item):
    tools = extract_tools(item)
    topics = [
        t.get("preferred_label", "")
        for t in item.get("scientific_topics", [])
        if t.get("preferred_label")
    ]
    ops = [
        op.get("preferred_label", "")
        for op in item.get("operations", [])
        if op.get("preferred_label")
    ]

    return {
        "source": "TESS",
        "id": item["id"],
        "url": item.get("url", ""),
        "title": item.get("title", ""),
        "description": item.get("description", ""),
        "doi": item.get("doi", ""),
        "tools": tools,
        "scientific_topics": topics,
        "operations": ops,
        "date_created": item.get("remote_created_date", ""),
        "date_updated": item.get("remote_updated_date", ""),
    }


def retrieve(max_items=None):
    tess_directory = os.path.join("imports", "tess")
    os.makedirs(tess_directory, exist_ok=True)

    print("Fetching training materials from TESS API...")
    all_items = fetch_all_materials(max_items)
    limit_msg = f" (limited to {max_items})" if max_items else ""
    print(f"Found {len(all_items)} training materials{limit_msg}")

    all_entries = []
    tool_to_mids = {}
    stat_unique_tools = set()

    for i, item in enumerate(all_items, 1):
        mid = item["id"]
        print(f"processing {i}/{len(all_items)}: {mid}")

        entry = build_entry(item)
        all_entries.append(entry)

        wf_cleaned = normalize_version_fields(entry, [])
        save_path = os.path.join(tess_directory, f"{mid}.tess.json")
        with open(save_path, "w") as f:
            json.dump(wf_cleaned, f, sort_keys=True, indent=4, separators=(",", ": "))

        for tool_name in entry.get("tools", []):
            stat_unique_tools.add(tool_name)
            if tool_name not in tool_to_mids:
                tool_to_mids[tool_name] = []
            tool_to_mids[tool_name].append(mid)

    print(f"\nSaved {len(all_entries)} training material files to imports/tess/")

    matched_count = 0
    for bt_id in sorted(tool_to_mids.keys()):
        directory = os.path.join("data", bt_id)
        if not os.path.isdir(directory):
            continue

        mids = sorted(set(tool_to_mids[bt_id]))
        data_save_path = os.path.join(directory, f"{bt_id}.tess.json")
        with open(data_save_path, "w") as f:
            json.dump(mids, f, sort_keys=True, indent=4, separators=(",", ": "))
        print(f"matched tool #{matched_count + 1}: {bt_id} ({len(mids)} trainings)")
        matched_count += 1

    print(f"\nTotal tools matched in RSEc content: {matched_count}")
    print("\nStats:")
    print(f"  training materials processed: {len(all_entries)}")
    print(f"  unique tool names found: {len(stat_unique_tools)}")
    print(f"  unique tools that hit data/ dir: {matched_count}")


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
    args = parser.parse_args()

    clean()
    retrieve(max_items=args.test)
