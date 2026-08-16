"""
TeleRAG — Claim Extraction
"""
import re
from typing import List

def extract_claims(answer: str) -> List[str]:
    """Extract factual claims from an answer for verification.
    
    For v0, this is a simplified heuristic:
    We split by sentences and filter out obvious conversational filler.
    In a real system, an LLM would extract atomic claims.
    """
    # Simple sentence splitting
    sentences = re.split(r'(?<=[.!?])\s+', answer)
    claims = []
    
    for s in sentences:
        s = s.strip()
        if not s:
            continue
            
        # Ignore conversational filler
        lower_s = s.lower()
        if lower_s.startswith(("based on the", "according to the", "the provided evidence")):
            continue
            
        # If it contains a citation, it's a claim
        if "[CHUNK_ID:" in s or "]" in s:
            claims.append(s)
        elif len(s) > 15: # Arbitrary threshold for a substantive sentence
            claims.append(s)
            
    return claims
