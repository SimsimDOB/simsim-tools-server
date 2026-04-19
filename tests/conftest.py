import pytest
from fastapi.testclient import TestClient

from simsim_tools_server.main import app


@pytest.fixture
def client():
    """
    Create a fresh TestClient for each test.
    """
    return TestClient(app)
