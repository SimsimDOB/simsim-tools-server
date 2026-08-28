from unittest.mock import patch

from fastapi.testclient import TestClient

TARGET = (
    "simsim_tools_server.api.v1.endpoints.multi_summonses_count.count_multi_summonses"
)


def test_sums_counts_across_files(client: TestClient):
    """Two files: total_count is the sum, details carry each file."""
    with patch(TARGET, side_effect=[(3, 1, "2"), (4, 0, "")]):
        response = client.post(
            "/api/v1/multi-summonses-count",
            files=[
                ("pdfs", ("a.pdf", b"%PDF-1.4", "application/pdf")),
                ("pdfs", ("b.pdf", b"%PDF-1.4", "application/pdf")),
            ],
        )

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 7
    assert body["details"] == [
        {
            "filename": "a.pdf",
            "count": 3,
            "removed_count": 1,
            "removed_pages": "2",
        },
        {
            "filename": "b.pdf",
            "count": 4,
            "removed_count": 0,
            "removed_pages": "",
        },
    ]


def test_one_bad_file_does_not_sink_the_batch(client: TestClient):
    """A failing file yields an error entry; the other still counts."""
    with patch(TARGET, side_effect=[RuntimeError("boom"), (5, 0, "")]):
        response = client.post(
            "/api/v1/multi-summonses-count",
            files=[
                ("pdfs", ("bad.pdf", b"not a pdf", "application/pdf")),
                ("pdfs", ("good.pdf", b"%PDF-1.4", "application/pdf")),
            ],
        )

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 5
    assert body["details"][0] == {"filename": "bad.pdf", "error": "boom"}
    assert body["details"][1]["count"] == 5
