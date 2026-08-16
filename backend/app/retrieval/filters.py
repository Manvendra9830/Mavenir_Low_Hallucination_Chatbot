"""
TeleRAG — Metadata filter construction for ChromaDB
"""
from typing import List, Dict, Any, Optional


def build_metadata_filter(release: str, specifications: List[str]) -> Optional[Dict[str, Any]]:
    """Build a ChromaDB metadata filter dictionary.
    
    Example:
    {
        "$and": [
            {"release": {"$eq": "18"}},
            {"specification": {"$in": ["TS 23.501", "TS 23.502"]}}
        ]
    }
    """
    if not specifications:
        return {"release": {"$eq": str(release)}}
        
    return {
        "$and": [
            {"release": {"$eq": str(release)}},
            {"specification": {"$in": specifications}}
        ]
    }
