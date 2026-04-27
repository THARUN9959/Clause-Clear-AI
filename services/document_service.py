"""Document parsing service for contract text extraction.

Supports:
  - PDF  (text-based, via PyPDF2)
  - PDF  (image/scanned, via pytesseract OCR fallback)
  - TXT  (plain text)
  - DOCX (Word documents, via python-docx)
  - PNG / JPG / JPEG (scanned contract images, via pytesseract OCR)
"""

import os
import logging

from PyPDF2 import PdfReader
from config import Config

logger = logging.getLogger(__name__)

# ── Optional imports (graceful degradation if not installed) ──────────────────

try:
    from docx import Document as DocxDocument
    _DOCX_AVAILABLE = True
except ImportError:
    _DOCX_AVAILABLE = False
    logger.warning("python-docx not installed — DOCX uploads will not be supported.")

try:
    import pytesseract
    from PIL import Image
    _OCR_AVAILABLE = True
except ImportError:
    _OCR_AVAILABLE = False
    logger.warning("pytesseract / Pillow not installed — OCR fallback will not be available.")


# ── Public helpers ────────────────────────────────────────────────────────────

def allowed_file(filename: str) -> bool:
    """Check if the file extension is allowed."""
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in Config.ALLOWED_EXTENSIONS
    )


def extract_text(filepath: str) -> str:
    """
    Extract text content from an uploaded document.

    Strategy:
      1. PDF  → try text-layer extraction first; if empty, fall back to OCR.
      2. TXT  → read as UTF-8.
      3. DOCX → extract paragraphs via python-docx.
      4. Image (PNG/JPG/JPEG) → OCR via pytesseract.

    Args:
        filepath: Absolute path to the uploaded file.

    Returns:
        Extracted text as a string (may be empty if extraction fails).
    """
    ext = os.path.splitext(filepath)[1].lower()

    if ext == ".pdf":
        text = _extract_pdf_text(filepath)
        if not text.strip() and _OCR_AVAILABLE:
            # Scanned / image-only PDF — fall back to page-level OCR
            logger.info("PDF text layer empty; attempting OCR fallback: %s", filepath)
            text = _extract_pdf_ocr(filepath)
        return text

    elif ext == ".txt":
        return _extract_txt(filepath)

    elif ext == ".docx":
        return _extract_docx(filepath)

    elif ext in {".png", ".jpg", ".jpeg"}:
        return _extract_image_ocr(filepath)

    return ""


# ── Private extractors ────────────────────────────────────────────────────────

def _extract_pdf_text(filepath: str) -> str:
    """Extract selectable text from a PDF using PyPDF2."""
    text_parts = []
    try:
        reader = PdfReader(filepath)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    except Exception as exc:
        logger.error("PyPDF2 error for %s: %s", filepath, exc)
    return "\n".join(text_parts)


def _extract_pdf_ocr(filepath: str) -> str:
    """
    OCR fallback for scanned PDFs.

    Converts each PDF page to an image using pdf2image (if available),
    then runs Tesseract on each page image.
    If pdf2image is not installed, logs a helpful error and returns empty string.
    """
    try:
        from pdf2image import convert_from_path  # optional heavy dependency
    except ImportError:
        logger.warning(
            "pdf2image not installed — cannot OCR scanned PDFs. "
            "Run: pip install pdf2image  (also requires poppler on PATH)."
        )
        return ""

    text_parts = []
    try:
        pages = convert_from_path(filepath, dpi=200)
        for page_img in pages:
            page_text = pytesseract.image_to_string(page_img)
            if page_text:
                text_parts.append(page_text)
    except Exception as exc:
        logger.error("OCR PDF error for %s: %s", filepath, exc)
    return "\n".join(text_parts)


def _extract_txt(filepath: str) -> str:
    """Extract text from a plain-text file."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except Exception as exc:
        logger.error("TXT read error for %s: %s", filepath, exc)
        return ""


def _extract_docx(filepath: str) -> str:
    """Extract text from a Word (.docx) file using python-docx."""
    if not _DOCX_AVAILABLE:
        return ""
    try:
        doc = DocxDocument(filepath)
        parts = []
        for para in doc.paragraphs:
            if para.text.strip():
                parts.append(para.text)
        # Also extract text from tables
        for table in doc.tables:
            for row in table.rows:
                row_text = " | ".join(
                    cell.text.strip() for cell in row.cells if cell.text.strip()
                )
                if row_text:
                    parts.append(row_text)
        return "\n".join(parts)
    except Exception as exc:
        logger.error("DOCX extraction error for %s: %s", filepath, exc)
        return ""


def _extract_image_ocr(filepath: str) -> str:
    """Run Tesseract OCR on a standalone image file (PNG/JPG/JPEG)."""
    if not _OCR_AVAILABLE:
        return ""
    try:
        img = Image.open(filepath)
        return pytesseract.image_to_string(img)
    except Exception as exc:
        logger.error("Image OCR error for %s: %s", filepath, exc)
        return ""
