"""Import every bio.tools entry into the RSEc commons as data/<id>/<id>.biotools.json.

Records are fetched into a staging directory first and only moved into data/
once the crawl has finished and looks complete. Deleting first and fetching
afterwards, as this script used to do, meant that any bio.tools outage emptied
data/ of ~34,000 records: the crawl treated an empty first page as a normal end
of pagination, returned no tools, and exited 0.
"""

import argparse
import datetime
import email.utils
import glob
import json
import os
import shutil
import sys
import tempfile
import time

import requests
from boltons.iterutils import remap

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.metadata import normalize_version_fields

BIOTOOLS_DOMAIN = "https://bio.tools"
SSL_VERIFY = True

# A full crawl is ~350 requests, so a single unretried failure is likely over
# time. Retry transient trouble; give up loudly on the rest.
TIMEOUT = (10, 60)  # (connect, read)
RETRY_ATTEMPTS = 5
RETRY_BACKOFF = 4  # seconds, doubling: 4, 8, 16, 32
# 429 plus the 5xx that mean "ask again later", including the Cloudflare codes
# for an origin that is down, unreachable or timing out (520, 521, 522, 523,
# 524). 525 and 526 are TLS misconfigurations at the origin: retrying cannot
# clear them, so they are deliberately left to fail loudly on the first
# response rather than after five rounds of backoff.
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504, 520, 521, 522, 523, 524})
MAX_RETRY_AFTER = 120

# A full crawl is authoritative, so it prunes records bio.tools no longer
# serves. Refuse to prune on this scale, which means something is wrong
# upstream rather than in the registry's contents.
MAX_DROP = 0.10

SESSION = requests.Session()


def retry_after_seconds(value):
    """How long a Retry-After header asks us to wait.

    RFC 9110 allows either a number of seconds or an HTTP-date, and rate
    limiters use both. Returns None when the header is absent or unparseable,
    in which case the caller keeps its own backoff.
    """
    value = (value or "").strip()
    if not value:
        return None
    if value.isdigit():
        return int(value)
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=datetime.timezone.utc)
    ahead = (when - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
    return max(0, int(ahead))


def get_with_retries(url, params, description):
    """GET a URL, retrying transient failures with exponential backoff.

    A plain loop over requests rather than an HTTPAdapter with a urllib3
    Retry: HTTPAdapter(max_retries=<int>) builds Retry(read=False), which never
    retries a request whose data reached the server, and the Retry object would
    pull urllib3 into a script whose requirements list only requests and
    boltons. Returns the response, or None once the attempts are exhausted.
    """
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        delay = RETRY_BACKOFF * 2 ** (attempt - 1)
        try:
            response = SESSION.get(
                url,
                params=params,
                headers={"Accept": "application/json"},
                verify=SSL_VERIFY,
                timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            reason = str(exc) or type(exc).__name__
        else:
            if response.status_code not in RETRY_STATUSES:
                return response
            reason = f"HTTP {response.status_code}"
            asked = retry_after_seconds(response.headers.get("Retry-After"))
            if asked is not None:
                delay = min(asked, MAX_RETRY_AFTER)

        if attempt == RETRY_ATTEMPTS:
            print(f"  ERROR: {description} failed after {attempt} attempts: {reason}")
            return None
        print(f"  {description} failed ({reason}); retrying in {delay}s")
        time.sleep(delay)

    return None


def fetch_page(page, filters):
    """Return one page of the tool list, or exit if it cannot be trusted."""
    description = f"tool list page {page}"
    response = get_with_retries(
        f"{BIOTOOLS_DOMAIN}/api/tool/", {**filters, "page": page}, description
    )
    if response is None:
        sys.exit(f"giving up on {description}; data/ left untouched")
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        sys.exit(f"{description}: {exc}; data/ left untouched")
    try:
        entry = response.json()
    except ValueError:
        # An outage typically serves an HTML error page with a 2xx or a status
        # we do not retry; either way it is not a tool list.
        sys.exit(
            f"{description} was not JSON (content-type "
            f"{response.headers.get('Content-Type', '?')}); data/ left untouched"
        )
    if not isinstance(entry, dict):
        sys.exit(
            f"{description} was not an object but a {type(entry).__name__}; "
            "data/ left untouched"
        )
    # Both keys are required. Inferring "that was the last page" from a missing
    # "next" would let a truncated response end the crawl quietly, and if it
    # still carried most of the records the drop gate would wave it through and
    # prune the rest.
    missing = [key for key in ("list", "next") if key not in entry]
    if missing:
        sys.exit(
            f"{description} is missing {', '.join(missing)} "
            f"(keys seen: {', '.join(sorted(entry)) or 'none'}); data/ left untouched"
        )
    return entry


def retrieve(staging, filters=None):
    """Write every tool's record into the staging directory.

    Returns {tool_id: staged path}. Nothing under data/ is touched here.
    """
    staged = {}
    filters = filters or {}
    page = 1
    while True:
        entry = fetch_page(page, filters)
        for tool in entry["list"]:
            tool_id = tool["biotoolsID"].lower()

            def drop_false(path, key, value):
                return bool(value)

            tool_cleaned = remap(tool, visit=drop_false)
            tool_cleaned = normalize_version_fields(tool_cleaned, ["version"])

            staged_path = os.path.join(staging, f"{tool_id}.biotools.json")
            with open(staged_path, "w") as write_file:
                json.dump(
                    tool_cleaned,
                    write_file,
                    sort_keys=True,
                    indent=4,
                    separators=(",", ": "),
                )
            staged[tool_id] = staged_path
            print(f"fetched tool #{len(staged)}: {tool_id}")
        if entry.get("next") is None:
            break
        page += 1
    return staged


def install(staged, prune):
    """Move staged records into data/, replacing what is there.

    With prune set -- a full, unfiltered crawl, which is authoritative -- records
    for tools the crawl did not return are removed. A filtered crawl speaks only
    for its own collection, so it leaves every other record alone.

    Records are put in place before anything is pruned, so that a failure part
    way through the move loop has pruned nothing at all. Files not yet reached
    still hold their previous contents, since a move overwrites rather than
    unlinks first.
    """
    for tool_id, staged_path in sorted(staged.items()):
        directory = os.path.join("data", tool_id)
        os.makedirs(directory, exist_ok=True)
        shutil.move(staged_path, os.path.join(directory, f"{tool_id}.biotools.json"))

    removed = 0
    if prune:
        for path in glob.glob(os.path.join("data", "*", "*.biotools.json")):
            if os.path.basename(os.path.dirname(path)) not in staged:
                os.remove(path)
                removed += 1
    return removed


def main():
    parser = argparse.ArgumentParser(description="biotools import script")
    parser.add_argument(
        "collection", type=str, default="*", nargs="?", help="collection name filter"
    )
    args = parser.parse_args()
    full_import = args.collection == "*"
    filters = {} if full_import else {"collection": args.collection}

    existing = len(glob.glob(os.path.join("data", "*", "*.biotools.json")))
    print(f"data/ currently holds {existing} bio.tools records")

    staging = tempfile.mkdtemp(prefix="biotools-import-")
    try:
        staged = retrieve(staging, filters)

        # Gate before anything under data/ is touched.
        if not staged:
            sys.exit(
                "bio.tools returned no tools at all; data/ left untouched. "
                "This is what an outage looks like, not an empty registry."
            )
        if full_import and existing and len(staged) < existing * (1 - MAX_DROP):
            sys.exit(
                f"refusing to replace {existing} records with only {len(staged)}: "
                f"a drop of more than {MAX_DROP:.0%} means the crawl is incomplete. "
                "data/ left untouched."
            )

        removed = install(staged, prune=full_import)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    print(f"\nimported {len(staged)} bio.tools records")
    if removed:
        print(f"pruned {removed} records no longer served by bio.tools")


if __name__ == "__main__":
    main()
