from fastapi import UploadFile
from pathlib import Path
import fitz
import logging
from enum import Enum
from io import BytesIO
import pillow_heif
from PIL import Image, ImageOps


MAX_IMAGE_SIZE = 1024 * 800  # 800 KB
RESIZE_PERCENTAGE = 20


class AllowedExtension(str, Enum):
    PDF = "pdf"
    JPG = "jpg"
    JPEG = "jpeg"
    PNG = "png"
    HEIC = "heic"
    HEIF = "heif"


def _resize_image(image: Image.Image, image_size: int) -> Image.Image:
    if image_size > MAX_IMAGE_SIZE:
        logging.info(f"Image size exceeds {MAX_IMAGE_SIZE} bytes, resizing.")
        logging.debug(
            f"Original image dimensions: {image.width}x{image.height}, size: {image_size} bytes"
        )

        new_width = image.width * RESIZE_PERCENTAGE // 100
        new_height = image.height * RESIZE_PERCENTAGE // 100
        image = image.resize((new_width, new_height))

    return image


def _save_image_bytes(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=85, optimize=True)
    return buffer.getvalue()


def _insert_image_to_pdf(image: Image.Image, merged_pdf: fitz.Document) -> None:
    image_bytes = _save_image_bytes(image)
    rect = fitz.Rect(0, 0, image.width, image.height)

    logging.info("Inserting image as PDF page.")
    logging.debug(
        f"Image dimensions: {image.width}x{image.height}, size: {len(image_bytes)} bytes"
    )

    page = merged_pdf.new_page(width=rect.width, height=rect.height)
    page.insert_image(rect, stream=image_bytes)


def _merge_image(file_bytes: bytes, file_name: str | None, merged_pdf: fitz.Document) -> None:
    pillow_heif.register_heif_opener()

    logging.info(f"Merging image file: {file_name}")

    image = Image.open(BytesIO(file_bytes)).convert("RGB")

    image = _resize_image(image, len(file_bytes))
    image = ImageOps.exif_transpose(image)

    _insert_image_to_pdf(image, merged_pdf)

    image.close()


def _merge_pdf(file_bytes: bytes, file_name: str | None, merged_pdf: fitz.Document) -> None:
    logging.info(f"Merging PDF file: {file_name}")

    with fitz.open(stream=file_bytes, filetype="pdf") as src_pdf:
        logging.info("Inserting PDF pages.")
        merged_pdf.insert_pdf(src_pdf)


def _save_pdf_bytes(merged_pdf: fitz.Document) -> BytesIO:
    merged_bytes = BytesIO()
    merged_pdf.save(merged_bytes)
    merged_pdf.close()
    merged_bytes.seek(0)

    return merged_bytes


async def merge_pdfs(files: list[UploadFile]) -> BytesIO:
    try:
        merged_pdf = fitz.open()

        logging.info(f"Starting to merge {len(files)} files.")

        for file in files:
            logging.info(f"Processing file: {file.filename}")
            ext_str = Path(file.filename or "").suffix.lower().lstrip(".")

            try:
                ext = AllowedExtension(ext_str)
            except ValueError:
                error_msg = f"Unsupported file type: {file.filename}"
                logging.error(error_msg)
                raise ValueError(error_msg)

            file_bytes = await file.read()

            if ext == AllowedExtension.PDF:
                _merge_pdf(file_bytes, file.filename, merged_pdf)
            else:
                _merge_image(file_bytes, file.filename, merged_pdf)

        merged_bytes = _save_pdf_bytes(merged_pdf)

        logging.info("PDF merging completed successfully.")

        return merged_bytes
    except Exception as error:
        logging.error(f"Error merging PDFs: {error}")
        raise error
