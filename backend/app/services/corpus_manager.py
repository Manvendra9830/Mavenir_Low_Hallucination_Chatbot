"""
TeleRAG — Corpus Manager Service
"""
import logging
from backend.app.config import get_settings
from backend.app.storage.metadata_store import MetadataStore
from backend.app.models.schemas import CorpusStatus, SpecificationInfo

logger = logging.getLogger(__name__)


class CorpusManager:
    def __init__(self):
        self.settings = get_settings()
        self.meta_store = MetadataStore.get_instance()
        
    def get_status(self) -> CorpusStatus:
        stats = self.meta_store.get_document_stats()
        
        specs = []
        total_docs = len(stats)
        total_chunks = 0
        total_pages = 0
        
        for s in stats:
            specs.append(SpecificationInfo(
                specification=s["specification"],
                title="",  # Could lookup from catalog if needed
                version=s["version"],
                release=s["release"],
                status=s["status"],
                chunk_count=s.get("chunk_count", 0) or 0,
                page_count=s.get("page_count", 0) or 0,
                source_filename=s.get("source_filename", "")
            ))
            total_chunks += s.get("chunk_count", 0) or 0
            total_pages += s.get("page_count", 0) or 0
            
        return CorpusStatus(
            release=self.settings.corpus_release,
            tier=self.settings.corpus_tier,
            specifications=specs,
            total_documents=total_docs,
            total_chunks=total_chunks,
            total_pages=total_pages,
            index_ready=total_docs > 0 and total_chunks > 0
        )
