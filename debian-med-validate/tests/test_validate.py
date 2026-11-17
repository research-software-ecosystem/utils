"""Fixture tests for the debian-med validator.

python3 -m unittest discover -s debian-med-validate/tests -t debian-med-validate/tests
"""

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
FOLDER = HERE.parent
sys.path.insert(0, str(FOLDER.parent / "common"))

from jsonschema import Draft202012Validator
from validation_checks import make_format_checker
from validation_runner import ERROR, validate_file

with open(FOLDER / "schema.json", encoding="utf-8") as fh:
    SCHEMA = json.load(fh)
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=make_format_checker())


class ValidFixtures(unittest.TestCase):
    def test_valid_fixtures_have_no_errors(self):
        fixtures = sorted((HERE / "fixtures" / "valid").iterdir())
        self.assertTrue(fixtures)
        for fixture in fixtures:
            findings = validate_file(str(fixture), VALIDATOR)
            errors = [f for f in findings if f.severity == ERROR]
            self.assertEqual(
                [], [(f.location, f.message) for f in errors], fixture.name
            )


class InvalidFixtures(unittest.TestCase):
    def test_invalid_fixtures_are_rejected(self):
        fixtures = sorted((HERE / "fixtures" / "invalid").iterdir())
        self.assertTrue(fixtures)
        for fixture in fixtures:
            findings = validate_file(str(fixture), VALIDATOR)
            errors = [f for f in findings if f.severity == ERROR]
            self.assertTrue(errors, f"{fixture.name} should have errors")


if __name__ == "__main__":
    unittest.main()
