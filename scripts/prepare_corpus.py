"""
TeleRAG — Corpus Preparation Script

Downloads, inspects, extracts, and chunks the 3GPP corpus.
Must be run explicitly via `python -m scripts.prepare_corpus`.
"""
import json
import logging
import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import get_settings
from backend.app.ingestion.downloader import download_corpus
from backend.app.ingestion.archive_inspector import inspect_archive, extract_selected_file
from backend.app.ingestion.extractor import extract_document
from backend.app.ingestion.chunker import chunk_pages
from backend.app.ingestion.metadata import parse_version_from_filename
from backend.app.storage.metadata_store import MetadataStore
from backend.app.storage.vector_store import VectorStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def main():
    settings = get_settings()
    logger.info("Starting TeleRAG Corpus Preparation...")
    logger.info(f"Target Release: {settings.corpus_release}")
    logger.info(f"Corpus Tier: {settings.corpus_tier}")
    
    output_dir = settings.get_corpus_path()
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Download
    downloads = download_corpus(
        release=settings.corpus_release,
        tier=settings.corpus_tier,
        output_dir=output_dir
    )
    
    if not downloads:
        logger.error("No specifications downloaded or available. Aborting.")
        return
        
    manifest_path = settings.get_data_path() / "manifest.json"
    manifest = {"release": settings.corpus_release, "documents": []}
    if manifest_path.exists():
        with open(manifest_path, "r") as f:
            try:
                manifest = json.load(f)
            except json.JSONDecodeError:
                pass

    # 2. Extract & Inspect
    valid_documents = []
    for dl in downloads:
        zip_path = Path(dl["local_path"])
        spec_key = dl["specification"]
        
        inspection = inspect_archive(zip_path, spec_key.split(" ")[1])
        if not inspection["selected_file"]:
            logger.error(f"Could not identify spec document in {zip_path.name}: {inspection['reason']}")
            dl["status"] = "error"
            dl["error"] = inspection["reason"]
            continue
            
        extracted_path = extract_selected_file(
            zip_path=zip_path,
            selected_file=inspection["selected_file"],
            output_dir=zip_path.parent
        )
        
        if extracted_path:
            dl["extracted_path"] = str(extracted_path)
            dl["selected_format"] = inspection["selected_format"]
            dl["version"] = parse_version_from_filename(zip_path.name) or dl["version"]
            dl["status"] = "extracted"
            valid_documents.append(dl)
            
    # Save partial manifest
    manifest["documents"] = valid_documents
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    # 3. Process (Extract text & Chunk)
    # This prepares the data, we won't embed here yet unless vector_store is ready
    # For now, let's just make sure we can read and chunk them.
    
    # Initialize stores
    MetadataStore.initialize(settings.get_metadata_db_path())
    VectorStore.initialize(settings.get_vector_db_path(), settings.embedding_model)
    from backend.app.retrieval.bm25 import BM25Store
    BM25Store.initialize(settings.get_bm25_index_path())
    
    meta_store = MetadataStore.get_instance()
    vector_store = VectorStore.get_instance()
    bm25_store = BM25Store.get_instance()
    
    all_chunks = []
    
    for doc in valid_documents:
        if "extracted_path" not in doc:
            continue
            
        doc_path = Path(doc["extracted_path"])
        pages = extract_document(doc_path)
        doc["page_count"] = len(pages)
        
        chunks = chunk_pages(pages, settings.chunk_size, settings.chunk_overlap)
        doc["chunk_count"] = len(chunks)
        
        # Prepare for DB
        spec_chunks = []
        for i, c in enumerate(chunks):
            chunk_id = f"{doc['specification'].replace(' ', '_')}_{doc['version']}_{i}"
            spec_chunks.append({
                "id": chunk_id,
                "chunk_id": chunk_id,
                "text": c.text,
                "specification": doc["specification"],
                "version": doc["version"],
                "release": doc["release"],
                "section": c.section or "",
                "page": c.page,
                "chunk_index": i,
                "metadata": {
                    "specification": doc["specification"],
                    "version": doc["version"],
                    "release": doc["release"],
                    "section": c.section or "",
                    "page": c.page,
                }
            })
            
        all_chunks.extend(spec_chunks)
        
        # Save to metadata store
        doc["status"] = "indexed"
        meta_store.update_document_status(doc)
        meta_store.store_chunks(spec_chunks)
        
        # Add to vector store
        vector_store.add_chunks(spec_chunks)
        
        logger.info(f"Indexed {doc['specification']}: {len(pages)} pages -> {len(chunks)} chunks.")

    # Build BM25 index
    if all_chunks:
        bm25_store.build_index(all_chunks)

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
        
    logger.info("Corpus preparation completed successfully.")


if __name__ == "__main__":
    main()
