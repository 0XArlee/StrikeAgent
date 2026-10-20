"""The original indicator is the immutable reference specification: fail loudly if it changes."""

import hashlib
from pathlib import Path

import pytest

from smartflow import REFERENCE_SCRIPT, REFERENCE_SHA256

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(not (ROOT / REFERENCE_SCRIPT).exists(),
                    reason="the proprietary source is never shipped to servers (deploy/bundle.sh)")
def test_reference_script_unchanged():
    data = (ROOT / REFERENCE_SCRIPT).read_bytes()
    assert hashlib.sha256(data).hexdigest() == REFERENCE_SHA256
