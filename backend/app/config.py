"""
TeleRAG Configuration — Loads all settings from environment variables.
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field

# Project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """All configurable settings for TeleRAG, loaded from .env"""

    # --- LLM: Primary (Google Gemini) ---
    gemini_api_key: str = Field(default="", description="Google Gemini API key")
    gemini_model: str = Field(default="gemini-3.5-flash", description="Gemini model name")

    # --- LLM: Fallback (Groq) ---
    groq_api_key: str = Field(default="", description="Groq API key")
    groq_model: str = Field(default="llama-3.3-70b-versatile", description="Groq model name")

    # --- Embedding ---
    embedding_model: str = Field(default="all-MiniLM-L6-v2", description="Sentence-transformers model")

    # --- Chunking ---
    chunk_size: int = Field(default=1024, description="Target chunk size in characters")
    chunk_overlap: int = Field(default=128, description="Overlap between adjacent chunks")

    # --- Retrieval ---
    vector_top_k: int = Field(default=20, description="Dense retrieval top-K")
    bm25_top_k: int = Field(default=20, description="BM25 sparse retrieval top-K")
    rrf_top_k: int = Field(default=30, description="RRF fusion top-K")
    rerank_top_k: int = Field(default=8, description="Cross-encoder reranker top-K output")

    # --- Grounding & Verification ---
    retrieval_score_threshold: float = Field(default=0.25, description="Min score to consider a retrieval hit relevant")
    evidence_threshold: float = Field(default=0.4, description="Min aggregated evidence score to proceed with generation")
    verification_threshold: float = Field(default=0.5, description="Min claim verification score")
    max_context_chunks: int = Field(default=6, description="Max chunks passed to LLM context")

    # --- Generation ---
    temperature: float = Field(default=0.1, description="LLM sampling temperature")
    max_output_tokens: int = Field(default=1024, description="Max LLM output tokens")

    # --- Storage (relative to PROJECT_ROOT) ---
    vector_db_path: str = Field(default="storage/vector", description="ChromaDB persistent path")
    bm25_index_path: str = Field(default="storage/bm25", description="BM25 index pickle path")
    metadata_db_path: str = Field(default="storage/metadata/telerag.db", description="SQLite metadata DB")

    # --- Corpus ---
    corpus_release: str = Field(default="18", description="Target 3GPP release")
    auto_download_corpus: bool = Field(default=True, description="Auto-download specs on startup")
    corpus_tier: str = Field(default="FULL", description="FULL / CORE / MINIMAL")

    # --- Debug ---
    debug_mode: bool = Field(default=False, description="Enable debug logging and latency display")

    # --- Server ---
    backend_host: str = Field(default="0.0.0.0")
    backend_port: int = Field(default=8000)
    frontend_url: str = Field(default="http://localhost:5173")

    model_config = {
        "env_file": str(PROJECT_ROOT / ".env"),
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }

    # --- Derived paths (resolved from PROJECT_ROOT) ---
    def get_vector_db_path(self) -> Path:
        return PROJECT_ROOT / self.vector_db_path

    def get_bm25_index_path(self) -> Path:
        path = PROJECT_ROOT / self.bm25_index_path
        if not str(path).endswith('.pkl'):
            path = path / "bm25_index.pkl"
        return path

    def get_metadata_db_path(self) -> Path:
        return PROJECT_ROOT / self.metadata_db_path

    def get_data_path(self) -> Path:
        return PROJECT_ROOT / "data"

    def get_corpus_path(self) -> Path:
        return PROJECT_ROOT / "data" / "3gpp" / f"release_{self.corpus_release}"


# Singleton
_settings = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
