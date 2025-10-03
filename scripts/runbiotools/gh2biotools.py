#!/usr/bin/env python3
import os
import json
import logging
import argparse
import requests
from boltons.iterutils import remap

HEADERS = {'Content-Type': 'application/json', 'Accept': 'application/json'}
HOST = 'https://bio.tools'
TOOL_API_URL = f'{HOST}/api/tool/'

logging.basicConfig(level=logging.INFO)   


def validate_upload_tool(tool, headers):
    url = f'{HOST}/api/tool/validate/'
    response = requests.post(url, headers=headers, data=json.dumps(tool))

    if not response.ok:
        logging.error(f"Error validating upload for {tool['biotoolsID']}: {response.status_code} {response.text}")
    return response.ok

def upload_tool(tool, headers):
    url = TOOL_API_URL

    response = requests.post(url, headers=headers, data=json.dumps(tool))
    return response.ok

def validate_update_tool(tool, tool_id, headers):
    url = f'{HOST}/api/{tool_id}/validate/'
    response = requests.put(url, headers=headers, data=json.dumps(tool))

    if not response.ok:
        logging.error(f"Error validating update for {tool['biotoolsID']}: {response.status_code} {response.text}")
    return response.ok

def update_tool(tool, headers):
    """Updates an existing tool on bio.tools."""
    url = f"{TOOL_API_URL}{tool['biotoolsID']}/"

    response = requests.put(url, headers=headers, data=json.dumps(tool))
    return response.ok
    

def process_single_file(file, headers):
    """
    Process a single tool file.
    returns tool_id, status
    status can be "uploaded", "updated", "unchanged", "failed", "failed_validation", "failed_upload" or "failed_update"
    """
    payload_dict = json.load(file)
    tool_id = payload_dict.get("biotoolsID")

    if not tool_id:
        logging.error(f"'biotoolsID' not found in {file}")
        return "UNKNOWN", "failed"
    
    # check if tool exists
    tool_url = f"{HOST}/api/tool/{tool_id}/"
    response = requests.get(tool_url, headers=headers)

    if response.status_code == 200:
        # remove empty fields
        existing_tool = remap(response.json(), lambda p, k, v: bool(v))
        payload_dict = remap(payload_dict, lambda p, k, v: bool(v))

        if existing_tool == payload_dict:
            return tool_id, "unchanged"

        valid = validate_update_tool(payload_dict, tool_id, headers)
        if not valid:
            return tool_id, "failed_validation"

        success = update_tool(payload_dict, headers)

        return tool_id, "updated" if success else "failed_update"

    elif response.status_code == 404:
        # tool not registered, proceed with upload
        logging.info(f'Tool {tool_id} not registered, proceeding with upload')                    
        valid = validate_upload_tool(payload_dict, headers)

        if not valid:
            return tool_id, "failed_validation"

        success = upload_tool(payload_dict, headers)

        return tool_id, "uploaded" if success else "failed_upload"
    
    else:
        logging.error(f"Error retrieving tool {tool_id}: {response.status_code} {response.text}")
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
    logging.info(f"Tools failed upload after validation: {len(results['failed_upload'])}")
    logging.info(f"Tools failed update after validation: {len(results['failed_update'])}")

    if results['uploaded']:
        logging.info(f"Uploaded tools: {', '.join(results['uploaded'])}")
    if results['updated']:
        logging.info(f"Updated tools: {', '.join(results['updated'])}")
    if results['failed']:
        logging.error(f"Failed tools: {', '.join(results['failed'])}")
    if results['failed_validation']:
        logging.error(f"Failed validation tools: {', '.join(results['failed_validation'])}")
    if results['failed_upload']:
        logging.error(f"Failed upload tools: {', '.join(results['failed_upload'])}")
    if results['failed_update']:
        logging.error(f"Failed update tools: {', '.join(results['failed_update'])}")



def run_upload(files):
    token = os.environ.get('BIOTOOLS_API_TOKEN')
    if not token:
        logging.error('Missing BIOTOOLS_API_TOKEN. Aborting upload.')
        raise SystemExit(1)
        
    headers = {**HEADERS, 'Authorization': f'Token {token}'}
    results = {
        'uploaded': [],
        'updated': [],
        'unchanged': [],
        'failed': [],
        'failed_validation': [],
        'failed_upload': [],
        'failed_update': []
    }

    for json in files:
        with open(json, 'r') as file:
            tool_id, status = process_single_file(file, headers)
            results[status].append(tool_id)

    print_summary(results)



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Sync changed .biotools.json files with bio.tools server')

    parser.add_argument('--files', metavar='F', type=str, nargs='+',
                        help='List of changed/created .biotools.json files to process')
    
    args = parser.parse_args()

    if args.files:
        run_upload(args.files)
