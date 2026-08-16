"""
TeleRAG — Pydantic models for API requests and responses.
"""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


# ── Request Models ──────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    """User query to the RAG pipeline."""
    query: str = Field(..., min_length=1, max_length=2000)
    release: str = Field(default="18")
    specifications: list[str] = Field(default_factory=lambda: [
        "TS 23.501", "TS 23.502", "TS 23.503",
        "TS 24.501", "TS 38.300", "TS 38.331",
    ])
    conversation_id: Optional[str] = None


# ── Evidence / Citation Models ──────────────────────────────────────────────

class Citation(BaseModel):
    """A verified citation pointing to a specific 3GPP source."""
    specification: str
    version: str
    release: str
    section: Optional[str] = None
    page: Optional[int] = None
    source_filename: str
    chunk_id: str


class EvidenceChunk(BaseModel):
    """A single retrieved evidence chunk with scores."""
    chunk_id: str
    text: str
    specification: str
    version: str
    release: str
    section: Optional[str] = None
    page: Optional[int] = None
    dense_score: Optional[float] = None
    bm25_score: Optional[float] = None
    rrf_score: Optional[float] = None
    rerank_score: Optional[float] = None


# ── Grounding Status ────────────────────────────────────────────────────────

class GroundingStatus(BaseModel):
    """Grounding and verification status for an answer."""
    evidence_found: bool = False
    citation_validated: bool = False
    claims_verified: bool = False
    evidence_score: Optional[float] = None
    verification_score: Optional[float] = None
    abstained: bool = False
    abstention_reason: Optional[str] = None


# ── Latency ─────────────────────────────────────────────────────────────────

class LatencyBreakdown(BaseModel):
    """Latency measurements for pipeline stages (in ms)."""
    query_processing_ms: Optional[float] = None
    embedding_ms: Optional[float] = None
    dense_retrieval_ms: Optional[float] = None
    bm25_retrieval_ms: Optional[float] = None
    rrf_fusion_ms: Optional[float] = None
    reranking_ms: Optional[float] = None
    llm_generation_ms: Optional[float] = None
    verification_ms: Optional[float] = None
    total_ms: Optional[float] = None


# ── Response Models ─────────────────────────────────────────────────────────

class QueryResponse(BaseModel):
    """Full response to a user query."""
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    evidence: list[EvidenceChunk] = Field(default_factory=list)
    grounding: GroundingStatus = Field(default_factory=GroundingStatus)
    latency: Optional[LatencyBreakdown] = None
    llm_used: Optional[str] = None
    query_type: Optional[str] = None
    knowledge_scope: Optional[str] = None


# ── Corpus Models ───────────────────────────────────────────────────────────

class SpecificationInfo(BaseModel):
    """Information about a single specification."""
    specification: str
    title: str
    version: str
    release: str
    status: str  # "indexed" | "pending" | "error"
    chunk_count: int = 0
    page_count: int = 0
    source_filename: str = ""


class CorpusStatus(BaseModel):
    """Overall corpus status."""
    release: str
    tier: str
    specifications: list[SpecificationInfo] = Field(default_factory=list)
    total_documents: int = 0
    total_chunks: int = 0
    total_pages: int = 0
    last_indexed: Optional[str] = None
    index_ready: bool = False


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "ok"
    version: str = "0.1.0"
    index_ready: bool = False
    llm_available: str = "unknown"
    corpus_release: str = ""
    corpus_specs: int = 0
    corpus_chunks: int = 0
