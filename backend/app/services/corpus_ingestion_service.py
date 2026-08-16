"""
TeleRAG — Corpus Ingestion Service
Orchestrates adding new 3GPP specifications to the existing corpus dynamically.
"""
import logging
from typing import Dict, Any, Optional

from backend.app.config import get_settings
from backend.app.ingestion.downloader import download_spec, get_archive_filename
from backend.app.ingestion.archive_inspector import inspect_archive, extract_selected_file
from backend.app.ingestion.extractor import extract_document
from backend.app.ingestion.chunker import chunk_specification
from backend.app.storage.vector_store import VectorStore
from backend.app.retrieval.bm25 import BM25Store
from backend.app.storage.metadata_store import MetadataStore

logger = logging.getLogger(__name__)


class CorpusIngestionService:
    def __init__(self):
        self.settings = get_settings()
        self.vector_store = VectorStore.get_instance()
        self.bm25_store = BM25Store.get_instance()
        self.meta_store = MetadataStore.get_instance()

    def ingest_specification(self, release: str, spec_number: str) -> Dict[str, Any]:
        """
        Orchestrate the end-to-end ingestion of a single 3GPP specification.
        """
        output_dir = self.settings.get_data_path() / "3gpp" / f"release_{release}"
        
        # 1. Download
        logger.info(f"Downloading spec {spec_number} (Release {release})")
        download_meta = download_spec(spec_number, release, output_dir)
        if not download_meta:
            return {"status": "error", "message": f"Failed to download {spec_number}. Ensure it is a valid 3GPP spec."}
            
        local_path = download_meta["local_path"]
        
        # Update metadata to 'processing'
        self.meta_store.update_document_status({
            "specification": spec_number,
            "version": download_meta["version"],
            "release": release,
            "source_filename": download_meta["source_filename"],
            "sha256": download_meta["sha256"],
            "status": "processing"
        })

        try:
            import pathlib
            local_path = pathlib.Path(local_path)
            # 2. Inspect Archive
            logger.info(f"Inspecting archive: {local_path}")
            inspection = inspect_archive(local_path, spec_number)
            if not inspection.get("selected_file"):
                raise ValueError(f"No viable document found in archive: {inspection.get('reason')}")
                
            pdf_path = extract_selected_file(local_path, inspection["selected_file"], output_dir / spec_number.replace(" ", "_"))
            if not pdf_path:
                raise ValueError("Failed to extract document from archive.")

            # 3. Extract Text
            logger.info(f"Extracting text from: {pdf_path}")
            pages = extract_document(pdf_path)
            if not pages:
                raise ValueError("Failed to extract text from document.")

            # 4. Chunking
            logger.info(f"Chunking {len(pages)} pages")
            chunks = chunk_specification(
                pages=pages,
                specification=spec_number,
                version=download_meta["version"],
                release=release,
                chunk_size=self.settings.chunk_size,
                chunk_overlap=self.settings.chunk_overlap
            )
            
            if not chunks:
                raise ValueError("Failed to generate chunks.")

            # 5. Embed & Index (Vector + BM25)
            logger.info(f"Adding {len(chunks)} chunks to Vector Store")
            self.vector_store.add_chunks(chunks)
            
            logger.info(f"Adding {len(chunks)} chunks to BM25 Store")
            self.bm25_store.add_chunks(chunks)
            
            # 6. Store metadata
            logger.info("Updating metadata store")
            self.meta_store.store_chunks([c.model_dump() for c in chunks])
            
            # 7. Final status
            self.meta_store.update_document_status({
                "specification": spec_number,
                "version": download_meta["version"],
                "release": release,
                "source_filename": download_meta["source_filename"],
                "sha256": download_meta["sha256"],
                "status": "ingested",
                "page_count": len(pages),
                "chunk_count": len(chunks)
            })

            return {
                "status": "success",
                "specification": spec_number,
                "release": release,
                "chunks_added": len(chunks),
                "pages_processed": len(pages)
            }
            
        except Exception as e:
            logger.error(f"Ingestion failed for {spec_number}: {e}")
            self.meta_store.update_document_status({
                "specification": spec_number,
                "version": download_meta["version"],
                "release": release,
                "status": f"failed: {str(e)}"
            })
            return {"status": "error", "message": str(e)}
