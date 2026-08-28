import fnmatch
import glob
import http.client
import json
import os
import urllib.error
import urllib.request

TOOLS_CONTENT_PATH = "data/"
OPENEBENCH_METRICS_ENDPOINT = "https://openebench.bsc.es/monitor/metrics/"

# Native records deposited by the other importers. A folder holding none of
# these has no upstream source left that vouches for the tool.
NATIVE_SOURCE_PATTERNS = (
    "*.biotools.json",
    "*.biocontainers.yaml",
    "biocontainers.yaml",
    "*.bioconductor.json",
    "bioconda_*.yaml",
    "*.bioconda.yaml",
    "*.neubias.raw.json",
    "*.galaxy.json",
    "*.debian.yaml",
    "*.workflowhub.json",
)

# Namespaces other than these are independent evidence that the tool exists:
# a bioconda- or galaxy-sourced record stands on its own even when bio.tools
# has nothing. Only bio.tools-sourced and namespace-less records are treated as
# possible residue.
BIOTOOLS_NAMESPACE = "biotools"

# Refuse to drop more than this share of the tools OpenEBench reports. The
# caller commits whatever this script leaves behind, so a bug in the rule below
# would silently delete data from the commons.
MAX_DROPPED_FRACTION = 0.10

JSONPATH_FILTER = [
    "/@timestamp",
    "/project/website/last_check",
    "/project/website/access_time",
    "/project/website/last_month_access/",
    "/project/website/half_year_stat/",
]


def clean():
    for data_file in glob.glob(r"data/*/*.oeb.metrics.json"):
        os.remove(data_file)


def has_native_source(tool_dir):
    """True when another importer has deposited a record in this folder.

    clean() has already removed the OpenEBench file, so what is left is the
    other sources' own records. Derived representations (.bioschemas.jsonld,
    .ttl, .jsonld) do not count: they are generated from a source rather than
    deposited by one, and one derived from a deleted bio.tools entry outlives
    it.
    """
    try:
        with os.scandir(tool_dir) as entries:
            names = [entry.name for entry in entries if entry.is_file()]
    except OSError:
        return False
    return any(
        fnmatch.fnmatch(name, pattern)
        for name in names
        if not name.endswith(".backup")
        for pattern in NATIVE_SOURCE_PATTERNS
    )


def record_namespace(record, tokens):
    """The registry OpenEBench harvested a record from, or None.

    Prefers the explicit @nmsp field, falling back to the namespace prefix of
    the @id, which is what identifies the tool folder in the first place.
    """
    namespace = record.get("@nmsp")
    if namespace:
        return namespace
    return tokens[0] if len(tokens) > 1 else None


def is_biotools_residue(tool_dir, namespaces):
    """True when this folder only survives because of a deleted bio.tools entry.

    OpenEBench keeps monitoring a tool after bio.tools drops it, and because
    this importer only writes into folders that already exist, the folder
    lingers with nothing in it but the metrics file -- a tool no registry
    describes any more. data/kolkata_escorts is the clearest case: spam that
    bio.tools purged, still carried here.

    Two conditions, both required, so that the far larger population of
    Bioconda and Bioconductor packages that OpenEBench monitors and bio.tools
    never listed is left alone:

      * no other importer has deposited a record in the folder, and
      * no namespace other than bio.tools vouches for the tool.

    Absence of a bio.tools record stands in for asking bio.tools. Querying the
    API per tool would be authoritative but needs ~41000 requests. The cost is
    one cycle of lag: this job and the bio.tools import run in parallel from
    the same commit, so a tool dropped from bio.tools this week still has last
    week's file here, and is removed on the next run.
    """
    if has_native_source(tool_dir):
        return False
    return not (namespaces - {None, BIOTOOLS_NAMESPACE})


def main():
    # dictionary to group metrics by the tool i.e. {'trimal' : [json1, json2, json3]}
    git_metrics = {}
    metrics = get_metrics()

    if metrics is None:
        raise SystemExit(
            "failed to retrieve metrics from OpenEBench; clean() has already "
            "removed the previous import, so exiting non-zero to keep the "
            "caller from committing the deletion of every metrics file"
        )

    # namespaces seen per tool, to tell a deleted bio.tools entry apart from a
    # package that bio.tools simply never listed
    git_namespaces = {}

    for m in metrics:
        uri = m.get("@id")
        suffix = uri.find("/", len(OPENEBENCH_METRICS_ENDPOINT))
        identifier = (
            uri[len(OPENEBENCH_METRICS_ENDPOINT) :]
            if suffix < 0
            else uri[len(OPENEBENCH_METRICS_ENDPOINT) : suffix]
        )
        tokens = identifier.split(":")
        oeb_id = tokens[0] if len(tokens) == 1 else tokens[1]
        tool_dir = TOOLS_CONTENT_PATH + oeb_id

        if tool_dir is not None and os.path.isdir(tool_dir):
            metrics_list = git_metrics.get(tool_dir)
            if metrics_list is not None:
                metrics_list.append(m)
            else:
                git_metrics[tool_dir] = [m]
            git_namespaces.setdefault(tool_dir, set()).add(record_namespace(m, tokens))

    dropped = {
        tool_dir
        for tool_dir in git_metrics
        if is_biotools_residue(tool_dir, git_namespaces[tool_dir])
    }
    if dropped:
        fraction = len(dropped) / len(git_metrics)
        print(
            f"dropping {len(dropped)} of {len(git_metrics)} tools "
            f"({fraction:.1%}): no source record left and nothing but bio.tools "
            "ever vouched for them"
        )
        for tool_dir in sorted(dropped):
            print("  dropped " + tool_dir)
        if fraction > MAX_DROPPED_FRACTION:
            raise SystemExit(
                f"aborting: refusing to drop {fraction:.1%} of tools, over the "
                f"{MAX_DROPPED_FRACTION:.0%} limit"
            )

    for tool_dir, m in git_metrics.items():
        if tool_dir in dropped:
            continue
        path = tool_dir + "/" + os.path.basename(tool_dir) + ".oeb.metrics.json"
        with open(path, "w") as f:
            print("writing to file " + path)
            json.dump(m, f, indent=4, sort_keys=True)


# Get OpenEBench metrics
def get_metrics():
    try:
        res = urllib.request.urlopen(OPENEBENCH_METRICS_ENDPOINT)
        if res.getcode() < 300:
            data = res.read()
            return json.loads(data)
        else:
            print(f"Error reading metrics: HTTP {res.getcode()}")
            return None
    except urllib.error.HTTPError as e:
        print(f"HTTP Error: {e.code} - {e.reason}")
        return None
    except urllib.error.URLError as e:
        print(f"URL Error: {e.reason}")
        return None
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}")
        return None
    except (OSError, http.client.HTTPException, ValueError) as e:
        print(f"Unexpected error reading metrics: {type(e).__name__}: {e}")
        return None


if __name__ == "__main__":
    clean()
    main()
