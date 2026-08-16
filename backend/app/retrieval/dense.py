"""
TeleRAG — Dense Retrieval wrapper
"""
import logging
from typing import List, Dict, Optional, Any

from backend.app.storage.vector_store import VectorStore

logger = logging.getLogger(__name__)


def dense_search(query: str, top_k: int, filter_dict: Optional[Dict[str, Any]]) -> List[Dict]:
    """Perform dense search using ChromaDB."""
    try:
        store = VectorStore.get_instance()
        results = store.search(query=query, top_k=top_k, filter_dict=filter_dict)
        
        # Extract and format results
        formatted = []
        if not results["ids"] or not results["ids"][0]:
            return formatted
            
        ids = results["ids"][0]
        distances = results["distances"][0]
        documents = results["documents"][0]
        metadatas = results["metadatas"][0]
        
        for i in range(len(ids)):
            # Convert cosine distance to a similarity score (approximate depending on distance metric)
            # Assuming L2 or Cosine distance. Chroma default is L2. 
            # Lower distance is better. We'll invert it for RRF scoring consistency.
            distance = distances[i]
            # Simple inversion: score = 1 / (1 + distance)
            score = 1.0 / (1.0 + distance)
            
            formatted.append({
                "chunk_id": ids[i],
                "score": score,
                "text": documents[i],
                "metadata": metadatas[i]
            })
            
        return formatted
    except Exception as e:
        logger.error(f"Dense search failed: {e}")
        return []
