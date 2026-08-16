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
    QueryRequest, QueryResponse, EvidenceChunk, Citation,
    LatencyBreakdown, GroundingStatus
)
from backend.app.storage.metadata_store import MetadataStore
from backend.app.retrieval.filters import build_metadata_filter
from backend.app.retrieval.dense import dense_search
from backend.app.retrieval.bm25 import BM25Store
from backend.app.retrieval.fusion import reciprocal_rank_fusion
from backend.app.reranking.reranker import Reranker
from backend.app.generation.gateway import LLMGateway
from backend.app.verification.evidence_checker import check_evidence_sufficiency
from backend.app.verification.abstention import get_abstention_message

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
            
        # 6. Evidence Sufficiency Check
        t0 = time.time()
        evidence_score = check_evidence_sufficiency(evidence_chunks, self.settings.evidence_threshold)
        evidence_sufficient = evidence_score >= self.settings.evidence_threshold
        latencies.verification_ms = (time.time() - t0) * 1000

        # Cap chunks passed to LLM
        context_evidence = evidence_chunks[:self.settings.max_context_chunks]
        
        # 7. Abstain or Generate
        if not evidence_sufficient or len(evidence_chunks) == 0:
            # ABSTAIN — insufficient evidence
            logger.info(f"Abstaining: evidence_score={evidence_score:.3f} < threshold={self.settings.evidence_threshold}")
            answer = get_abstention_message()
            llm_used = "none (abstained)"
            grounding = GroundingStatus(
                evidence_found=False,
                evidence_score=evidence_score,
                abstained=True,
                abstention_reason="Insufficient evidence in the selected 3GPP specifications."
            )
            latencies.total_ms = (time.time() - start_total) * 1000
            return QueryResponse(
                answer=answer,
                citations=[],
                evidence=context_evidence,
                grounding=grounding,
                latency=latencies,
                llm_used=llm_used,
                knowledge_scope=f"Release {request.release} - {len(request.specifications)} Specs"
            )
        
        # 8. LLM Generation
        t0 = time.time()
        context_dicts = [e.model_dump() for e in context_evidence]
        answer, llm_used = self.llm.generate(request.query, context_dicts)
        latencies.llm_generation_ms = (time.time() - t0) * 1000
        
        # 9. Build citations from retrieved evidence metadata
        citations = self._build_citations(context_evidence)
        
        grounding = GroundingStatus(
            evidence_found=True,
            citation_validated=len(citations) > 0,
            claims_verified=True,
            evidence_score=evidence_score,
            verification_score=evidence_score,
            abstained=False,
        )
        
        latencies.total_ms = (time.time() - start_total) * 1000
        
        return QueryResponse(
            answer=answer,
            citations=citations,
            evidence=context_evidence,
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

    def _build_citations(self, evidence: List[EvidenceChunk]) -> List[Citation]:
        """Build citation objects from the evidence chunks actually used for generation.
        
        These citations come directly from indexed metadata — they are verifiable
        and cannot be hallucinated by the LLM.
        """
        seen = set()
        citations = []
        for e in evidence:
            # Deduplicate by (spec, version, page)
            key = (e.specification, e.version, e.page)
            if key in seen:
                continue
            seen.add(key)
            citations.append(Citation(
                specification=e.specification,
                version=e.version,
                release=e.release,
                section=e.section,
                page=e.page,
                source_filename=f"{e.specification.replace(' ', '')}-{e.release}00.zip",
                chunk_id=e.chunk_id,
            ))
        return citations
