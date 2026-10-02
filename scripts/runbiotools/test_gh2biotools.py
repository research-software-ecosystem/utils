"""Tests for gh2biotools.py.

    python3 -m unittest discover -s scripts/runbiotools

Offline: every bio.tools call is stubbed, so the suite neither needs a token
nor touches live records.
"""

import io
import json
import os
import sys
import unittest
from typing import ClassVar
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gh2biotools as g


class DropEdamLabels(unittest.TestCase):
    """The URI identifies the concept; bio.tools supplies the label."""

    def test_a_label_beside_a_uri_is_dropped(self):
        out = g.drop_edam_labels(
            {
                "operation": [
                    {"term": "Formatting", "uri": "http://e.org/operation_0335"}
                ]
            }
        )
        self.assertEqual(out, {"operation": [{"uri": "http://e.org/operation_0335"}]})

    def test_a_label_without_a_uri_is_kept(self):
        """It is the only thing identifying the concept.

        Dropping it fails with "Either the URI or term is required."
        """
        for empty in ({"term": "Formatting"}, {"term": "Formatting", "uri": ""}):
            with self.subTest(value=empty):
                self.assertEqual(g.drop_edam_labels({"t": [empty]})["t"][0], empty)

    def test_every_edam_bearing_field_is_covered(self):
        """Matched on shape, not on field name, so nested ones come free."""
        payload = {
            "topic": [{"term": "Lipids", "uri": "http://e.org/topic_0153"}],
            "function": [
                {
                    "operation": [
                        {"term": "Analysis", "uri": "http://e.org/operation_2945"}
                    ],
                    "input": [
                        {
                            "data": {
                                "term": "Sequence",
                                "uri": "http://e.org/data_2044",
                            },
                            "format": [
                                {"term": "FASTA", "uri": "http://e.org/format_1929"}
                            ],
                        }
                    ],
                    "output": [
                        {"data": {"term": "Report", "uri": "http://e.org/data_2048"}}
                    ],
                }
            ],
        }
        out = g.drop_edam_labels(payload)
        found = []

        def walk(node):
            if isinstance(node, dict):
                if "uri" in node:
                    found.append(node)
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)

        walk(out)
        self.assertEqual(len(found), 5, "all five EDAM entries should be visited")
        for entry in found:
            self.assertNotIn("term", entry)
            self.assertTrue(entry["uri"])

    def test_nothing_else_is_touched(self):
        payload = {
            "name": "affxparser",
            "biotoolsID": "affxparser",
            "description": "a tool",
            "credit": [{"name": "A", "typeEntity": "Person"}],
            "link": [{"url": "https://x.org", "type": ["Repository"]}],
        }
        self.assertEqual(g.drop_edam_labels(payload), payload)

    def test_the_input_is_not_mutated(self):
        payload = {"topic": [{"term": "Lipids", "uri": "http://e.org/topic_0153"}]}
        g.drop_edam_labels(payload)
        self.assertEqual(payload["topic"][0]["term"], "Lipids")


class Response:
    def __init__(self, status_code=200, payload=None, ok=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.ok = (200 <= status_code < 300) if ok is None else ok
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload


class Sync(unittest.TestCase):
    """What actually goes over the wire."""

    STORED: ClassVar[dict] = {
        "name": "affxparser",
        "biotoolsID": "affxparser",
        "function": [
            {
                "operation": [
                    # the label bio.tools serves, and rejects on write
                    {"term": "Formatting", "uri": "http://e.org/operation_0335"}
                ]
            }
        ],
    }

    def setUp(self):
        self.sent = []

        def put(url, headers=None, data=None):
            self.sent.append(("PUT", url, json.loads(data)))
            return Response(200)

        def post(url, headers=None, data=None):
            self.sent.append(("POST", url, json.loads(data)))
            return Response(200)

        self.get_response = Response(200, self.STORED)
        self.requests = mock.MagicMock()
        self.requests.get.side_effect = lambda url, headers=None: self.get_response
        self.requests.put.side_effect = put
        self.requests.post.side_effect = post
        patcher = mock.patch.object(g, "requests", self.requests)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_file(self, payload, **kw):
        return g.process_single_file(io.StringIO(json.dumps(payload)), {}, **kw)

    def test_a_stale_label_alone_is_not_a_difference(self):
        """The whole point of stripping both sides.

        Without it, every EDAM-annotated tool differs from the stored record
        for as long as the label is stale, and is rewritten on every run.
        """
        tool_id, status = self.run_file(self.STORED)
        self.assertEqual((tool_id, status), ("affxparser", "unchanged"))
        self.assertEqual(self.sent, [], "nothing should be written")

    def test_a_label_difference_alone_is_not_a_difference_either(self):
        local = json.loads(json.dumps(self.STORED))
        local["function"][0]["operation"][0]["term"] = "Data formatting"
        _, status = self.run_file(local)
        self.assertEqual(status, "unchanged")

    def test_a_real_change_is_sent_without_any_edam_label(self):
        local = json.loads(json.dumps(self.STORED))
        local["description"] = "a genuinely new description"
        _, status = self.run_file(local)
        self.assertEqual(status, "updated")
        methods = [m for m, _, _ in self.sent]
        self.assertEqual(methods, ["PUT", "PUT"], "validate then update")
        for _, url, body in self.sent:
            op = body["function"][0]["operation"][0]
            self.assertNotIn("term", op, f"{url} still carried an EDAM label")
            self.assertEqual(op["uri"], "http://e.org/operation_0335")

    def test_an_upload_also_sends_no_edam_label(self):
        self.get_response = Response(404)
        _, status = self.run_file(self.STORED)
        self.assertEqual(status, "uploaded")
        self.assertEqual([m for m, _, _ in self.sent], ["POST", "POST"])
        for _, _, body in self.sent:
            self.assertNotIn("term", body["function"][0]["operation"][0])

    def test_validate_only_validates_and_stops(self):
        local = json.loads(json.dumps(self.STORED))
        local["description"] = "changed"
        _, status = self.run_file(local, validate_only=True)
        self.assertEqual(status, "updated", "reported as it would have applied")
        self.assertEqual(len(self.sent), 1, "only the validate call")
        self.assertIn("/validate/", self.sent[0][1])

    def test_validate_only_does_not_upload_either(self):
        self.get_response = Response(404)
        _, status = self.run_file(self.STORED, validate_only=True)
        self.assertEqual(status, "uploaded")
        self.assertEqual(len(self.sent), 1)
        self.assertIn("/validate/", self.sent[0][1])

    def test_a_rejected_record_is_reported_as_failed_validation(self):
        self.requests.put.side_effect = lambda url, headers=None, data=None: Response(
            400, {"detail": "nope"}
        )
        local = json.loads(json.dumps(self.STORED))
        local["description"] = "changed"
        _, status = self.run_file(local)
        self.assertEqual(status, "failed_validation")


if __name__ == "__main__":
    unittest.main(verbosity=2)
