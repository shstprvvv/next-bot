import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Must be set BEFORE any app imports
os.environ["TESTING"] = "1"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-unit-tests-only-do-not-use-in-prod"
os.environ.setdefault("OPENAI_API_KEY", "sk-test-fake")

_test_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_test_db.close()
os.environ["DATABASE_PATH"] = _test_db.name

import pytest
from fastapi.testclient import TestClient

from app.core.database import Base, engine


@pytest.fixture(autouse=True)
def _reset_db():
    """Recreate tables for every test to ensure isolation."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture()
def client():
    from api import app
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture()
def auth_headers(client):
    """Register a test user and return Authorization headers."""
    r = client.post("/api/auth/register", json={
        "email": "fixture@test.com",
        "password": "testpassword123"
    })
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
