"""
TeleRAG — Document Extractor

Extracts text from PDF/DOCX documents while preserving structure.
Focuses on preserving page numbers for citation accuracy.
"""
import logging
from pathlib import Path
from typing import Iterator

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


class ExtractedPage:
    def __init__(self, page_number: int, text: str):
        self.page_number = page_number
        self.text = text


def extract_pdf(filepath: Path) -> Iterator[ExtractedPage]:
    """Extract text from a PDF, yielding ExtractedPage objects."""
    logger.info(f"Extracting PDF: {filepath.name}")
    try:
        with fitz.open(str(filepath)) as doc:
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                # Use "text" dict or blocks if we need more layout control, 
                # but plain text is often fine for 3GPP specs if chunked cleanly.
                text = page.get_text("text")
                # 3GPP docs have header/footer, but for now we take full text.
                # Page numbers in 3GPP are usually physical page = printed page - offset.
                # We'll use the physical page number (1-indexed) as the citation page.
                yield ExtractedPage(page_number=page_num + 1, text=text)
    except Exception as e:
        logger.error(f"Error extracting PDF {filepath.name}: {e}")


def extract_docx(filepath: Path) -> Iterator[ExtractedPage]:
    """Extract text from a DOCX.
    
    DOCX has no strict physical pages. We'll simulate 'pages' by splitting
    text into chunks or treating the whole document as page 1.
    For this prototype, if it's DOCX, we just yield one big page, or break
    by headings. Since we prefer PDF for fidelity, this is a fallback.
    """
    logger.info(f"Extracting DOCX: {filepath.name}")
    try:
        from docx import Document
        doc = Document(str(filepath))
        text = "\n".join([p.text for p in doc.paragraphs])
        # Fallback: Treat as a single 'page' for extraction purposes
        yield ExtractedPage(page_number=1, text=text)
    except ImportError:
        logger.error("python-docx not installed. Cannot extract DOCX.")
    except Exception as e:
        logger.error(f"Error extracting DOCX {filepath.name}: {e}")


def extract_document(filepath: Path) -> list[ExtractedPage]:
    """Extract text from a supported document type."""
    ext = filepath.suffix.lower()
    pages = []
    
    if ext == ".pdf":
        pages = list(extract_pdf(filepath))
    elif ext == ".docx":
        pages = list(extract_docx(filepath))
    else:
        logger.error(f"Unsupported extraction format: {ext}")
        
    return pages
