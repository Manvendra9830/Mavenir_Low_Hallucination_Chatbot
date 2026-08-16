"""
TeleRAG — Query Orchestrator Service

v0 simplified: Citation validation, claim verification, and abstention are
bypassed for this iteration. The verification modules remain in the codebase
for future use.
"""
import time
import logging
from typing import List, Dict

from backend.app.config import get_settings
from backend.app.models.schemas import (
    QueryRequest, QueryResponse, EvidenceChunk, 
    LatencyBreakdown, GroundingStatus
)
from backend.app.storage.metadata_store import MetadataStore
from backend.app.retrieval.filters import build_metadata_filter
from backend.app.retrieval.dense import dense_search
from backend.app.retrieval.bm25 import BM25Store
from backend.app.retrieval.fusion import reciprocal_rank_fusion
from backend.app.reranking.reranker import Reranker
from backend.app.generation.gateway import LLMGateway

logger = logging.getLogger(__name__)


class QueryService:
    def __init__(self):
        self.settings = get_settings()
        self.llm = LLMGateway()
        
    def process_query(self, request: QueryRequest) -> QueryResponse:
        logger.info(f"Processing query: {request.query}")
        start_total = time.time()
        latencies = LatencyBreakdown()
        
        # 1. Prepare Filter
        t0 = time.time()
        metadata_filter = build_metadata_filter(request.release, request.specifications)
        meta_store = MetadataStore.get_instance()
        valid_chunk_ids = meta_store.get_chunk_ids_for_scope(
            request.release,
            request.specifications,
        )
        latencies.query_processing_ms = (time.time() - t0) * 1000
        
        # 2. Dense Retrieval
        t0 = time.time()
        dense_results = dense_search(request.query, self.settings.vector_top_k, metadata_filter)
        latencies.dense_retrieval_ms = (time.time() - t0) * 1000
        
        # 3. BM25 Retrieval
        t0 = time.time()
        try:
            bm25 = BM25Store.get_instance()
            sparse_results = bm25.search(
                request.query,
                self.settings.bm25_top_k,
                valid_chunk_ids=valid_chunk_ids,
            )
        except Exception as e:
            logger.warning(f"BM25 search failed: {e}")
            sparse_results = []
        latencies.bm25_retrieval_ms = (time.time() - t0) * 1000
        
        # 4. RRF Fusion
        t0 = time.time()
        fused_results = reciprocal_rank_fusion(dense_results, sparse_results, k=self.settings.rrf_top_k)
        self._hydrate_fused_results(fused_results, meta_store)
        latencies.rrf_fusion_ms = (time.time() - t0) * 1000
        
        # 5. Reranking
        t0 = time.time()
        reranker = Reranker.get_instance()
        reranked = reranker.rerank(request.query, fused_results, self.settings.rerank_top_k)
        latencies.reranking_ms = (time.time() - t0) * 1000
        
        # Format Evidence Chunks
        evidence_chunks = []
        for c in reranked:
            meta = c.get("metadata", {})
            evidence_chunks.append(EvidenceChunk(
                chunk_id=c["chunk_id"],
                text=c.get("text", ""),
                specification=meta.get("specification", ""),
                version=meta.get("version", ""),
                release=meta.get("release", ""),
                section=meta.get("section", ""),
                page=meta.get("page", 0),
                dense_score=c.get("dense_score"),
                bm25_score=c.get("bm25_score"),
                rrf_score=c.get("rrf_score"),
                rerank_score=c.get("rerank_score")
            ))
            
        # 6. Evidence Checking (Bypassed gating for V1)
        t0 = time.time()
        # We can calculate the score for latency/debugging, but we do not gate or abstain on it.
        evidence_score = 1.0
        latencies.verification_ms = (time.time() - t0) * 1000
        
        # 7. LLM Generation
        t0 = time.time()
        # Cap chunks passed to LLM
        context_evidence = evidence_chunks[:self.settings.max_context_chunks]
        # Convert EvidenceChunk to dict for prompt builder
        context_dicts = [e.model_dump() for e in context_evidence]
        
        answer, llm_used = self.llm.generate(request.query, context_dicts)
        latencies.llm_generation_ms = (time.time() - t0) * 1000
        
        # 8. Verification Pipeline (Bypassed for V1)
        # Grounding status is simplified for V1 (no abstention based on citations or claims)
        grounding = GroundingStatus(
            evidence_found=len(evidence_chunks) > 0,
            citation_validated=False,
            claims_verified=False,
            evidence_score=evidence_score,
            verification_score=1.0,
            abstained=False,
            abstention_reason=None
        )
        
        latencies.total_ms = (time.time() - start_total) * 1000
        
        return QueryResponse(
            answer=answer,
            citations=[], # Citations not required for V1
            evidence=context_evidence,  # Return what was actually used
            grounding=grounding,
            latency=latencies,
            llm_used=llm_used,
            knowledge_scope=f"Release {request.release} - {len(request.specifications)} Specs"
        )

    def _hydrate_fused_results(self, candidates: List[Dict], meta_store: MetadataStore) -> None:
        """Populate text/metadata for BM25-only candidates before reranking."""
        missing_ids = [
            candidate["chunk_id"]
            for candidate in candidates
            if not candidate.get("text") or not candidate.get("metadata")
        ]
        chunks_by_id = meta_store.get_chunks_by_ids(missing_ids)

        for candidate in candidates:
            chunk = chunks_by_id.get(candidate["chunk_id"])
            if not chunk:
                continue

            candidate["text"] = candidate.get("text") or chunk.get("text", "")
            candidate["metadata"] = candidate.get("metadata") or {
                "specification": chunk.get("specification", ""),
                "version": chunk.get("version", ""),
                "release": chunk.get("release", ""),
                "section": chunk.get("section", ""),
                "page": chunk.get("page", 0),
            }
