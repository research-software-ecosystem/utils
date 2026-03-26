#!/usr/bin/env python3
import os
import json
import logging
import argparse
import time
from functools import wraps
import requests
from boltons.iterutils import remap

HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}
DEFAULT_HOST = "https://bio.tools"

REQUEST_TIMEOUT = 30
RATE_LIMIT_DELAY = 0.5
MAX_RETRIES = 3
RETRY_BACKOFF_FACTOR = 2

logging.basicConfig(level=logging.INFO)


def retry_on_failure(max_retries=MAX_RETRIES, backoff_factor=RETRY_BACKOFF_FACTOR):
    """Decorator to retry failed requests with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts.
        backoff_factor: Multiplier for exponential backoff delay.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except requests.exceptions.RequestException as e:
                    if attempt == max_retries - 1:
                        raise
                    
                    delay = backoff_factor ** attempt
                    logging.warning(
                        f"Request failed (attempt {attempt + 1}/{max_retries}): {e}. "
                        f"Retrying in {delay}s..."
                    )
                    time.sleep(delay)
            
        return wrapper
    return decorator


class BioToolsClient:
    """Client for interacting with the bio.tools API."""

    def __init__(self, token=None, host=None, rate_limit_delay=RATE_LIMIT_DELAY):
        """Initialize the bio.tools client.
        
        Args:
            token: API token for bio.tools. If not provided, reads from 
                   BIOTOOLS_API_TOKEN environment variable.
            host: Base URL for the bio.tools API. Defaults to production.
                  Use 'https://bio-tools-dev.sdu.dk' for dev server.
            rate_limit_delay: Delay in seconds between API operations.
                   
        Raises:
            ValueError: If no token is provided or found in environment.
        """
        token = token or os.environ.get("BIOTOOLS_API_TOKEN")
        if not token:
            raise ValueError(
                "BIOTOOLS_API_TOKEN is required. Set environment variable or pass token parameter."
            )
        
        self.host = (host or DEFAULT_HOST).rstrip('/')
        self.headers = {**HEADERS, "Authorization": f"Token {token}"}
        self.rate_limit_delay = rate_limit_delay
        
        logging.info(f"Using bio.tools API at: {self.host}")

    @retry_on_failure()
    def get_tool(self, tool_id):
        """Retrieve a tool from bio.tools.
        
        Args:
            tool_id: The biotoolsID of the tool to retrieve.
            
        Returns:
            dict: Tool metadata if found, None otherwise.
            
        Raises:
            requests.RequestException
        """
        url = f"{self.host}/api/tool/{tool_id}/"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=REQUEST_TIMEOUT)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return None
            else:
                logging.error(
                    f"Error retrieving tool {tool_id}: {response.status_code} {response.text}"
                )
                return None
        except requests.RequestException as e:
            logging.error(f"Request failed for tool {tool_id}: {e}")
            raise

    def validate_upload(self, tool):
        """Validate a tool before uploading to bio.tools.
        
        Args:
            tool: Dictionary containing tool metadata with biotoolsID.
            
        Returns:
            bool: True if validation succeeds, False otherwise.
        """
        url = f"{self.host}/api/tool/validate/"
        
        try:
            response = requests.post(
                url, headers=self.headers, data=json.dumps(tool), timeout=REQUEST_TIMEOUT
            )
            
            if not response.ok:
                logging.error(
                    f"Error validating upload for {tool.get('biotoolsID', 'UNKNOWN')}: "
                    f"{response.status_code} {response.text}"
                )
            
            return response.ok
        except requests.RequestException as e:
            logging.error(f"Validation request failed: {e}")
            return False

    def validate_update(self, tool_id, tool):
        """Validate a tool before updating on bio.tools.
        
        Args:
            tool_id: The biotoolsID of the tool to update.
            tool: Dictionary containing updated tool metadata.
            
        Returns:
            bool: True if validation succeeds, False otherwise.
        """
        url = f"{self.host}/api/{tool_id}/validate/"
        
        try:
            response = requests.put(
                url, headers=self.headers, data=json.dumps(tool), timeout=REQUEST_TIMEOUT
            )
            
            if not response.ok:
                logging.error(
                    f"Error validating update for {tool.get('biotoolsID', tool_id)}: "
                    f"{response.status_code} {response.text}"
                )
            
            return response.ok
        except requests.RequestException as e:
            logging.error(f"Validation request failed for {tool_id}: {e}")
            return False

    def upload_tool(self, tool):
        """Upload a new tool to bio.tools.
        
        Args:
            tool: Dictionary containing tool metadata.
            
        Returns:
            bool: True if upload succeeds, False otherwise.
        """
        url = f"{self.host}/api/tool/"
        
        try:
            response = requests.post(
                url, headers=self.headers, data=json.dumps(tool), timeout=REQUEST_TIMEOUT
            )
            
            if not response.ok:
                logging.error(
                    f"Error uploading tool {tool.get('biotoolsID', 'UNKNOWN')}: "
                    f"{response.status_code} {response.text}"
                )
            
            return response.ok
        except requests.RequestException as e:
            logging.error(f"Upload request failed: {e}")
            return False

    def update_tool(self, tool):
        """Update an existing tool on bio.tools.
        
        Args:
            tool: Dictionary containing updated tool metadata with biotoolsID.
            
        Returns:
            bool: True if update succeeds, False otherwise.
        """
        tool_id = tool.get('biotoolsID')
        if not tool_id:
            logging.error("Cannot update tool without biotoolsID")
            return False
        
        url = f"{self.host}/api/tool/{tool_id}/"
        
        try:
            response = requests.put(
                url, headers=self.headers, data=json.dumps(tool), timeout=REQUEST_TIMEOUT
            )
            
            if not response.ok:
                logging.error(
                    f"Error updating tool {tool_id}: {response.status_code} {response.text}"
                )
            
            return response.ok
        except requests.RequestException as e:
            logging.error(f"Update request failed for {tool_id}: {e}")
            return False

    def process_tool_file(self, file_path):
        """Process a single tool file.
        
        Args:
            file_path: Path to a JSON file containing tool metadata.
            
        Returns:
            tuple: (tool_id, status) where status can be:
                   "uploaded", "updated", "unchanged", "failed",
                   "failed_validation", "failed_upload", or "failed_update"
        """
        try:
            with open(file_path, 'r') as file:
                payload_dict = json.load(file)
        except (IOError, json.JSONDecodeError) as e:
            logging.error(f"Error reading file {file_path}: {e}")
            return "UNKNOWN", "failed"
        
        tool_id = payload_dict.get("biotoolsID")
        if not tool_id:
            logging.error(f"'biotoolsID' not found in {file_path}")
            return "UNKNOWN", "failed"
        
        # Check if tool exists
        try:
            existing_tool = self.get_tool(tool_id)
        except requests.RequestException:
            return tool_id, "failed"
        
        if existing_tool:
            # Tool exists, check if update is needed
            # Remove empty fields for comparison
            existing_tool_clean = remap(existing_tool, lambda p, k, v: bool(v))
            payload_dict_clean = remap(payload_dict, lambda p, k, v: bool(v))
            
            if existing_tool_clean == payload_dict_clean:
                logging.info(f"Tool {tool_id} is unchanged")
                return tool_id, "unchanged"
            
            # Validate and update
            if not self.validate_update(tool_id, payload_dict):
                return tool_id, "failed_validation"
            
            success = self.update_tool(payload_dict)
            if success:
                logging.info(f"Tool {tool_id} updated successfully")
                return tool_id, "updated"
            else:
                return tool_id, "failed_update"
        else:
            # Tool doesn't exist, proceed with upload
            logging.info(f"Tool {tool_id} not registered, proceeding with upload")
            
            if not self.validate_upload(payload_dict):
                return tool_id, "failed_validation"
            
            success = self.upload_tool(payload_dict)
            if success:
                logging.info(f"Tool {tool_id} uploaded successfully")
                return tool_id, "uploaded"
            else:
                return tool_id, "failed_upload"

    def sync_tools(self, file_paths):
        """Process multiple tool files and sync them to bio.tools.
        
        Args:
            file_paths: List of paths to JSON files containing tool metadata.
            
        Returns:
            dict: Results dictionary with lists of tool IDs categorized by status.
        """
        results = {
            "uploaded": [],
            "updated": [],
            "unchanged": [],
            "failed": [],
            "failed_validation": [],
            "failed_upload": [],
            "failed_update": [],
        }
        
        total_files = len(file_paths)
        logging.info(f"Starting sync of {total_files} file(s)")
        
        for index, file_path in enumerate(file_paths, start=1):
            logging.info(f"[{index}/{total_files}] Processing {file_path}")
            
            tool_id, status = self.process_tool_file(file_path)
            results[status].append(tool_id)
            time.sleep(self.rate_limit_delay)
        
        return results


def print_summary(results):
    """Print a summary of the sync results.
    
    Args:
        results: Dictionary containing lists of tool IDs categorized by status.
    """
    logging.info("="*50)
    logging.info("SUMMARY")
    logging.info("="*50)
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
    logging.info("="*50)

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


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Sync changed .biotools.json files with bio.tools server"
    )

    parser.add_argument(
        "--files",
        metavar="F",
        type=str,
        nargs="+",
        required=True,
        help="List of changed/created .biotools.json files to process",
    )
    
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help=f"Bio.tools API host URL (default: {DEFAULT_HOST}). "
             "Use https://bio-tools-dev.sdu.dk for dev server",
    )

    args = parser.parse_args()

    try:
        client = BioToolsClient(host=args.host)
        
        results = client.sync_tools(args.files)
        
        print_summary(results)
        
        # Exit with error code if any operations failed
        total_failures = (
            len(results["failed"]) +
            len(results["failed_validation"]) +
            len(results["failed_upload"]) +
            len(results["failed_update"])
        )
        
        if total_failures > 0:
            logging.error(f"Completed with {total_failures} failure(s)")
            raise SystemExit(1)
        else:
            logging.info("All operations completed successfully")
            raise SystemExit(0)
            
    except ValueError as e:
        logging.error(str(e))
        raise SystemExit(1)
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
