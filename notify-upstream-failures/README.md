# notify-upstream-failures

Reports why each importer failed, and whether the upstream resource or the
importer is to blame.

For every importer job that failed, it re-probes that importer's upstream and
reaches one of two verdicts:

| verdict | meaning |
| --- | --- |
| `upstream-unavailable` | The resource is down. Nothing to fix; the importer stopped before writing, so `data/` still holds the previous import and the next run resumes by itself. |
| `needs-attention` | The resource answers normally, so the failure is most likely in the importer or in a change to the resource's API. |

The verdict lives in one open issue per resource, labelled `upstream-outage`.
A new failure opens it, a change of verdict comments on it, an unchanged
verdict stays silent so a long outage does not alert weekly, and a recovery
comments and closes it. Every run also writes a table of outcomes to the job
summary, whether or not anything failed.

## Usage

```yaml
notify:
  runs-on: ubuntu-latest
  needs: [biotools, openebench, bioconda, ...]
  # Run whatever the importers did: `needs` alone would skip this job as soon
  # as one of them failed, which is precisely when it is needed.
  if: always()
  permissions:
    # A job-level permissions map denies every scope it does not name.
    issues: write   # read, open, comment on, close and label the issue
    actions: read   # list this workflow's runs, for the stale-run check
  concurrency:
    # find-then-create is not atomic across runners: a manual dispatch
    # overlapping the schedule would otherwise open duplicate issues.
    group: notify-upstream-failures
    cancel-in-progress: false
  steps:
    - uses: research-software-ecosystem/utils/notify-upstream-failures@main
      with:
        repo-token: ${{ secrets.GITHUB_TOKEN }}
        job-results: ${{ toJSON(needs) }}
        workflow-file: import.yaml
```

No `actions/checkout` is needed: the action brings its own script.

### Inputs

| input | required | default | |
| --- | --- | --- | --- |
| `repo-token` | yes | | Token used for the issue API calls. With no token and `dry-run` off, the action exits non-zero rather than doing nothing quietly. |
| `job-results` | yes | | `${{ toJSON(needs) }}`. Its keys are matched against the table of upstream resources below. |
| `workflow-file` | no | `import.yaml` | Filename of the calling workflow, for the stale-run check. |
| `dry-run` | no | `false` | Rehearse: probe for real and read the real issue list, but change nothing. The only way to run without a token. |

## Adding an importer

Add an entry to `SOURCES` in `notify_upstream_failures.py`, keyed by the job
name in the calling workflow, with the URLs that importer actually fetches.
Use a `tcp://host:port` target for a resource that is not HTTP.

Name the endpoint, not the host. A site's front page can be perfectly healthy
while the API behind it is not, and telling those apart is the whole job; a
target that is only a site root is rejected by the tests.

Every target must answer for the verdict to be `needs-attention`: an importer
that reads two resources fails if either is down, so one reachable host is not
evidence that the bug is ours.

A job passed in `job-results` with no entry in `SOURCES` is reported as
`not probed: no upstream configured`, and if that job failed the notifier exits
non-zero. That is deliberate — an importer nobody probes is an importer whose
failures are silent, which is the thing this action exists to prevent.

## Tests

```console
$ python3 -m unittest discover -s notify-upstream-failures -p 'test_*.py' -v
```

Stdlib-only and fully stubbed, so the suite is offline and cannot fail because
an upstream happens to be down. That is enforced, not merely intended: the
suite blocks socket connections outright, so a test that forgets to stub
something fails instead of quietly reaching the network.

To exercise the real probes, run the script with `DRY_RUN=1`. It probes for
real and reads the real issue list, but suppresses every write, so the report
says what a real run would have done -- including that an issue is already
open, or that a recovery would close one. Reads are unauthenticated when no
token is given, and if the issue list cannot be read the dry run says so and
carries on rather than failing.
