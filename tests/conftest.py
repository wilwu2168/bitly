"""Test configuration — the only place your app gets imported.

Contract:
  - Your app lives in `app/main.py` and exposes `app = FastAPI()`.
  - Your app reads its database path from the DB_PATH environment
    variable (default "links.db"). We overwrite DB_PATH to point at a
    scratch file so the suite never touches your real database.
"""

import os
import tempfile

_SCRATCH_DIR = tempfile.mkdtemp(prefix="pybitly-tests-")
os.environ["DB_PATH"] = os.path.join(_SCRATCH_DIR, "test.db")

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c
