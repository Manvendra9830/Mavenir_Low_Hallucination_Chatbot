"""
TeleRAG — Setup & Indexing Script
This script validates the raw 3GPP dataset, extracts the text, generates chunks, builds
the local SQLite metadata database, generates SentenceTransformer embeddings locally,
builds the ChromaDB vector index, and the BM25 sparse index.

Usage:
    python scripts/setup.py
    python scripts/setup.py --rebuild
"""
import sys
import os
import argparse
import shutil
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("setup")

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import get_settings
from backend.app.ingestion.archive_inspector import inspect_archive, extract_selected_file
from backend.app.ingestion.extractor import extract_document
from backend.app.ingestion.chunker import chunk_specification
from backend.app.storage.vector_store import VectorStore
from backend.app.retrieval.bm25 import BM25Store
from backend.app.storage.metadata_store import MetadataStore

REQUIRED_SPECS = [
    "TS 23.501",
    "TS 23.502",
    "TS 23.503",
    "TS 24.501",
    "TS 38.300",
    "TS 38.331"
]

def main():
    parser = argparse.ArgumentParser(description="TeleRAG Corpus Setup Script")
    parser.add_argument("--rebuild", action="store_true", help="Force rebuild of all indexes")
    args = parser.parse_args()

    print("=" * 60)
    print(" TeleRAG Corpus Setup ".center(60, "="))
    print("=" * 60)

    # 1. Environment Check
    if sys.version_info < (3, 9):
        logger.error("Python 3.9+ is required.")
        sys.exit(1)

    settings = get_settings()
    data_dir = PROJECT_ROOT / "data" / "3gpp" / "release_18"
    storage_dir = PROJECT_ROOT / "storage"

    # 2. Idempotency Check
    indexes_exist = (
        (storage_dir / "metadata" / "telerag.db").exists() and
        (storage_dir / "vector").exists() and
        (storage_dir / "bm25" / "bm25_index.pkl").exists()
    )

    if indexes_exist and not args.rebuild:
        print("\nIndexes already exist. Verifying current corpus...\n")
        MetadataStore.initialize(settings.get_metadata_db_path())
        VectorStore.initialize(settings.get_vector_db_path(), settings.embedding_model)
        BM25Store.initialize(settings.get_bm25_index_path())
        
        from backend.app.services.corpus_manager import CorpusManager
        manager = CorpusManager()
        status = manager.get_status().model_dump()
        print_status(status)
        print("\nStatus: READY (Indexes already exist. Use --rebuild to force regeneration.)")
        sys.exit(0)

    if args.rebuild and storage_dir.exists():
        logger.info(f"Removing existing storage directory: {storage_dir}")
        shutil.rmtree(storage_dir, ignore_errors=True)

    # Initialize empty stores
    storage_dir.mkdir(parents=True, exist_ok=True)
    MetadataStore.initialize(settings.get_metadata_db_path())
    VectorStore.initialize(settings.get_vector_db_path(), settings.embedding_model)
    BM25Store.initialize(settings.get_bm25_index_path())

    meta_store = MetadataStore.get_instance()
    vector_store = VectorStore.get_instance()
    bm25_store = BM25Store.get_instance()

    # 3. Dataset Validation
    if not data_dir.exists():
        logger.error(f"Dataset directory not found: {data_dir}")
        logger.error("Please download the 3GPP dataset and place it in data/3gpp/release_18/")
        sys.exit(1)

    logger.info("Discovering specification ZIP files...")
    spec_files = {}
    
    # We expect data/3gpp/release_18/TS_23.501/23501-i00.zip format
    for spec in REQUIRED_SPECS:
        spec_folder = spec.replace(" ", "_")
        target_dir = data_dir / spec_folder
        if not target_dir.exists():
            logger.error(f"Missing specification directory: {target_dir}")
            sys.exit(1)
            
        zips = list(target_dir.glob("*.zip"))
        if not zips:
            logger.error(f"No ZIP file found in {target_dir}")
            sys.exit(1)
        
        # Take the first zip file
        spec_files[spec] = zips[0]
        logger.info(f"Found {spec} -> {spec_files[spec].name}")

    # 4. Extraction & Indexing Pipeline
    print("\nStarting Ingestion Pipeline...")
    total_pages = 0
    total_chunks = 0
    
    for spec, zip_path in spec_files.items():
        logger.info("-" * 40)
        logger.info(f"Processing {spec} from {zip_path.name}")
        
        # Inspect
        inspection = inspect_archive(zip_path, spec.replace("TS ", ""))
        if not inspection.get("selected_file"):
            logger.error(f"No viable document found in {zip_path.name}: {inspection.get('reason')}")
            sys.exit(1)
            
        # Extract file from ZIP
        temp_pdf_path = extract_selected_file(zip_path, inspection["selected_file"], data_dir / spec.replace(" ", "_"))
        if not temp_pdf_path:
            logger.error(f"Failed to extract document from {zip_path.name}")
            sys.exit(1)
            
        # Extract text
        logger.info(f"Extracting text from {temp_pdf_path.name}")
        pages = extract_document(temp_pdf_path)
        if not pages:
            logger.error(f"Failed to extract text from {temp_pdf_path.name}")
            sys.exit(1)
            
        # Chunk
        logger.info(f"Chunking {len(pages)} pages")
        chunks = chunk_specification(
            pages=pages,
            specification=spec,
            version="18.0.0", # Simplified for offline setup
            release="18",
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap
        )
        if not chunks:
            logger.error(f"Failed to generate chunks for {spec}")
            sys.exit(1)
            
        # Insert to DBs
        logger.info(f"Adding {len(chunks)} chunks to Vector Store (this generates embeddings locally...)")
        vector_store.add_chunks(chunks)
        
        logger.info("Adding chunks to BM25 Store")
        bm25_store.add_chunks(chunks)
        
        logger.info("Updating Metadata Store")
        meta_store.store_chunks([c.model_dump() for c in chunks])
        
        meta_store.update_document_status({
            "specification": spec,
            "version": "18.0.0",
            "release": "18",
            "source_filename": zip_path.name,
            "status": "indexed",
            "page_count": len(pages),
            "chunk_count": len(chunks)
        })
        
        total_pages += len(pages)
        total_chunks += len(chunks)

    # 5. Finalize
    print("\n" + "=" * 60)
    print(" TeleRAG Corpus Build Summary ".center(60, "="))
    print("=" * 60)
    print("Release: 18")
    print("\nSpecifications:")
    
    from backend.app.services.corpus_manager import CorpusManager
    manager = CorpusManager()
    status = manager.get_status().model_dump()
    
    for spec in REQUIRED_SPECS:
        found = any(s["specification"] == spec for s in status.get("specifications", []))
        if found:
            print(f"  [OK] {spec}")
        else:
            print(f"  [MISSING] {spec}")
            
    print(f"\nDocuments: {status.get('total_documents', 0)}")
    print(f"Chunks: {status.get('total_chunks', 0)}")
    
    print(f"\nEmbedding model:\n  {settings.embedding_model}")
    print("\nVector index:\n  ChromaDB")
    print("Sparse index:\n  BM25")
    print("\nStatus:\n  READY")
    print("=" * 60)
    
def print_status(status):
    for spec in status.get("specifications", []):
        print(f"  [OK] {spec['specification']} ({spec['chunk_count']} chunks)")
    print(f"\nDocuments: {status.get('total_documents', 0)}")
    print(f"Chunks: {status.get('total_chunks', 0)}")
    
if __name__ == "__main__":
    main()
