"""
TeleRAG — Vector Store (ChromaDB)
"""
import logging
import pickle
from pathlib import Path
from typing import Optional, List, Dict, Any

import chromadb
from chromadb.config import Settings
from chromadb.segment.impl.vector.local_persistent_hnsw import PersistentData
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class VectorStore:
    """Singleton wrapper for ChromaDB."""
    _instance = None

    @classmethod
    def initialize(cls, db_path: Path, model_name: str):
        if cls._instance is None:
            cls._instance = cls(db_path, model_name)

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            raise RuntimeError("VectorStore not initialized. Call initialize() first.")
        return cls._instance

    def __init__(self, db_path: Path, model_name: str):
        self.db_path = db_path
        self.db_path.mkdir(parents=True, exist_ok=True)

        # Use persistent client
        self.client = chromadb.PersistentClient(path=str(self.db_path))
        logger.info(f"Loading embedding model: {model_name}")
        self.embedding_model = SentenceTransformer(model_name)
        self._repair_persistent_index_metadata()

        # We store everything in one collection for 3GPP
        self.collection = self.client.get_or_create_collection(
            name="3gpp_corpus",
            metadata={"description": "3GPP Standards Knowledge Base"}
        )
        # Create a new collection for newly uploaded chunks to avoid 0.4 -> 0.5 migration crash
        self.new_collection = self.client.get_or_create_collection(
            name="3gpp_corpus_v2",
            metadata={"description": "3GPP Standards Knowledge Base (New uploads)"}
        )
        try:
            count = self.collection.count()
            count_new = self.new_collection.count()
            logger.info(f"VectorStore initialized. Baseline count: {count}, New count: {count_new}")
        except Exception as e:
            logger.warning(f"VectorStore initialized at {self.db_path}. Could not get collection count: {e}")

    def _repair_persistent_index_metadata(self) -> None:
        """Migrate old Chroma HNSW metadata pickles to the installed Chroma shape."""
        embedding_dim = self.embedding_model.get_sentence_embedding_dimension()
        for metadata_path in self.db_path.glob("*/index_metadata.pickle"):
            try:
                with open(metadata_path, "rb") as f:
                    data = pickle.load(f)

                if isinstance(data, dict):
                    repaired = PersistentData(
                        dimensionality=data.get("dimensionality") or embedding_dim,
                        total_elements_added=data.get("total_elements_added", 0),
                        id_to_label=data.get("id_to_label", {}),
                        label_to_id=data.get("label_to_id", {}),
                        id_to_seq_id=data.get("id_to_seq_id", {}),
                    )
                elif getattr(data, "dimensionality", None) is None:
                    data.dimensionality = embedding_dim
                    repaired = data
                else:
                    continue

                with open(metadata_path, "wb") as f:
                    pickle.dump(repaired, f)
                logger.info(f"Repaired Chroma index metadata at {metadata_path}")
            except Exception as e:
                logger.warning(f"Could not repair Chroma index metadata at {metadata_path}: {e}")

    def _embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Create embeddings with the configured local sentence-transformers model."""
        embeddings = self.embedding_model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()

    def add_chunks(self, chunks: List[dict]):
        """Add chunks to the collection.
        chunks must be list of dicts: {'id': str, 'text': str, 'metadata': dict}
        """
        if not chunks:
            return

        ids = [c["id"] for c in chunks]
        documents = [c["text"] for c in chunks]
        metadatas = [c["metadata"] for c in chunks]

        # Batch insert to avoid issues
        batch_size = 5000
        try:
            new_col = self.client.get_collection(name="3gpp_corpus_v2")
            for i in range(0, len(ids), batch_size):
                batch_documents = documents[i:i+batch_size]
                try:
                    new_col.add(
                        ids=ids[i:i+batch_size],
                        documents=batch_documents,
                        metadatas=metadatas[i:i+batch_size],
                        embeddings=self._embed_texts(batch_documents),
                    )
                except Exception as e:
                    logger.error(f"Failed to add batch to vector store: {e}")
                    raise e
            logger.info(f"Added {len(chunks)} chunks to vector store (v2 collection).")
        except Exception as e:
            logger.error(f"Failed to get v2 collection: {e}")
            raise e

    def search(self, query: str, top_k: int = 10, filter_dict: Optional[Dict[str, Any]] = None) -> dict:
        """Search the vector store.
        filter_dict format: {"$and": [{"release": "18"}, {"specification": {"$in": ["TS 23.501"]}}]} etc.
        """
        query_embedding = self._embed_texts([query])[0]

        # Query old collection
        results1 = {"ids": [], "distances": [], "documents": [], "metadatas": []}
        try:
            baseline_col = self.client.get_collection(name="3gpp_corpus")
            results1 = baseline_col.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=filter_dict,
                include=["documents", "metadatas", "distances"]
            )
        except Exception as e:
            logger.warning(f"Query on baseline collection failed: {e}")

        # Query new collection
        results2 = {"ids": [], "distances": [], "documents": [], "metadatas": []}
        try:
            new_col = self.client.get_collection(name="3gpp_corpus_v2")
            results2 = new_col.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=filter_dict,
                include=["documents", "metadatas", "distances"]
            )
        except Exception as e:
            logger.warning(f"Query on new collection failed: {e}")

        # Merge results
        combined_ids = (results1.get("ids", [[]])[0] if results1.get("ids") else []) + (results2.get("ids", [[]])[0] if results2.get("ids") else [])
        combined_distances = (results1.get("distances", [[]])[0] if results1.get("distances") else []) + (results2.get("distances", [[]])[0] if results2.get("distances") else [])
        combined_docs = (results1.get("documents", [[]])[0] if results1.get("documents") else []) + (results2.get("documents", [[]])[0] if results2.get("documents") else [])
        combined_metas = (results1.get("metadatas", [[]])[0] if results1.get("metadatas") else []) + (results2.get("metadatas", [[]])[0] if results2.get("metadatas") else [])

        if not combined_ids:
            return {"ids": [[]], "distances": [[]], "documents": [[]], "metadatas": [[]]}

        # Sort by distance and limit to top_k
        combined = list(zip(combined_distances, combined_ids, combined_docs, combined_metas))
        combined.sort(key=lambda x: x[0])
        combined = combined[:top_k]

        return {
            "ids": [[x[1] for x in combined]],
            "distances": [[x[0] for x in combined]],
            "documents": [[x[2] for x in combined]],
            "metadatas": [[x[3] for x in combined]]
        }

    def delete_by_ids(self, chunk_ids: List[str]):
        """Delete specific chunks by their IDs from v2 collection only."""
        if not chunk_ids:
            return
        batch_size = 5000
        try:
            new_col = self.client.get_collection(name="3gpp_corpus_v2")
            for i in range(0, len(chunk_ids), batch_size):
                new_col.delete(ids=chunk_ids[i:i+batch_size])
            logger.info(f"Deleted {len(chunk_ids)} chunks from vector store (v2 collection).")
        except Exception as e:
            logger.warning(f"Failed to delete chunks from v2 collection: {e}")
