import argparse
import glob
import json
import os
import sys
import time


import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.metadata import normalize_version_fields

WORKFLOWHUB_BASE = "https://workflowhub.eu"
PER_PAGE = 100


def clean(data_base="."):
    data_glob = os.path.join(data_base, "data/*/*.workflowhub.json")
    for data_file in glob.glob(data_glob):
        os.remove(data_file)
    import_glob = os.path.join(data_base, "imports/workflowhub/*.workflowhub.json")
    for import_file in glob.glob(import_glob):
        os.remove(import_file)


def fetch_all_workflow_ids(max_workflows=None):
    """Paginate through WorkflowHub list to get all workflow IDs."""
    ids = []
    page = 1

    while True:
        url = f"{WORKFLOWHUB_BASE}/workflows.json?page={page}&per_page={PER_PAGE}"
        print(f"  fetching page {page}")
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        for item in data.get("data", []):
            ids.append(item["id"])

        next_url = data.get("links", {}).get("next")
        if not next_url:
            break
        page += 1
        time.sleep(0.3)

        if max_workflows and len(ids) >= max_workflows:
            ids = ids[:max_workflows]
            break

    return ids


def shorten_tool_id(tool):
    """Shorten a tool ID to its base name, matching shared.shorten_tool_id."""
    if "toolshed" in tool:
        return tool.split("/")[-2]
    return tool


def fetch_workflow_detail(workflow_id):
    """Fetch detailed workflow JSON."""
    url = f"{WORKFLOWHUB_BASE}/workflows/{workflow_id}.json"
    resp = requests.get(url, timeout=30)
    if resp.status_code != 200:
        print(f"  WARNING: failed to fetch workflow {workflow_id}: {resp.status_code}")
        return None
    return resp.json()


def extract_tools_from_detail(attr):
    """Extract tools from both curated annotations and Galaxy internals.steps."""
    tools = set()

    # Source 1: curated bio.tools annotations from the tools field
    for t in attr.get("tools", []):
        name = t.get("name", "").strip()
        if name:
            tools.add(name.lower())
        tid = t.get("id", "")
        if tid.startswith("https://bio.tools/"):
            bt = tid.replace("https://bio.tools/", "").strip()
            if bt:
                tools.add(bt.lower())

    # Source 2: Galaxy tool IDs from step descriptions
    internals = attr.get("internals", {})
    steps = internals.get("steps")
    if steps is not None:
        for step in steps:
            desc = step.get("description")
            if desc is not None:
                tools.add(shorten_tool_id(desc).lower())

    return list(tools)


def build_workflow_entry(wf_id, attr):
    """Build a workflow entry matching galaxy_codex Workflow class format."""
    versions = attr.get("versions", [])
    latest_version = attr.get("latest_version") or (len(versions) if versions else 1)

    last_version = versions[-1] if versions else {}
    doi = attr.get("doi") or ""
    if not doi and last_version:
        doi = last_version.get("doi") or ""

    wf_link = f"{WORKFLOWHUB_BASE}/workflows/{wf_id}?version={latest_version}"

    creators = []
    for c in attr.get("creators", []):
        parts = []
        if c.get("given_name"):
            parts.append(c["given_name"])
        if c.get("family_name"):
            parts.append(c["family_name"])
        if parts:
            creators.append(" ".join(parts))
    other = attr.get("other_creators", "")
    if other:
        creators.append(other)

    edam_operations = [
        op["label"] for op in attr.get("operation_annotations", []) if op.get("label")
    ]
    edam_topics = [
        t["label"] for t in attr.get("topic_annotations", []) if t.get("label")
    ]
    tags = [w.lower() for w in attr.get("tags", [])]

    internals = attr.get("internals", {})
    steps = internals.get("steps")
    number_of_steps = len(steps) if steps else 0

    tools = extract_tools_from_detail(attr)

    workflow_class = attr.get("workflow_class", {})
    engine = workflow_class.get("title", "") if workflow_class else ""

    return {
        "source": "WorkflowHub",
        "id": wf_id,
        "link": wf_link,
        "name": attr.get("title", ""),
        "description": attr.get("description", ""),
        "creators": creators,
        "tags": tags,
        "create_time": (attr.get("created_at") or "").split("T")[0],
        "update_time": (attr.get("updated_at") or "").split("T")[0],
        "latest_version": latest_version,
        "versions": len(versions) if versions else 1,
        "number_of_steps": number_of_steps,
        "tools": tools,
        "discussion_links": attr.get("discussion_links", []),
        "content_blobs": attr.get("content_blobs", []),
        "edam_operation": edam_operations,
        "edam_topic": edam_topics,
        "license": attr.get("license", ""),
        "doi": doi,
        "workflow_class": engine,
        "projects": [],
    }


def retrieve(max_workflows=None, data_base="."):
    workflowhub_directory = os.path.join(data_base, "imports", "workflowhub")
    os.makedirs(workflowhub_directory, exist_ok=True)

    # Load galaxy_codex tools for Suite ID → bio.tool ID mapping
    print("Loading galaxy_codex tools...")
    resp = requests.get(
        "https://raw.githubusercontent.com/galaxyproject/galaxy_codex/refs/heads/main/communities/all/resources/tools.json",
        timeout=30,
    )
    galaxy_tools = json.loads(resp.text)

    tool_to_biotool = {}
    for tool in galaxy_tools:
        suite_id = tool.get("Suite ID")
        biotool_id = tool.get("bio.tool ID")
        if suite_id and biotool_id:
            tool_to_biotool[suite_id.lower()] = biotool_id.lower()

    print(f"Loaded {len(tool_to_biotool)} Suite ID → bio.tool ID mappings")
    print("Fetching workflow list from WorkflowHub API...")

    workflow_ids = fetch_all_workflow_ids(max_workflows)
    limit_msg = f" (limited to {max_workflows})" if max_workflows else ""
    print(f"Found {len(workflow_ids)} workflows{limit_msg}")

    all_entries = []
    tool_to_wf_ids = {}
    stat_mapped = 0
    stat_fallback = 0
    stat_unique_tools = set()
    stat_engines = {}
    stat_engine_tools = {}

    for i, wf_id in enumerate(workflow_ids, 1):
        print(f"fetching {i}/{len(workflow_ids)}: {wf_id}")
        detail = fetch_workflow_detail(wf_id)
        if not detail:
            continue

        attr = detail.get("data", {}).get("attributes", {})
        entry = build_workflow_entry(wf_id, attr)
        all_entries.append(entry)

        wf_cleaned = normalize_version_fields(entry, ["latest_version", "versions"])
        save_path = os.path.join(workflowhub_directory, f"{wf_id}.workflowhub.json")
        with open(save_path, "w") as f:
            json.dump(wf_cleaned, f, sort_keys=True, indent=4, separators=(",", ": "))

        # Map each workflow tool to bio.tool ID and record the workflow ID
        for tool_name in entry.get("tools", []):
            bt_id = tool_to_biotool.get(tool_name.lower())
            if bt_id:
                stat_mapped += 1
            else:
                bt_id = tool_name.lower()
                stat_fallback += 1
            stat_unique_tools.add(bt_id)
            if bt_id not in tool_to_wf_ids:
                tool_to_wf_ids[bt_id] = []
            tool_to_wf_ids[bt_id].append(wf_id)

        engine = entry.get("workflow_class", "unknown") or "unknown"
        stat_engines[engine] = stat_engines.get(engine, 0) + 1
        if engine not in stat_engine_tools:
            stat_engine_tools[engine] = set()
        stat_engine_tools[engine].update(entry.get("tools", []))

        time.sleep(0.2)

    print(f"\nSaved {len(all_entries)} workflow files to imports/workflowhub/")

    # Write per-tool workflowhub JSONs — store only workflow IDs
    matched_count = 0
    wf_id_to_data_tools = {}
    for bt_id in sorted(tool_to_wf_ids.keys()):
        directory = os.path.join(data_base, "data", bt_id)
        if not os.path.isdir(directory):
            continue

        wf_ids = sorted(set(tool_to_wf_ids[bt_id]))

        for wf_id in wf_ids:
            wf_id_to_data_tools.setdefault(wf_id, []).append(bt_id)

        data_save_path = os.path.join(directory, f"{bt_id}.workflowhub.json")
        with open(data_save_path, "w") as f:
            json.dump(wf_ids, f, sort_keys=True, indent=4, separators=(",", ": "))
        print(f"matched tool #{matched_count + 1}: {bt_id} ({len(wf_ids)} workflows)")
        matched_count += 1

    for entry in all_entries:
        wf_id = entry["id"]
        if wf_id in wf_id_to_data_tools:
            entry["mapped_tools"] = sorted(wf_id_to_data_tools[wf_id])
            save_path = os.path.join(workflowhub_directory, f"{wf_id}.workflowhub.json")
            with open(save_path, "w") as f:
                json.dump(
                    entry, f, sort_keys=True, indent=4, separators=(",", ": ")
                )

    print(f"\nTotal tools matched in RSEc content: {matched_count}")
    print("\nStats:")
    print(f"  workflows processed: {len(all_entries)}")
    print(f"  unique tool names found: {len(stat_unique_tools)}")
    print(f"  tool occurrences via galaxy_codex mapping: {stat_mapped}")
    print(f"  tool occurrences via raw-name fallback: {stat_fallback}")
    print(f"  unique tools that hit data/ dir: {matched_count}")
    print("\n  Workflow engine distribution:")
    for engine in sorted(
        stat_engines.keys(), key=lambda e: stat_engines[e], reverse=True
    ):
        wf_count = stat_engines[engine]
        tool_count = len(stat_engine_tools[engine])
        pct = wf_count / len(all_entries) * 100
        print(f"    {engine}: {wf_count} workflows ({pct:.0f}%), {tool_count} tools")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Import workflows from WorkflowHub API"
    )
    parser.add_argument(
        "--test",
        type=int,
        nargs="?",
        const=100,
        default=None,
        help="Run with a limited number of workflows (default: 100)",
    )
    parser.add_argument(
        "--content-dir",
        type=str,
        default=".",
        help="Path to the content directory containing a data/ subfolder (default: current dir)",
    )
    args = parser.parse_args()

    clean(data_base=args.content_dir)
    retrieve(max_workflows=args.test, data_base=args.content_dir)
