"""
TeleRAG — Chunking & Parsing

Splits extracted pages into manageable chunks while preserving context.
"""
import logging
from typing import Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class Chunk(BaseModel):
    text: str
    page: int
    section: Optional[str] = None
    chunk_index: int = 0


def simple_chunk_text(text: str, chunk_size: int = 1024, chunk_overlap: int = 128) -> list[str]:
    """Simple character-based chunking with overlap (fallback)."""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        
        # Try to break at a newline or space if not at the very end
        if end < len(text):
            last_newline = text.rfind('\n', start, end)
            if last_newline != -1 and last_newline > start + chunk_size // 2:
                end = last_newline + 1
            else:
                last_space = text.rfind(' ', start, end)
                if last_space != -1 and last_space > start + chunk_size // 2:
                    end = last_space + 1
                    
        chunks.append(text[start:end].strip())
        
        next_start = end - chunk_overlap
        
        # Ensure we always move forward to prevent infinite loops
        if next_start <= start:
            start = start + 1
        else:
            start = next_start
            
    return [c for c in chunks if c]


def chunk_pages(pages: list, chunk_size: int = 1024, chunk_overlap: int = 128) -> list[Chunk]:
    """Chunk a list of ExtractedPage objects.
    
    For v0, we use a simplistic approach: chunk within pages to strictly preserve 
    page metadata. This means chunks don't cross page boundaries, which is great 
    for strict citations but might occasionally break sentences across pages.
    """
    logger.info(f"Chunking {len(pages)} pages (size={chunk_size}, overlap={chunk_overlap})")
    all_chunks = []
    chunk_idx = 0
    
    for page in pages:
        if not page.text.strip():
            continue
            
        text_chunks = simple_chunk_text(page.text, chunk_size, chunk_overlap)
        
        for tc in text_chunks:
            if len(tc) < 50:  # Skip tiny garbage chunks
                continue
            all_chunks.append(Chunk(
                text=tc,
                page=page.page_number,
                section=None,  # Section extraction could be added here by regexing headings
                chunk_index=chunk_idx
            ))
            chunk_idx += 1
            
    logger.info(f"Generated {len(all_chunks)} chunks.")
    return all_chunks

class DocumentChunk(BaseModel):
    id: str
    text: str
    metadata: dict
    chunk_id: str
    specification: str
    version: str
    release: str
    section: Optional[str] = None
    page: int
    chunk_index: int

    def __getitem__(self, item):
        return getattr(self, item)


def chunk_specification(
    pages: list, 
    specification: str, 
    version: str, 
    release: str, 
    chunk_size: int = 1024, 
    chunk_overlap: int = 128
) -> list[DocumentChunk]:
    """
    Chunk extracted pages and package them with required VectorStore and MetadataStore fields.
    """
    base_chunks = chunk_pages(pages, chunk_size, chunk_overlap)
    doc_chunks = []
    
    for c in base_chunks:
        chunk_id = f"{specification}_{version}_{c.page}_{c.chunk_index}"
        doc_chunks.append(DocumentChunk(
            id=chunk_id,
            text=c.text,
            metadata={
                "specification": specification,
                "version": version,
                "release": release,
                "page": c.page,
                "section": c.section or ""
            },
            chunk_id=chunk_id,
            specification=specification,
            version=version,
            release=release,
            section=c.section,
            page=c.page,
            chunk_index=c.chunk_index
        ))
        
    return doc_chunks
