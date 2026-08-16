"""
TeleRAG — Evaluation Metrics
"""
from typing import List, Dict


def recall_at_k(retrieved_ids: List[str], relevant_ids: List[str], k: int) -> float:
    """Recall@K: proportion of relevant documents found in top-K."""
    if not relevant_ids:
        return 0.0
    top_k = set(retrieved_ids[:k])
    relevant = set(relevant_ids)
    return len(top_k & relevant) / len(relevant)


def mrr(retrieved_ids: List[str], relevant_ids: List[str]) -> float:
    """Mean Reciprocal Rank: 1/rank of the first relevant result."""
    relevant = set(relevant_ids)
    for i, rid in enumerate(retrieved_ids, 1):
        if rid in relevant:
            return 1.0 / i
    return 0.0


def citation_accuracy(valid_citation_count: int, total_citation_count: int) -> float:
    """Proportion of citations that are validated against retrieved evidence."""
    if total_citation_count == 0:
        return 1.0  # No citations attempted = no hallucinated citations
    return valid_citation_count / total_citation_count


def abstention_accuracy(abstained: bool, is_answerable: bool) -> bool:
    """True if system correctly abstained on unanswerable or correctly answered on answerable."""
    if is_answerable:
        return not abstained  # Should NOT abstain on answerable
    else:
        return abstained  # SHOULD abstain on unanswerable
