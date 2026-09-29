"""Tests for notify_upstream_failures.py.

    python3 -m unittest discover -s notify-upstream-failures

Offline by design: every probe and every GitHub call is stubbed, so the suite
is fast and cannot fail because an upstream happens to be down. To exercise the
real probes, run the notifier itself with DRY_RUN=1, which reports what it
would do without touching anything.

Stdlib only, for the same reason the notifier is: the thing that tells you
something broke should not depend on something that can break.
"""

import importlib
import json
import os
import re
import sys
import unittest
from typing import ClassVar
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# The module reads its configuration at import time. These are set rather than
# defaulted: on a runner the real GITHUB_RUN_ID is already present, and with
# setdefault the suite silently tested against it -- every run then looked
# superseded by a newer one, which passed locally and failed in CI.
os.environ["GITHUB_REPOSITORY"] = "owner/repo"
os.environ["GITHUB_RUN_ID"] = "100"
os.environ["GITHUB_TOKEN"] = "x"
os.environ["GITHUB_SERVER_URL"] = "https://github.com"
os.environ.pop("DRY_RUN", None)
# Never append to the runner's real job summary.
os.environ.pop("GITHUB_STEP_SUMMARY", None)

import notify_upstream_failures as notifier

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "notify_upstream_failures.py")
ACTION = os.path.join(HERE, "action.yml")


class Base(unittest.TestCase):
    def setUp(self):
        # Reload so module state, notably the cached issue list, is clean.
        importlib.reload(notifier)
        notifier.DRY_RUN = False
        self.calls = []

    def stub_api(self, gets=None, raises=None):
        """Record every API call. `gets` maps a path regex to a GET response.

        Matching is per method on purpose: POST /issues and GET /issues share a
        path, and an earlier version of this stub answered the create call with
        the list response.
        """
        gets = gets or {}

        def api(method, path, payload=None):
            self.calls.append((method, path, payload))
            if raises and re.search(raises, path):
                raise RuntimeError("GitHub said no")
            if method != "GET":
                return {"number": 1}
            for pattern, value in gets.items():
                if re.search(pattern, path):
                    return value
            return []

        notifier.api = api

    def run_main(self, results):
        os.environ["JOB_RESULTS"] = json.dumps(
            {job: {"result": r} for job, r in results.items()}
        )
        self.rows = None
        notifier.write_summary = lambda rows: setattr(self, "rows", rows)
        try:
            notifier.main()
            return 0
        except SystemExit as exc:
            return 0 if exc.code in (0, None) else 1

    def writes(self):
        return [(m, p) for m, p, _ in self.calls if m in ("POST", "PATCH")]


class Probe(Base):
    """A status line means the host is serving; 5xx and 52x mean it is not."""

    def check(self, status, expected):
        import urllib.error

        if status == "unreachable":
            err = urllib.error.URLError("no route")
            with mock.patch("urllib.request.urlopen", side_effect=err):
                self.assertEqual(notifier.probe("https://x")[0], expected)
            return
        if status >= 400:
            err = urllib.error.HTTPError("https://x", status, "", {}, None)
            with mock.patch("urllib.request.urlopen", side_effect=err):
                self.assertEqual(notifier.probe("https://x")[0], expected)
            return
        resp = mock.MagicMock()
        resp.status = status
        resp.__enter__.return_value = resp
        with mock.patch("urllib.request.urlopen", return_value=resp):
            self.assertEqual(notifier.probe("https://x")[0], expected)

    def test_serving_states_are_reachable(self):
        for status in (200, 301, 403, 404):
            with self.subTest(status=status):
                self.check(status, True)

    def test_not_serving_states_are_unreachable(self):
        for status in (500, 502, 521, 522, 524, "unreachable"):
            with self.subTest(status=status):
                self.check(status, False)

    def test_tcp_probe_reports_connect_failure(self):
        import socket

        with mock.patch("socket.create_connection", side_effect=OSError("refused")):
            ok, detail = notifier.probe("tcp://host:5432")
        self.assertFalse(ok)
        self.assertIn("TCP connect failed", detail)
        with mock.patch("socket.create_connection", return_value=mock.MagicMock()):
            self.assertTrue(notifier.probe("tcp://host:5432")[0])
        del socket


class Verdict(Base):
    """An importer reading two resources fails if either is down."""

    def verdict_for(self, probes):
        notifier.SOURCES = {"x": ("X", list(probes))}
        notifier.probe = lambda target: probes[target]
        self.stub_api()
        self.run_main({"x": "failure"})
        return self.rows[0][3]

    def test_all_targets_must_answer(self):
        up, down = (True, "HTTP 200"), (False, "HTTP 521")
        self.assertEqual(self.verdict_for({"a": up, "b": up}), "needs-attention")
        self.assertEqual(self.verdict_for({"a": up, "b": down}), "upstream-unavailable")
        self.assertEqual(
            self.verdict_for({"a": down, "b": down}), "upstream-unavailable"
        )


class FindIssue(Base):
    """The issues endpoint also returns pull requests."""

    PR: ClassVar[dict] = {
        "number": 5,
        "title": "import failure: X",
        "pull_request": {},
        "body": "",
    }
    ISSUE: ClassVar[dict] = {"number": 9, "title": "import failure: X", "body": ""}

    def test_pull_request_is_never_selected(self):
        self.stub_api(gets={"issues": [self.PR, self.ISSUE]})
        self.assertEqual(notifier.find_issue("import failure: X")["number"], 9)

    def test_pull_request_alone_is_no_match(self):
        self.stub_api(gets={"issues": [self.PR]})
        self.assertIsNone(notifier.find_issue("import failure: X"))

    def test_issue_list_is_fetched_once(self):
        self.stub_api(gets={"issues": [self.ISSUE]})
        for _ in range(3):
            notifier.find_issue("import failure: X")
        self.assertEqual(len([c for c in self.calls if c[0] == "GET"]), 1)


class Lifecycle(Base):
    """One open issue per resource: open, stay quiet, update, close."""

    def setUp(self):
        super().setUp()
        notifier.SOURCES = {"x": ("X", ["u"])}
        notifier.probe = lambda target: (False, "HTTP 521")

    def open_issue(self, verdict="upstream-unavailable"):
        return {
            "number": 42,
            "title": "import failure: X",
            "body": f"{notifier.MARKER}{verdict} -->",
        }

    def test_first_failure_opens_an_issue(self):
        self.stub_api(gets={"issues": []})
        self.run_main({"x": "failure"})
        self.assertIn(("POST", f"/repos/{notifier.REPO}/issues"), self.writes())

    def test_unchanged_verdict_stays_quiet(self):
        self.stub_api(gets={r"issues\?": [self.open_issue()]})
        self.run_main({"x": "failure"})
        self.assertEqual(self.writes(), [])

    def test_changed_verdict_comments_and_refreshes(self):
        self.stub_api(gets={r"issues\?": [self.open_issue("needs-attention")]})
        self.run_main({"x": "failure"})
        methods = [m for m, _ in self.writes()]
        self.assertIn("POST", methods)
        self.assertIn("PATCH", methods)

    def test_recovery_comments_and_closes(self):
        self.stub_api(gets={r"issues\?": [self.open_issue()]})
        self.run_main({"x": "success"})
        self.assertTrue(any("comments" in p for _, p in self.writes()))
        self.assertTrue(
            any(m == "PATCH" for m, _ in self.writes()), "issue should be closed"
        )

    def test_success_with_nothing_open_does_nothing(self):
        self.stub_api(gets={"issues": []})
        self.run_main({"x": "success"})
        self.assertEqual(self.writes(), [])

    def test_skipped_job_is_not_evaluated(self):
        self.stub_api(gets={"issues": []})
        self.run_main({"x": "skipped"})
        self.assertEqual(self.writes(), [])
        self.assertEqual(self.rows[0][4], "not evaluated")


class Resilience(Base):
    """Reporting is the job; it must not be the most brittle part of the run."""

    def test_one_failure_does_not_hide_the_others(self):
        notifier.SOURCES = {k: (k.upper(), ["u"]) for k in ("a", "b", "c")}
        notifier.probe = lambda target: (False, "HTTP 521")
        self.stub_api(gets={"issues": []}, raises=r"issues$")
        code = self.run_main({k: "failure" for k in notifier.SOURCES})
        self.assertEqual([r[0] for r in self.rows], ["a", "b", "c"])
        self.assertEqual(code, 1, "the run must still go red")

    def test_label_failure_still_writes_the_summary(self):
        notifier.SOURCES = {"x": ("X", ["u"])}
        notifier.probe = lambda target: (False, "HTTP 521")
        self.stub_api(
            gets={"workflows": {"workflow_runs": [{"id": 100}]}}, raises=r"/labels"
        )
        code = self.run_main({"x": "failure"})
        self.assertIsNotNone(self.rows, "summary must be written anyway")
        self.assertEqual(code, 1)

    def test_label_failure_holds_back_new_issues(self):
        """An unlabelled issue would be invisible next run, and duplicated."""
        notifier.SOURCES = {"x": ("X", ["u"])}
        notifier.probe = lambda target: (False, "HTTP 521")
        self.stub_api(
            gets={"workflows": {"workflow_runs": [{"id": 100}]}}, raises=r"/labels"
        )
        code = self.run_main({"x": "failure"})
        self.assertEqual(
            [(m, p) for m, p in self.writes() if p.endswith("/issues")],
            [],
            "no issue may be opened while the label is unconfirmed",
        )
        self.assertIn("label could not be confirmed", self.rows[0][4])
        self.assertEqual(code, 1)

    def test_label_failure_still_closes_a_recovered_issue(self):
        """Anything findable was labelled when it was opened, so recovery runs."""
        notifier.SOURCES = {"x": ("X", ["u"])}
        open_issue = {"number": 42, "title": "import failure: X", "body": ""}
        self.stub_api(
            gets={
                "workflows": {"workflow_runs": [{"id": 100}]},
                r"issues\?": [open_issue],
            }
        )
        self.run_main({"x": "success"})
        self.assertTrue(any("comments" in p for _, p in self.writes()))

    def test_a_superseded_run_changes_nothing(self):
        notifier.SOURCES = {"x": ("X", ["u"])}
        notifier.probe = lambda target: (False, "HTTP 521")
        self.stub_api(gets={"workflows": {"workflow_runs": [{"id": 999}]}})
        self.run_main({"x": "failure"})
        self.assertEqual(self.writes(), [])
        self.assertIn("newer run", self.rows[0][4])

    def test_the_newest_run_does_act(self):
        notifier.SOURCES = {"x": ("X", ["u"])}
        notifier.probe = lambda target: (False, "HTTP 521")
        self.stub_api(
            gets={"workflows": {"workflow_runs": [{"id": 100}]}, "issues": []}
        )
        self.run_main({"x": "failure"})
        self.assertNotEqual(self.writes(), [])


class Drift(Base):
    """SOURCES and the calling workflow must not quietly diverge.

    A test used to read content's import.yaml and compare it against SOURCES.
    This action lives in a different repository now and cannot, so the check
    moved into the script, against the job list the caller passes in at
    runtime -- which is the real list, not a parsed approximation of it.
    """

    def test_a_job_with_no_upstream_is_reported(self):
        notifier.SOURCES = {"known": ("Known", ["u"])}
        notifier.probe = lambda target: (True, "HTTP 200")
        self.stub_api(gets={"issues": []})
        self.run_main({"known": "success", "newcomer": "success"})
        rows = {row[0]: row[4] for row in self.rows}
        self.assertIn("newcomer", rows, "an unprobed importer must still be listed")
        self.assertIn("no upstream configured", rows["newcomer"])

    def test_an_unconfigured_job_that_failed_makes_the_run_red(self):
        """Otherwise a red import is followed by a green notifier saying nothing.

        This is the drift that matters: someone adds an importer to the
        workflow, does not add it here, and its failures are silent -- the
        exact outcome the notifier exists to prevent.
        """
        notifier.SOURCES = {"known": ("Known", ["u"])}
        notifier.probe = lambda target: (True, "HTTP 200")
        self.stub_api(gets={"issues": []})
        code = self.run_main({"known": "success", "newcomer": "failure"})
        self.assertEqual(code, 1)

    def test_no_issue_is_opened_for_an_unconfigured_job(self):
        """It is reported, not acted on: there is no resource to probe."""
        notifier.SOURCES = {}
        self.stub_api(gets={"issues": []})
        self.run_main({"newcomer": "failure"})
        self.assertEqual(self.writes(), [])

    def test_every_source_has_at_least_one_target(self):
        importlib.reload(notifier)
        for name, (_, targets) in notifier.SOURCES.items():
            with self.subTest(source=name):
                self.assertTrue(targets)


class Manifest(unittest.TestCase):
    """action.yml is the seam between the two repositories; it has to match."""

    # Set by the runner for every step, so the action does not pass them.
    RUNNER_PROVIDED: ClassVar[set] = {
        "GITHUB_REPOSITORY",
        "GITHUB_SERVER_URL",
        "GITHUB_RUN_ID",
        "GITHUB_STEP_SUMMARY",
    }

    def setUp(self):
        importlib.reload(notifier)
        with open(ACTION) as handle:
            self.text = handle.read()

    def test_every_env_var_the_script_reads_is_passed_by_the_action(self):
        """A new os.environ.get in the script is inert until it is plumbed here."""
        with open(SCRIPT) as handle:
            source = handle.read()
        read = set(re.findall(r'os\.environ\.get\(\s*"([A-Z_]+)"', source))
        block = self.text.split("      env:\n", 1)[1].split("\n      run:", 1)[0]
        passed = set(re.findall(r"^        ([A-Z_]+):", block, re.MULTILINE))
        self.assertTrue(read, "no environment reads found; the regex has rotted")
        for name in sorted(read - self.RUNNER_PROVIDED):
            with self.subTest(var=name):
                self.assertIn(name, passed)

    def test_workflow_file_default_matches_the_script(self):
        block = self.text.split("  workflow-file:", 1)[1].split("  dry-run:", 1)[0]
        default = re.search(r'default:\s*"([^"]+)"', block).group(1)
        os.environ.pop("WORKFLOW_FILE", None)
        importlib.reload(notifier)
        self.assertEqual(notifier.WORKFLOW_FILE, default)

    def test_dry_run_is_mapped_to_the_value_the_script_looks_for(self):
        """The script tests DRY_RUN == "1", but the input is "true"/"false".

        Passing the input straight through would leave every dry run opening
        and closing issues for real.
        """
        self.assertIn("inputs.dry-run == 'true' && '1' || '0'", self.text)

    def test_the_manifest_states_the_permissions_the_caller_must_grant(self):
        """Composite actions cannot request scopes, and a job-level permissions
        map denies every scope it does not name. Saying so where the caller
        looks is all this repository can do -- and losing `actions: read` only
        degrades the stale-run guard, so it is the easiest one to drop.
        """
        declared = set(
            re.findall(r"^#   (\w+):\s+(read|write)\b", self.text, re.MULTILINE)
        )
        # Matched on the declaration lines, not anywhere in the file: the prose
        # underneath mentions `actions: read` too, and an earlier version of
        # this test passed on that alone after the declaration was deleted.
        for scope in (("issues", "write"), ("actions", "read")):
            with self.subTest(scope=scope):
                self.assertIn(scope, declared)


if __name__ == "__main__":
    unittest.main(verbosity=2)
