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


async def merge_pdfs(files: list[UploadFile]) -> BytesIO:
    def resize_image(image: Image.Image) -> Image.Image:
        if len(file_bytes) > MAX_IMAGE_SIZE:
            logging.info(f"Image size exceeds {MAX_IMAGE_SIZE} bytes, resizing.")
            logging.debug(
                f"Original image dimensions: {image.width}x{image.height}, size: {len(file_bytes)} bytes"
            )

            new_width = image.width * RESIZE_PERCENTAGE // 100
            new_height = image.height * RESIZE_PERCENTAGE // 100
            image = image.resize((new_width, new_height))

        return image

    def save_image_bytes(image: Image.Image) -> bytes:
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=85, optimize=True)
        return buffer.getvalue()

    def insert_image_to_pdf(image: Image.Image, merged_pdf: fitz.Document) -> None:
        image_bytes = save_image_bytes(image)
        rect = fitz.Rect(0, 0, image.width, image.height)

        logging.info("Inserting image as PDF page.")
        logging.debug(
            f"Image dimensions: {image.width}x{image.height}, size: {len(image_bytes)} bytes"
        )

        page = merged_pdf.new_page(width=rect.width, height=rect.height)
        page.insert_image(rect, stream=image_bytes)

    def merge_image(file_bytes: bytes, merged_pdf: fitz.Document) -> None:
        pillow_heif.register_heif_opener()

        logging.info(f"Merging image file: {file.filename}")

        image = Image.open(BytesIO(file_bytes)).convert("RGB")

        image = resize_image(image)
        image = ImageOps.exif_transpose(image)

        insert_image_to_pdf(image, merged_pdf)

        image.close()

    def merge_pdf(file_bytes: bytes, merged_pdf: fitz.Document) -> None:
        logging.info(f"Merging PDF file: {file.filename}")

        with fitz.open(stream=file_bytes, filetype=ext.value) as src_pdf:
            logging.info("Inserting PDF pages.")
            merged_pdf.insert_pdf(src_pdf)

    def save_pdf_bytes(merged_pdf: fitz.Document) -> BytesIO:
        merged_bytes = BytesIO()
        merged_pdf.save(merged_bytes)
        merged_pdf.close()
        merged_bytes.seek(0)

        return merged_bytes

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
                merge_pdf(file_bytes, merged_pdf)
            else:
                merge_image(file_bytes, merged_pdf)

        merged_bytes = save_pdf_bytes(merged_pdf)

        logging.info("PDF merging completed successfully.")

        return merged_bytes
    except Exception as error:
        logging.error(f"Error merging PDFs: {error}")
        raise error
