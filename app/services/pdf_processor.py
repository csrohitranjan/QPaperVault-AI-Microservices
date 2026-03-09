import io
import httpx
import fitz  # PyMuPDF
from PIL import Image

from app.config import settings


async def download_pdf(file_url: str) -> bytes:
    """
    Download a PDF file from the given URL.

    Args:
        file_url: Full URL to the PDF (Cloudinary signed URL).

    Returns:
        Raw PDF bytes.
    """
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        response = await client.get(file_url)
        response.raise_for_status()
        return response.content


def pdf_to_images(pdf_bytes: bytes) -> list[Image.Image]:
    """
    Convert each page of a PDF to optimized PIL Images using PyMuPDF.
    Images are resized to max 800px width to minimize Gemini token usage
    while maintaining readable text quality for OCR.

    Args:
        pdf_bytes: Raw PDF file bytes.

    Returns:
        List of PIL Image objects (one per page).
    """
    images = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        # 1.2x resolution — lighter on tokens
        pix = page.get_pixmap(matrix=fitz.Matrix(1.2, 1.2))
        img_bytes = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_bytes))

        # Resize to max 800px width to reduce Gemini token usage
        max_width = 800
        if img.width > max_width:
            ratio = max_width / img.width
            new_size = (max_width, int(img.height * ratio))
            img = img.resize(new_size, Image.LANCZOS)

        # Convert to RGB (remove alpha channel if present)
        if img.mode == "RGBA":
            img = img.convert("RGB")

        images.append(img)

    doc.close()
    return images
