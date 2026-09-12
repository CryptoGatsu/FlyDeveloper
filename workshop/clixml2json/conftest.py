"""Make the test data self-healing.

sample.clixml is a normal file in the repo, but if it goes missing (someone
copies just the .py files, a packaging step drops non-code assets, a fly sits
on the delete key) we rewrite it from the constant inside the module so the
tests still describe reality.
"""
from pathlib import Path

import clixml2json


def pytest_configure(config):
    sample = Path(__file__).parent / "sample.clixml"
    if not sample.exists():
        sample.write_text(clixml2json.SAMPLE_CLIXML, encoding="utf-8")
