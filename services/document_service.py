"""Document parsing service for contract text extraction."""

import os
from PyPDF2 import PdfReader
from config import Config


def allowed_file(filename):
    """Check if the file extension is allowed."""
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in Config.ALLOWED_EXTENSIONS
    )


def extract_text(filepath):
    """
    Extract text content from uploaded document.

    Supports: PDF, TXT files.

    Args:
        filepath: Path to the uploaded file.

    Returns:
        Extracted text content as a string.
    """
    ext = os.path.splitext(filepath)[1].lower()

    if ext == ".pdf":
        return _extract_pdf(filepath)
    elif ext == ".txt":
        return _extract_txt(filepath)
    else:
        return ""


def _extract_pdf(filepath):
    """Extract text from a PDF file."""
    text_parts = []
    reader = PdfReader(filepath)
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text_parts.append(page_text)
    return "\n".join(text_parts)


def _extract_txt(filepath):
    """Extract text from a plain text file."""
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()
