"""
TeleRAG — Sparse Retrieval (BM25)
"""
import logging
import pickle
from pathlib import Path
from typing import List, Dict, Optional

from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)


class BM25Store:
    """Singleton for BM25 sparse retrieval."""
    _instance = None
    
    @classmethod
    def initialize(cls, index_path: Path):
        if cls._instance is None:
            cls._instance = cls(index_path)
            
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            raise RuntimeError("BM25Store not initialized. Call initialize() first.")
        return cls._instance
        
    def __init__(self, index_path: Path):
        self.index_path = index_path
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.bm25: Optional[BM25Okapi] = None
        self.chunk_ids: List[str] = []
        
        self.load_index()

    def tokenize(self, text: str) -> List[str]:
        # Simple whitespace/punctuation tokenizer for BM25
        # In a real system, might use a better telecom-aware tokenizer
        import string
        text = text.lower()
        text = text.translate(str.maketrans(string.punctuation, ' ' * len(string.punctuation)))
        return text.split()

    def build_index(self, chunks: List[dict]):
        """Build BM25 index from chunks and save to disk."""
        logger.info(f"Building BM25 index from {len(chunks)} chunks...")
        self.chunk_ids = [c["id"] for c in chunks]
        tokenized_corpus = [self.tokenize(c["text"]) for c in chunks]
        self.bm25 = BM25Okapi(tokenized_corpus)
        
        self.save_index()
        logger.info("BM25 index built successfully.")

    def save_index(self):
        if self.bm25 is None:
            return
            
        data = {
            "bm25": self.bm25,
            "chunk_ids": self.chunk_ids
        }
        with open(self.index_path, "wb") as f:
            pickle.dump(data, f)
            
    def load_index(self):
        if self.index_path.exists():
            try:
                with open(self.index_path, "rb") as f:
                    data = pickle.load(f)
                    self.bm25 = data["bm25"]
                    self.chunk_ids = data["chunk_ids"]
                logger.info(f"Loaded BM25 index with {len(self.chunk_ids)} documents.")
            except Exception as e:
                logger.error(f"Failed to load BM25 index: {e}")

    def search(self, query: str, top_k: int = 10, valid_chunk_ids: Optional[List[str]] = None) -> List[Dict]:
        """Search BM25 index.
        valid_chunk_ids: Optional list of chunk IDs allowed by metadata filter.
        """
        if self.bm25 is None:
            return []
            
        tokenized_query = self.tokenize(query)
        # BM25 scores
        scores = self.bm25.get_scores(tokenized_query)
        
        # Zip with IDs and sort
        results = list(zip(self.chunk_ids, scores))
        
        # Apply metadata filter
        if valid_chunk_ids is not None:
            valid_set = set(valid_chunk_ids)
            results = [r for r in results if r[0] in valid_set]
            
        # Sort descending
        results.sort(key=lambda x: x[1], reverse=True)
        
        # Return top_k
        top_results = results[:top_k]
        
        return [{"chunk_id": chunk_id, "score": score} for chunk_id, score in top_results if score > 0]

    def remove_by_ids(self, chunk_ids_to_remove: List[str]):
        """Remove specific chunk IDs from the BM25 index and rebuild."""
        if not chunk_ids_to_remove or self.bm25 is None:
            return
            
        remove_set = set(chunk_ids_to_remove)
        # We need to rebuild BM25 from remaining documents
        # BM25Okapi doesn't support incremental removal, so we filter and rebuild
        remaining_ids = []
        remaining_docs = []
        
        # We need the original tokenized corpus — BM25Okapi stores it internally
        # The safest approach is to rebuild from the corpus attribute
        corpus = self.bm25.corpus  # BM25Okapi stores tokenized docs
        
        for i, chunk_id in enumerate(self.chunk_ids):
            if chunk_id not in remove_set and i < len(corpus):
                remaining_ids.append(chunk_id)
                remaining_docs.append(corpus[i])
                
        if remaining_docs:
            self.chunk_ids = remaining_ids
            self.bm25 = BM25Okapi(remaining_docs)
            self.save_index()
            logger.info(f"Removed {len(chunk_ids_to_remove)} chunks. BM25 index rebuilt with {len(remaining_ids)} documents.")
        else:
            self.chunk_ids = []
            self.bm25 = None
            self.save_index()
            logger.info("BM25 index is now empty after removal.")

    def add_chunks(self, chunks: List[dict]):
        """Add new chunks to the existing BM25 index incrementally."""
        if not chunks:
            return
            
        new_ids = [c["id"] for c in chunks]
        new_tokenized = [self.tokenize(c["text"]) for c in chunks]
        
        if self.bm25 is not None and self.chunk_ids:
            # Rebuild with combined corpus
            existing_corpus = list(self.bm25.corpus)
            all_corpus = existing_corpus + new_tokenized
            all_ids = self.chunk_ids + new_ids
            self.chunk_ids = all_ids
            self.bm25 = BM25Okapi(all_corpus)
        else:
            self.chunk_ids = new_ids
            self.bm25 = BM25Okapi(new_tokenized)
            
        self.save_index()
        logger.info(f"Added {len(chunks)} chunks to BM25 index. Total: {len(self.chunk_ids)}")
