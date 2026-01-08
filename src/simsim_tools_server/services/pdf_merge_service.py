from fastapi import UploadFile
from pathlib import Path
import fitz
import logging
from enum import Enum
from io import BytesIO
import pillow_heif
from PIL import Image


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

                if ext in (AllowedExtension.HEIC, AllowedExtension.HEIF):
                    logging.info(f"Merging HEIC/HEIF image: {file.filename}")

                    image = Image.open(BytesIO(file_bytes)).convert("RGB")
                    buf = BytesIO()
                    image.save(buf, format="PNG")
                    image_bytes = buf.getvalue()
                    rect = fitz.Rect(0, 0, image.width, image.height)
                else:
                    logging.info(f"Merging image file: {file.filename}")

                    image = fitz.open(stream=file_bytes, filetype=ext.value)
                    rect = image[0].rect
                    image_bytes = file_bytes
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
