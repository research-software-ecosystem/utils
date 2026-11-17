#!/usr/bin/env python3
"""Validate debian-med files imported into the content repository.

Usage: python validate.py <path-to-content-checkout>
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))

from validation_runner import main

SOURCE = "debian-med"
SCHEMA = Path(__file__).with_name("schema.json")
GLOBS = ["imports/debian-med/*.debian.yaml", "data/*/*.debian.yaml"]

if __name__ == "__main__":
    raise SystemExit(main(SOURCE, SCHEMA, GLOBS))
