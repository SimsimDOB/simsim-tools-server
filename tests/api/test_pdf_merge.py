import zipfile
from io import BytesIO

import fitz
from fastapi.testclient import TestClient
from PIL import Image


def _jpeg_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (40, 30), "red").save(buffer, format="JPEG")
    return buffer.getvalue()


def _page_count(pdf_bytes: bytes) -> int:
    with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
        return pdf.page_count


def test_pdf_merge_accepts_jfif(client: TestClient):
    """
    A .jfif upload (a JPEG under another extension) becomes one PDF page.
    """
    response = client.post(
        "/api/v1/pdf-merge",
        files=[("files", ("photo.jfif", _jpeg_bytes(), "image/jpeg"))],
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert _page_count(response.content) == 1


def test_pdf_merge_accepts_jfif_in_zip(client: TestClient):
    """
    A .jfif entry inside a ZIP is merged rather than skipped.
    """
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("photo.jfif", _jpeg_bytes())

    response = client.post(
        "/api/v1/pdf-merge",
        files=[("files", ("photos.zip", zip_buffer.getvalue(), "application/zip"))],
    )
    assert response.status_code == 200
    assert _page_count(response.content) == 1


def test_pdf_merge_rejects_unsupported_extension(client: TestClient):
    response = client.post(
        "/api/v1/pdf-merge",
        files=[("files", ("notes.txt", b"hello", "text/plain"))],
    )
    assert response.status_code == 500
