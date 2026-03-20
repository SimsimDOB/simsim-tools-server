from fastapi.testclient import TestClient


def test_ping(client: TestClient):
    """
    Test the /api/ping endpoint returns 200 OK.
    """
    response = client.get("/api/ping")
    assert response.status_code == 200
    assert response.json() is None
