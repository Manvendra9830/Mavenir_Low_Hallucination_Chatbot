"""
TeleRAG — Cross-Encoder Reranker
"""
import logging
from typing import List, Dict

try:
    from sentence_transformers import CrossEncoder
    HAS_CROSS_ENCODER = True
except ImportError:
    HAS_CROSS_ENCODER = False

logger = logging.getLogger(__name__)


class Reranker:
    """Singleton for CrossEncoder reranking."""
    _instance = None
    
    @classmethod
    def initialize(cls, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        if cls._instance is None:
            cls._instance = cls(model_name)
            
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            # Initialize with default if not done
            cls.initialize()
        return cls._instance
        
    def __init__(self, model_name: str):
        if not HAS_CROSS_ENCODER:
            logger.warning("sentence-transformers not installed. Reranking disabled.")
            self.model = None
            return
            
        logger.info(f"Loading CrossEncoder reranker: {model_name}")
        try:
            self.model = CrossEncoder(model_name)
        except Exception as e:
            logger.error(f"Failed to load reranker: {e}")
            self.model = None

    def rerank(self, query: str, candidates: List[Dict], top_k: int) -> List[Dict]:
        """Rerank candidate chunks using the cross-encoder."""
        if not self.model or not candidates:
            return candidates[:top_k]
            
        # We need text for all candidates
        valid_candidates = [c for c in candidates if c.get("text")]
        if not valid_candidates:
            return []
            
        pairs = [[query, c["text"]] for c in valid_candidates]
        
        try:
            scores = self.model.predict(pairs)
            
            for i, score in enumerate(scores):
                # Float32 from numpy -> standard float for JSON serialization
                valid_candidates[i]["rerank_score"] = float(score)
                
            # Sort descending
            valid_candidates.sort(key=lambda x: x["rerank_score"], reverse=True)
            return valid_candidates[:top_k]
            
        except Exception as e:
            logger.error(f"Reranking failed: {e}")
            return candidates[:top_k]
