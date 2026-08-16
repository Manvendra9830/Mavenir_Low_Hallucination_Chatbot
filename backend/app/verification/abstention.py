"""
TeleRAG — Abstention Logic
"""
import logging
from backend.app.models.schemas import GroundingStatus

logger = logging.getLogger(__name__)


def evaluate_abstention(
    evidence_score: float, 
    evidence_threshold: float, 
    valid_citations_count: int,
    total_claims: int
) -> GroundingStatus:
    """Evaluate if the system should abstain from answering."""
    status = GroundingStatus(
        evidence_found=evidence_score >= evidence_threshold,
        evidence_score=evidence_score,
        citation_validated=valid_citations_count > 0,
        claims_verified=True,  # Simplified for v0
    )
    
    if not status.evidence_found:
        status.abstained = True
        status.abstention_reason = "Insufficient evidence in selected specifications."
        logger.warning(f"Abstaining: Evidence score {evidence_score:.2f} < threshold {evidence_threshold}")
        
    elif total_claims > 0 and valid_citations_count == 0:
        status.abstained = True
        status.abstention_reason = "Answer contained claims but no valid citations to retrieved evidence."
        logger.warning("Abstaining: Hallucinated citations detected.")
        
    return status

def get_abstention_message() -> str:
    return "I could not find sufficient evidence in the selected 3GPP standards to answer this question."
