"""
TeleRAG — Reciprocal Rank Fusion (RRF)
"""
from typing import List, Dict


def reciprocal_rank_fusion(dense_results: List[Dict], sparse_results: List[Dict], k: int = 60) -> List[Dict]:
    """Combines dense and sparse results using Reciprocal Rank Fusion.
    
    RRF Score = 1 / (k + rank_dense) + 1 / (k + rank_sparse)
    """
    rrf_scores = {}
    chunk_data = {}
    
    # Process dense results
    for rank, result in enumerate(dense_results, 1):
        chunk_id = result["chunk_id"]
        if chunk_id not in rrf_scores:
            rrf_scores[chunk_id] = 0.0
            chunk_data[chunk_id] = {
                "chunk_id": chunk_id,
                "text": result.get("text", ""),
                "metadata": result.get("metadata", {}),
                "dense_score": result.get("score", 0.0)
            }
        rrf_scores[chunk_id] += 1.0 / (k + rank)
        
    # Process sparse results
    # Sparse results might not have text/metadata attached if coming directly from rank_bm25 
    # without a lookup, so they rely on dense or a DB fetch to populate text.
    for rank, result in enumerate(sparse_results, 1):
        chunk_id = result["chunk_id"]
        if chunk_id not in rrf_scores:
            rrf_scores[chunk_id] = 0.0
            # If not in dense, we'd need to fetch text/metadata. Handled in query orchestrator.
            chunk_data[chunk_id] = {
                "chunk_id": chunk_id,
                "bm25_score": result.get("score", 0.0)
            }
        rrf_scores[chunk_id] += 1.0 / (k + rank)
        if "bm25_score" not in chunk_data[chunk_id]:
            chunk_data[chunk_id]["bm25_score"] = result.get("score", 0.0)
            
    # Compile final list
    fused = []
    for chunk_id, score in rrf_scores.items():
        data = chunk_data[chunk_id]
        data["rrf_score"] = score
        fused.append(data)
        
    # Sort by RRF score descending
    fused.sort(key=lambda x: x["rrf_score"], reverse=True)
    
    return fused
