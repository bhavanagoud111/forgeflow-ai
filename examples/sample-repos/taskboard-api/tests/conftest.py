import pytest
from fastapi.testclient import TestClient

from taskboard.main import app, store


@pytest.fixture(autouse=True)
def _reset_store():
    store.reset()
    yield
    store.reset()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
