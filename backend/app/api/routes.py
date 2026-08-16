"""
TeleRAG — API Routes
"""
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from pydantic import BaseModel
import shutil
import pathlib
import os

from backend.app.models.schemas import QueryRequest, QueryResponse, CorpusStatus, HealthResponse
from backend.app.services.query_service import QueryService
from backend.app.services.corpus_manager import CorpusManager
from backend.app.config import get_settings

router = APIRouter()

MAX_DOCUMENTS = 10


def get_query_service() -> QueryService:
    return QueryService()

def get_corpus_manager() -> CorpusManager:
    return CorpusManager()


# ── Query ───────────────────────────────────────────────────────────────────

@router.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest, service: QueryService = Depends(get_query_service)):
    """Process a RAG query against the 3GPP corpus."""
    try:
        return service.process_query(request)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ── Corpus Management ───────────────────────────────────────────────────────

class AddDocumentRequest(BaseModel):
    release: str
    specification: str

@router.post("/corpus/add")
async def add_document(request: AddDocumentRequest):
    """Dynamically download, process, and ingest a new 3GPP document."""
    from backend.app.storage.metadata_store import MetadataStore
    meta_store = MetadataStore.get_instance()
    
    # Enforce 10-document maximum
    current_count = meta_store.get_document_count()
    if current_count >= MAX_DOCUMENTS:
        raise HTTPException(
            status_code=400, 
            detail=f"Maximum corpus capacity of {MAX_DOCUMENTS} documents reached."
        )
    
    from backend.app.services.corpus_ingestion_service import CorpusIngestionService
    service = CorpusIngestionService()
    result = service.ingest_specification(request.release, request.specification)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result

@router.post("/corpus/upload")
async def upload_document(
    release: str = Form(...),
    specification: str = Form(...),
    file: UploadFile = File(...)
):
    """Upload and ingest a local document."""
    from backend.app.storage.metadata_store import MetadataStore
    meta_store = MetadataStore.get_instance()
    
    # Enforce 10-document maximum
    current_count = meta_store.get_document_count()
    if current_count >= MAX_DOCUMENTS:
        raise HTTPException(
            status_code=400, 
            detail=f"Maximum corpus capacity of {MAX_DOCUMENTS} documents reached."
        )
    
    # Save the uploaded file to a temporary location
    temp_dir = pathlib.Path(get_settings().get_data_path()) / "temp_uploads"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_file_path = temp_dir / file.filename
    
    try:
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        from backend.app.services.corpus_ingestion_service import CorpusIngestionService
        service = CorpusIngestionService()
        
        result = service.ingest_uploaded_file(
            local_path=str(temp_file_path),
            original_filename=file.filename,
            release=release,
            spec_number=specification
        )
        
        if result.get("status") == "error":
            raise HTTPException(status_code=400, detail=result.get("message"))
            
        return result
    finally:
        # Clean up temporary file
        if temp_file_path.exists():
            os.remove(temp_file_path)

@router.delete("/corpus/{specification}")
async def remove_document(specification: str):
    """Remove a specification from the indexed corpus."""
    from backend.app.storage.metadata_store import MetadataStore
    from backend.app.storage.vector_store import VectorStore
    from backend.app.retrieval.bm25 import BM25Store
    
    meta_store = MetadataStore.get_instance()
    
    # Get chunk IDs for this specification before deleting
    chunk_ids = meta_store.get_chunk_ids_for_spec(specification)
    if not chunk_ids:
        raise HTTPException(status_code=404, detail=f"Specification '{specification}' not found in corpus.")
    
    # 1. Remove from vector store
    try:
        vector_store = VectorStore.get_instance()
        vector_store.delete_by_ids(chunk_ids)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to remove vectors: {e}")
    
    # 2. Remove from BM25 index
    try:
        bm25_store = BM25Store.get_instance()
        bm25_store.remove_by_ids(chunk_ids)
    except Exception as e:
        # Log but don't fail — metadata cleanup is more important
        import logging
        logging.getLogger(__name__).warning(f"BM25 removal issue: {e}")
    
    # 3. Remove from metadata store
    meta_store.delete_document(specification)
    
    return {
        "status": "removed",
        "specification": specification,
        "chunks_removed": len(chunk_ids)
    }

@router.get("/corpus/available-specs")
async def get_available_specs():
    """Returns the base catalog of specifications."""
    from backend.app.ingestion.downloader import SPEC_CATALOG
    return list(SPEC_CATALOG.keys())

@router.get("/corpus/status", response_model=CorpusStatus)
async def get_corpus_status(manager: CorpusManager = Depends(get_corpus_manager)):
    """Get the indexing status of the 3GPP corpus."""
    return manager.get_status()


# ── Health ──────────────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse)
async def health(manager: CorpusManager = Depends(get_corpus_manager)):
    """System health check."""
    settings = get_settings()
    status = manager.get_status()
    
    llm_status = "ok" if settings.gemini_api_key else "missing_key"
    
    return HealthResponse(
        status="ok",
        index_ready=status.index_ready,
        llm_available=llm_status,
        corpus_release=status.release,
        corpus_specs=status.total_documents,
        corpus_chunks=status.total_chunks
    )
