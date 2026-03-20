from fastapi import UploadFile
from pathlib import Path
import fitz
import logging
from enum import Enum
from io import BytesIO
import pillow_heif
from PIL import Image


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
                logging.info(f"Merging PDF file: {file.filename}")

                with fitz.open(stream=file_bytes, filetype=ext.value) as src_pdf:
                    logging.info("Inserting PDF pages.")
                    merged_pdf.insert_pdf(src_pdf)
            else:
                pillow_heif.register_heif_opener()

                logging.info(f"Merging image file: {file.filename}")

                image = Image.open(BytesIO(file_bytes)).convert("RGB")

                if len(file_bytes) > MAX_IMAGE_SIZE:
                    new_width = image.width * RESIZE_PERCENTAGE // 100
                    new_height = image.height * RESIZE_PERCENTAGE // 100
                    image = image.resize((new_width, new_height))

                buffer = BytesIO()
                image.save(buffer, format="PNG")
                image_bytes = buffer.getvalue()
                rect = fitz.Rect(0, 0, image.width, image.height)

                image.close()

                logging.info("Inserting image as PDF page.")
                page = merged_pdf.new_page(width=rect.width, height=rect.height)
                page.insert_image(rect, stream=image_bytes)

        merged_bytes = BytesIO()
        merged_pdf.save(merged_bytes)
        merged_pdf.close()
        merged_bytes.seek(0)

        logging.info("PDF merging completed successfully.")

        return merged_bytes
    except Exception as error:
        logging.error(f"Error merging PDFs: {error}")
        raise error
