"""Tell maintainers why an importer failed, and whether it is our problem.

Runs after the import jobs. For every importer that failed, it re-checks that
importer's upstream resource and says which of two things happened:

  upstream-unavailable  the resource is down. Nothing to fix here; the import
                        will resume by itself. data/ was left untouched.
  needs-attention       the resource answers normally, so the failure is most
                        likely in the importer.

The verdict is carried in one open issue per resource, labelled
`upstream-outage`. A new failure opens it, a change of verdict comments on it,
an unchanged verdict stays silent so that a long outage does not produce a
weekly alert, and a recovery comments and closes it.

Packaged as a composite action, so the workflow driving it can live elsewhere:
research-software-ecosystem/content's import workflow calls it as
`research-software-ecosystem/utils/notify-upstream-failures@main` and passes in
`toJSON(needs)`.

Deliberately stdlib-only: no requirements.txt, no pip install step, and no
dependency that can break the thing whose job is to tell you something broke.
"""

import json
import os
import socket
import sys
import urllib.error
import urllib.request

# Each importer's own upstream, taken from what the importer actually fetches.
# A tcp:// probe is for a resource that is not HTTP at all.
SOURCES = {
    "biotools": ("bio.tools", ["https://bio.tools/api/tool/?page=1"]),
    "openebench": ("OpenEBench", ["https://openebench.bsc.es/monitor/metrics/"]),
    "bioconda": (
        "Bioconda",
        ["https://codeload.github.com/bioconda/bioconda-recipes/zip/master"],
    ),
    # biii-import runs with `-td https://biii.eu` and fetches the software
    # list view from it; the http:// form in its source is an RDF namespace,
    # not a fetch target. Probing the site root instead would call a broken
    # Drupal view "reachable" while the front page still served fine.
    "biii": ("BIII", ["https://biii.eu/soft/?_format=json"]),
    "biocontainers": (
        "BioContainers",
        [
            (
                "https://raw.githubusercontent.com/BioContainers/tools-metadata/"
                "master/annotations.yaml"
            )
        ],
    ),
    "galaxytool": (
        "Galaxy Codex",
        [
            (
                "https://raw.githubusercontent.com/galaxyproject/galaxy_codex/"
                "refs/heads/main/communities/all/resources/tools.json"
            ),
            (
                "https://raw.githubusercontent.com/galaxyproject/galaxy_codex/"
                "refs/heads/main/communities/all/resources/workflows.json"
            ),
        ],
    ),
    "debian-med": ("Debian Med (UDD)", ["tcp://udd-mirror.debian.net:5432"]),
    "bioconductor": ("Bioconductor", ["https://bioconductor.org/config.yaml"]),
    # WorkflowHub's importer also reads the galaxy_codex table, to map Galaxy
    # tool IDs onto bio.tools IDs, so an outage there fails it just as surely.
    "workflowhub": (
        "WorkflowHub",
        [
            "https://workflowhub.eu/workflows.json?page=1",
            (
                "https://raw.githubusercontent.com/galaxyproject/galaxy_codex/"
                "refs/heads/main/communities/all/resources/tools.json"
            ),
        ],
    ),
}

LABEL = "upstream-outage"
NOTIFY_TEAM = "@research-software-ecosystem/rsec-ops"
MARKER = "<!-- rsec-notify verdict="
TIMEOUT = 20

API = "https://api.github.com"
REPO = os.environ.get("GITHUB_REPOSITORY", "")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
SERVER = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
RUN_ID = os.environ.get("GITHUB_RUN_ID", "")
RUN_URL = f"{SERVER}/{REPO}/actions/runs/{RUN_ID}" if RUN_ID else "(no run url)"
# Which workflow the stale-run check lists runs of. An input rather than a
# constant: this action lives in utils, and the workflow calling it does not.
WORKFLOW_FILE = os.environ.get("WORKFLOW_FILE") or "import.yaml"
# Only the explicit input turns this on. It used to fall back to `not TOKEN`,
# which quietly turned a missing credential into a run that probed nothing,
# printed simulated issue creations and finished green -- the configuration
# fault hidden by the very thing meant to surface faults. main() now refuses
# to run without a token instead.
DRY_RUN = os.environ.get("DRY_RUN") == "1"

# Set when the stale-run check could not run. Reported with the outcomes: a
# missing `actions: read` in the caller degrades the guard silently, and the
# calling workflow now lives in a repository this action cannot inspect.
STALE_GUARD_NOTE = None


def probe(target):
    """Return (reachable, detail) for one upstream target."""
    if target.startswith("tcp://"):
        host, _, port = target[len("tcp://") :].partition(":")
        try:
            with socket.create_connection((host, int(port or 0)), timeout=TIMEOUT):
                return True, "TCP connect OK"
        except OSError as exc:
            return False, f"TCP connect failed: {exc}"
    # HEAD first: one of these targets is a multi-megabyte archive, and we only
    # ever want the status line. Some servers refuse HEAD, hence the fallback.
    for method in ("HEAD", "GET"):
        request = urllib.request.Request(
            target,
            method=method,
            headers={"Accept": "*/*", "User-Agent": "rsec-notify"},
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                return True, f"HTTP {response.status}"
        except urllib.error.HTTPError as exc:
            if method == "HEAD" and exc.code in (403, 405, 501):
                continue
            # A status line is an answer: the host is up even if the path is
            # unhappy. 5xx, and Cloudflare's 52x, mean it is not serving.
            return (exc.code < 500), f"HTTP {exc.code}"
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            return False, f"unreachable: {getattr(exc, 'reason', exc)}"
    return False, "no response to HEAD or GET"


def api(method, path, payload=None):
    # Only writes are suppressed in a dry run. Stubbing reads too made the
    # report wrong in exactly the cases worth rehearsing: with the issue list
    # always coming back empty, a recovery looked like "nothing to do" and a
    # failure with an issue already open looked like a fresh create.
    if DRY_RUN and method != "GET":
        print(
            f"    [dry-run] {method} {path} {json.dumps(payload)[:120] if payload else ''}"
        )
        return {}
    headers = {
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "User-Agent": "rsec-notify",
    }
    # A dry run is allowed to have no token; reading public issues does not
    # need one, and `Bearer ` with nothing after it is rejected outright.
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    request = urllib.request.Request(
        f"{API}{path}",
        method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read()
    return json.loads(body) if body else {}


def superseded_by_newer_run():
    """True when a newer run of this workflow has already started.

    Overlapping import runs are a problem in their own right, since they share
    the *-import-branch names, but the notifier should at least not let a slow
    older run reopen an outage that a newer run has just closed. The
    concurrency group serialises us; it does not order us.
    """
    global STALE_GUARD_NOTE
    if DRY_RUN or not RUN_ID:
        return False
    try:
        runs = api(
            "GET", f"/repos/{REPO}/actions/workflows/{WORKFLOW_FILE}/runs?per_page=1"
        )
    except Exception as exc:  # noqa: BLE001 - this check must never be the thing that breaks
        # A 403 here means the calling job is missing `actions: read`, which is
        # a configuration fault rather than a blip, so name what is lost and
        # put it in the summary where someone will see it.
        STALE_GUARD_NOTE = (
            f"Could not list runs of `{WORKFLOW_FILE}` ({exc}), so this run had "
            "no stale-run protection. A 403 here means the calling job is "
            "missing `actions: read`."
        )
        print(f"  {STALE_GUARD_NOTE}")
        return False
    if not isinstance(runs, dict):
        return False
    listed = runs.get("workflow_runs") or []
    newest = listed[0].get("id") if listed else None
    return bool(newest) and str(newest) != str(RUN_ID)


def ensure_label():
    """Create the tracking label if the repository does not have it yet.

    find_issue() filters on this label, so an issue created before the label
    exists could be invisible on the next run, and a duplicate would be opened
    for an outage already being tracked.
    """
    if DRY_RUN:
        print(f"    [dry-run] ensure label {LABEL} exists")
        return
    try:
        api("GET", f"/repos/{REPO}/labels/{LABEL}")
        return
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
    api(
        "POST",
        f"/repos/{REPO}/labels",
        {
            "name": LABEL,
            "color": "d93f0b",
            "description": "An upstream resource an importer depends on is unavailable",
        },
    )
    print(f"created the {LABEL} label")


_OPEN_ISSUES = None


def find_issue(title):
    """Look up our open tracking issues, fetching the list at most once."""
    global _OPEN_ISSUES
    if _OPEN_ISSUES is None:
        path = f"/repos/{REPO}/issues?state=open&labels={LABEL}&per_page=100"
        try:
            _OPEN_ISSUES = api("GET", path)
        except Exception as exc:
            # Unauthenticated reads are rate limited, and a local dry run may
            # have no network or no real repository. Say so and carry on as
            # if nothing were open; a real run still propagates the error.
            if not DRY_RUN:
                raise
            print(f"    [dry-run] could not list issues ({exc}); assuming none open")
            _OPEN_ISSUES = []
    for issue in _OPEN_ISSUES:
        # The issues endpoint returns pull requests as well. Matching one would
        # mean commenting on it and closing it on the recovery path.
        if "pull_request" in issue:
            continue
        if issue.get("title") == title:
            return issue
    return None


def previous_verdict(issue):
    body = (issue or {}).get("body") or ""
    if MARKER in body:
        return body.split(MARKER, 1)[1].split("-->", 1)[0].strip()
    return None


def body_for(resource, verdict, probe_lines):
    headline = {
        "upstream-unavailable": (
            f"**{resource} is not answering.** The importer stopped before writing "
            "anything, so `data/` still holds the previous import. Nothing needs "
            "fixing here: the next scheduled run will pick up where it left off "
            "once the resource is back."
        ),
        "needs-attention": (
            f"**{resource} answers normally, so this is probably not an outage.** "
            "The failure is more likely in the importer or in a change to the "
            f"resource's API. Someone should look at the run."
        ),
    }[verdict]
    probes = "\n".join(f"- `{url}` -> {detail}" for url, detail in probe_lines)
    return (
        f"{MARKER}{verdict} -->\n"
        f"{headline}\n\n"
        f"Checked just now, from the notifier job:\n{probes}\n\n"
        f"Failing run: {RUN_URL}\n\n"
        f"{NOTIFY_TEAM}\n\n"
        "<sub>Opened automatically. It will be closed when the importer next "
        "succeeds.</sub>"
    )


def handle(job, resource, targets, result, label_ready=True):
    """Report on one importer. Returns the summary row for it.

    With label_ready false the label could not be confirmed, so no new issue is
    opened: find_issue() filters on that label, and an issue created without it
    would be invisible next run and duplicated every run after. Recovery still
    runs, since anything it finds was labelled when it was opened.
    """
    title = f"import failure: {resource}"

    if result == "success":
        issue = find_issue(title)
        if not issue:
            return (job, result, "-", "-", "nothing to do")
        api(
            "POST",
            f"/repos/{REPO}/issues/{issue['number']}/comments",
            {"body": f"Recovered: the importer succeeded in {RUN_URL}."},
        )
        api("PATCH", f"/repos/{REPO}/issues/{issue['number']}", {"state": "closed"})
        return (job, result, "-", "recovered", f"closed #{issue['number']}")

    if result in ("skipped", "cancelled", "missing"):
        return (job, result, "-", "-", "not evaluated")

    # Probe each target once; both the verdict and the report come from it.
    checked = [(target, *probe(target)) for target in targets]
    probe_lines = [(target, detail) for target, _, detail in checked]
    # Every target has to answer. An importer that reads two resources fails if
    # either is down, so one reachable host is not evidence that it is our bug.
    verdict = (
        "needs-attention" if all(ok for _, ok, _ in checked) else "upstream-unavailable"
    )
    summary = "; ".join(detail for _, detail in probe_lines)

    issue = find_issue(title)
    if issue is None:
        if not label_ready:
            return (
                job,
                result,
                summary,
                verdict,
                "not opened: the label could not be confirmed",
            )
        created = api(
            "POST",
            f"/repos/{REPO}/issues",
            {
                "title": title,
                "body": body_for(resource, verdict, probe_lines),
                "labels": [LABEL],
            },
        )
        action = f"opened #{created.get('number', '?')}"
    elif previous_verdict(issue) != verdict:
        api(
            "POST",
            f"/repos/{REPO}/issues/{issue['number']}/comments",
            {
                "body": f"Still failing, but the picture changed "
                f"(`{previous_verdict(issue)}` -> `{verdict}`).\n\n"
                f"{body_for(resource, verdict, probe_lines)}"
            },
        )
        api(
            "PATCH",
            f"/repos/{REPO}/issues/{issue['number']}",
            {"body": body_for(resource, verdict, probe_lines)},
        )
        action = f"updated #{issue['number']}"
    else:
        action = f"#{issue['number']} already open, staying quiet"
    return (job, result, summary, verdict, action)


def unconfigured(needs):
    """Jobs the caller waits on that this script has no upstream for.

    A test used to keep SOURCES and the workflow in step by reading import.yaml
    directly. This script now lives in another repository and cannot do that,
    so the same drift is caught here instead, against the job list the caller
    passes in. An importer nobody probes is an importer whose failures are
    silent, which is the thing this script exists to prevent.
    """
    return [job for job in needs if job not in SOURCES]


def main():
    needs = json.loads(os.environ.get("JOB_RESULTS") or "{}")
    if not needs:
        sys.exit("JOB_RESULTS is empty; nothing to report")
    if not DRY_RUN and not TOKEN:
        sys.exit(
            "no GITHUB_TOKEN: pass `repo-token` to the action, or set "
            "`dry-run: true` to report without touching issues. Refusing to "
            "continue, because a silent no-op here looks exactly like a run "
            "with nothing to report."
        )

    rows = []
    failures = []

    if superseded_by_newer_run():
        write_summary(
            [
                (
                    job,
                    (needs.get(job) or {}).get("result", "missing"),
                    "-",
                    "-",
                    "skipped: a newer run of this workflow has started",
                )
                for job in SOURCES
            ]
        )
        return

    label_ready = True
    if any((needs.get(job) or {}).get("result") == "failure" for job in SOURCES):
        try:
            ensure_label()
        except Exception as exc:  # noqa: BLE001 - reporting must survive its own faults
            # Do not abort here: that would skip the summary at exactly the
            # moment the reporting path is in trouble. Opening issues is held
            # back instead, so a run cannot leave unlabelled ones behind.
            label_ready = False
            reason = f"{type(exc).__name__}: {exc}"
            print(f"  ERROR ensuring the {LABEL} label: {reason}")
            failures.append(("label setup", reason))
    for job, (resource, targets) in SOURCES.items():
        result = (needs.get(job) or {}).get("result", "missing")
        try:
            rows.append(handle(job, resource, targets, result, label_ready))
        except Exception as exc:  # noqa: BLE001 - one resource must not hide the rest
            # One resource failing to report must not hide the other eight, nor
            # lose the summary. Record it and carry on; the exit status below
            # still makes the run red.
            reason = f"{type(exc).__name__}: {exc}"
            print(f"  ERROR reporting on {job}: {reason}")
            rows.append((job, result, "-", "-", f"REPORTING FAILED - {reason[:60]}"))
            failures.append((job, reason))

    for job in unconfigured(needs):
        result = (needs.get(job) or {}).get("result", "missing")
        rows.append((job, result, "-", "-", "not probed: no upstream configured"))
        if result == "failure":
            # Nothing else reports this one, so make the run red and say why
            # rather than letting it pass as a green notifier over a red import.
            failures.append((job, "no upstream configured for this job"))

    write_summary(rows)
    if failures:
        sys.exit(
            "could not report on: "
            + "; ".join(f"{job} ({error})" for job, error in failures)
        )


def write_summary(rows):
    lines = [
        "## Importer outcomes",
        "",
        "| importer | result | upstream check | verdict | action |",
        "| --- | --- | --- | --- | --- |",
    ]
    for job, result, summary, verdict, action in rows:
        lines.append(f"| {job} | {result} | {summary} | {verdict} | {action} |")
    if STALE_GUARD_NOTE:
        lines += ["", "> [!WARNING]", f"> {STALE_GUARD_NOTE}"]
    text = "\n".join(lines) + "\n"
    print(text)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a") as handle:
            handle.write(text)


if __name__ == "__main__":
    main()
