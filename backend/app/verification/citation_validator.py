"""
TeleRAG — Citation Validator
"""
import re
import logging
from typing import List, Dict

from backend.app.models.schemas import Citation, EvidenceChunk

logger = logging.getLogger(__name__)


def extract_citations_from_text(text: str) -> List[str]:
    """Extract chunk IDs from text formatted as [CHUNK_ID: <id>] or [<id1>, <id2>]."""
    found_ids = []
    # Find everything inside brackets
    bracket_contents = re.findall(r'\[(.*?)\]', text)
    for content in bracket_contents:
        # Remove 'CHUNK_ID:' prefix if present, then split by comma or whitespace
        cleaned = re.sub(r'^CHUNK_ID:\s*', '', content)
        parts = re.split(r'[,;\s]+', cleaned)
        for p in parts:
            p = p.strip()
            # Match our chunk ID pattern: alphanumeric, dots, underscores, hyphens, min 10 chars
            if re.match(r'^[a-zA-Z0-9_.-]{10,}$', p):
                found_ids.append(p)
    return list(set(found_ids))


def validate_citations(answer: str, retrieved_evidence: List[EvidenceChunk]) -> List[Citation]:
    """Validate that citations in the answer actually exist in the retrieved evidence."""
    found_ids = extract_citations_from_text(answer)
    valid_citations = []
    
    evidence_map = {e.chunk_id: e for e in retrieved_evidence}
    
    for cid in found_ids:
        if cid in evidence_map:
            ev = evidence_map[cid]
            valid_citations.append(Citation(
                specification=ev.specification,
                version=ev.version,
                release=ev.release,
                section=ev.section,
                page=ev.page,
                source_filename=f"{ev.specification.replace(' ', '')}-{ev.release}00.zip",  # Mocked
                chunk_id=ev.chunk_id
            ))
        else:
            logger.warning(f"Hallucinated citation detected: {cid}")
            
    return valid_citations
