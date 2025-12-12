import fitz
from PIL import Image
import pytesseract
import re
import traceback
from io import BytesIO
import logging


def count_summonses(pdf_bytes: bytes) -> tuple[int, int, str]:
    try:
        total_count = 0
        pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

        with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
            count = 0
            removed = 0
            pages = []
            logging.info(f"Pdf length: {len(pdf)}")

            images_index = 0
            while images_index < len(pdf):
                img = __page_to_image(pdf.load_page(images_index))
                summonses_str = __get_summonses_str(img)

                # PATTERNS = ["1 summons", "1. summons", "1. summonses", "1 summonses"]
                if re.search(r"1.*summons", summonses_str) or re.search(
                    r"[0-9].*summons[^es]", summonses_str
                ):
                    count += 1
                else:
                    removed += 1
                    pages.append(images_index + 1)
                images_index += 1

                if images_index >= len(pdf):
                    break

                img = __page_to_image(pdf.load_page(images_index))
                skip_pages = __get_skip_pages(img)

                if skip_pages is not None:
                    images_index += skip_pages + 1
                else:
                    summonses_str = __get_summonses_str(img)
                    while not re.search(r"[0-9].*summons", summonses_str):
                        images_index += 1
                        if images_index >= len(pdf):
                            break
                        img = __page_to_image(pdf.load_page(images_index))
                        summonses_str = __get_summonses_str(img)

            total_count += count
            pages_str = ", ".join(map(str, pages))

        return total_count, removed, pages_str
    except Exception as error:
        logging.error(traceback.format_exc())
        raise error


def __page_to_image(page: fitz.Page) -> Image.Image:
    pix = page.get_pixmap(dpi=150)
    png_bytes = pix.tobytes("png")
    return Image.open(BytesIO(png_bytes))


def __get_summonses_str(img: Image.Image) -> str:
    cropped_img = __crop_summonses(img)
    summonses_str = pytesseract.image_to_string(cropped_img, lang="eng").lower()
    return summonses_str


def __crop_summonses(img: Image.Image) -> Image.Image:
    width, height = img.size
    left = width * 0.75
    top = height * 0.15
    right = width
    bottom = height * 0.27
    return img.crop((left, top, right, bottom))


def __crop_pages(img: Image.Image) -> Image.Image:
    width, height = img.size
    left = width * 0.7
    top = height * 0.85
    right = width
    bottom = height
    return img.crop((left, top, right, bottom))


def __get_skip_pages(img: Image.Image) -> int | None:
    pages_img = __crop_pages(img)
    pages_str = pytesseract.image_to_string(pages_img, lang="eng").lower()
    pages = re.search(r"[0-9].*of.*[0-9]", pages_str)
    if pages:
        cur_page, total_page = pages.group().split(" of ")
        cur_page = re.sub(r"[^0-9]", "", cur_page)
        total_page = re.sub(r"[^0-9]", "", total_page)
        return int(total_page) - int(cur_page)
    return None
