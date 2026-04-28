import os
import tempfile

import pytest
from fastapi.testclient import TestClient

# Before importing the app, point at an isolated SQLite file.
_fd, _TEST_DB_PATH = tempfile.mkstemp(suffix=".talkbi-pytest.db")
os.close(_fd)
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{_TEST_DB_PATH}"


@pytest.fixture(scope="module")
def client() -> TestClient:
    from app.main import app

    with TestClient(app) as c:
        yield c
