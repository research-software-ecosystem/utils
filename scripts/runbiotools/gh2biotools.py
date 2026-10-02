#!/usr/bin/env python3
import os
import json
import logging
import argparse
import requests
from boltons.iterutils import remap

HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}
HOST = "https://bio.tools"
TOOL_API_URL = f"{HOST}/api/tool/"

logging.basicConfig(level=logging.INFO)


def drop_edam_labels(payload):
    """Return `payload` with every EDAM label removed, keeping the URIs.

    bio.tools derives the term from the URI against its own copy of EDAM, and
    only compares a submitted term when one is given. From its validator:

        # URI takes precedence over term, so if URI matches the one found in
        # EDAM we replace the term with the one from EDAM (EDAM is assumed to
        # have the correct term)
        if term and term.lower().strip() != found["data"]["text"].lower() ...:
            raise serializers.ValidationError("The term does not match the URI")
        self.term = found["data"]["text"]

    So the label we send is redundant when it is right and fatal when it is
    stale. EDAM 1.25-20260626 renamed a batch of high-level terms -- Formatting
    to Data formatting, Analysis to Data analysis, Lipids to Lipidomics -- and
    bio.tools still serves the old labels from its own database while rejecting
    them on write. Ten such pairs caused 104 of the 319 validation failures in
    the 2026-09-30 import.

    Re-deriving the labels ourselves was the obvious alternative and is worse:
    bio.tools loads EDAM from a database table, so its version is not something
    we can query, and matching a published release would only be a guess at it.
    The one system that knows which EDAM bio.tools uses is bio.tools.

    The `uri` guard matters. A term with no URI is the only thing identifying
    the concept, and dropping it fails with "Either the URI or term is
    required."
    """

    def visit(path, key, value):
        if isinstance(value, dict) and value.get("uri") and "term" in value:
            return key, {k: v for k, v in value.items() if k != "term"}
        return key, value

    return remap(payload, visit=visit)


def validate_upload_tool(tool, headers):
    url = f"{HOST}/api/tool/validate/"
    response = requests.post(url, headers=headers, data=json.dumps(tool))

    if not response.ok:
        logging.error(
            f"Error validating upload for {tool['biotoolsID']}: {response.status_code} {response.text}"
        )
    return response.ok


def upload_tool(tool, headers):
    url = TOOL_API_URL

    response = requests.post(url, headers=headers, data=json.dumps(tool))
    return response.ok


def validate_update_tool(tool, tool_id, headers):
    url = f"{HOST}/api/{tool_id}/validate/"
    response = requests.put(url, headers=headers, data=json.dumps(tool))

    if not response.ok:
        logging.error(
            f"Error validating update for {tool['biotoolsID']}: {response.status_code} {response.text}"
        )
    return response.ok


def update_tool(tool, headers):
    """Updates an existing tool on bio.tools."""
    url = f"{TOOL_API_URL}{tool['biotoolsID']}/"

    response = requests.put(url, headers=headers, data=json.dumps(tool))
    return response.ok


def process_single_file(file, headers, validate_only=False):
    """
    Process a single tool file.
    returns tool_id, status
    status can be "uploaded", "updated", "unchanged", "failed", "failed_validation", "failed_upload" or "failed_update"

    With validate_only, nothing is written: a record that validates is counted
    as it would have been applied. Useful for checking a batch before pushing
    it, and for confirming a change to what gets sent without touching live
    records.
    """
    payload_dict = drop_edam_labels(json.load(file))
    tool_id = payload_dict.get("biotoolsID")

    if not tool_id:
        logging.error(f"'biotoolsID' not found in {file}")
        return "UNKNOWN", "failed"

    # check if tool exists
    tool_url = f"{HOST}/api/tool/{tool_id}/"
    response = requests.get(tool_url, headers=headers)

    if response.status_code == 200:
        # remove empty fields, and the labels from the stored record: the
        # payload already has none, so leaving them here would make every
        # EDAM-annotated tool differ and be rewritten on every run. Change
        # detection keys on the URIs, which is what identifies the concept.
        existing_tool = drop_edam_labels(
            remap(response.json(), lambda p, k, v: bool(v))
        )
        payload_dict = remap(payload_dict, lambda p, k, v: bool(v))

        if existing_tool == payload_dict:
            return tool_id, "unchanged"

        valid = validate_update_tool(payload_dict, tool_id, headers)
        if not valid:
            return tool_id, "failed_validation"

        if validate_only:
            return tool_id, "updated"

        success = update_tool(payload_dict, headers)

        return tool_id, "updated" if success else "failed_update"

    elif response.status_code == 404:
        # tool not registered, proceed with upload
        logging.info(f"Tool {tool_id} not registered, proceeding with upload")
        valid = validate_upload_tool(payload_dict, headers)

        if not valid:
            return tool_id, "failed_validation"

        if validate_only:
            return tool_id, "uploaded"

        success = upload_tool(payload_dict, headers)

        return tool_id, "uploaded" if success else "failed_upload"

    else:
        logging.error(
            f"Error retrieving tool {tool_id}: {response.status_code} {response.text}"
        )
        return tool_id, "failed"


def print_summary(results):
    """Print a summary of the upload results."""
    logging.info("---------------------------")
    logging.info("SUMMARY")
    logging.info(f"Tools uploaded: {len(results['uploaded'])}")
    logging.info(f"Tools updated: {len(results['updated'])}")
    logging.info(f"Tools unchanged: {len(results['unchanged'])}")
    logging.info(f"Tools failed: {len(results['failed'])}")
    logging.info(f"Tools failed validation: {len(results['failed_validation'])}")
    logging.info(
        f"Tools failed upload after validation: {len(results['failed_upload'])}"
    )
    logging.info(
        f"Tools failed update after validation: {len(results['failed_update'])}"
    )

    if results["uploaded"]:
        logging.info(f"Uploaded tools: {', '.join(results['uploaded'])}")
    if results["updated"]:
        logging.info(f"Updated tools: {', '.join(results['updated'])}")
    if results["failed"]:
        logging.error(f"Failed tools: {', '.join(results['failed'])}")
    if results["failed_validation"]:
        logging.error(
            f"Failed validation tools: {', '.join(results['failed_validation'])}"
        )
    if results["failed_upload"]:
        logging.error(f"Failed upload tools: {', '.join(results['failed_upload'])}")
    if results["failed_update"]:
        logging.error(f"Failed update tools: {', '.join(results['failed_update'])}")


def run_upload(files, validate_only=False):
    token = os.environ.get("BIOTOOLS_API_TOKEN")
    if not token:
        logging.error("Missing BIOTOOLS_API_TOKEN. Aborting upload.")
        raise SystemExit(1)

    headers = {**HEADERS, "Authorization": f"Token {token}"}
    results = {
        "uploaded": [],
        "updated": [],
        "unchanged": [],
        "failed": [],
        "failed_validation": [],
        "failed_upload": [],
        "failed_update": [],
    }

    if validate_only:
        logging.info("validate-only: nothing will be written to bio.tools")

    for json_file in files:
        with open(json_file, "r") as file:
            tool_id, status = process_single_file(file, headers, validate_only)
            results[status].append(tool_id)

    print_summary(results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Sync changed .biotools.json files with bio.tools server"
    )

    parser.add_argument(
        "--files",
        metavar="F",
        type=str,
        nargs="+",
        help="List of changed/created .biotools.json files to process",
    )

    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate against bio.tools without uploading or updating anything",
    )

    args = parser.parse_args()

    if args.files:
        run_upload(args.files, args.validate_only)
