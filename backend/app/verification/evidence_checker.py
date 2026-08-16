"""
TeleRAG — Evidence Checker
"""
from typing import List
from backend.app.models.schemas import EvidenceChunk

def check_evidence_sufficiency(evidence: List[EvidenceChunk], threshold: float) -> float:
    """Calculate an aggregated evidence score to determine if we should generate an answer.
    
    Returns a score between 0.0 and 1.0.
    """
    if not evidence:
        return 0.0
        
    # For v0, we can use the max retrieval score (from dense or RRF)
    # If using dense distance directly, it's inverted. 
    # If using RRF, it's a small float. 
    # Let's normalize it to a pseudo-confidence score.
    
    max_score = 0.0
    for e in evidence:
        # Prefer rerank score if available
        if e.rerank_score is not None:
            # CrossEncoder scores are logits, usually between -10 and 10.
            # Sigmoid transformation: 1 / (1 + exp(-score))
            import math
            try:
                score = 1.0 / (1.0 + math.exp(-e.rerank_score))
            except OverflowError:
                score = 0.0 if e.rerank_score < 0 else 1.0
            max_score = max(max_score, score)
        elif e.dense_score is not None:
            max_score = max(max_score, e.dense_score)
            
    return max_score
