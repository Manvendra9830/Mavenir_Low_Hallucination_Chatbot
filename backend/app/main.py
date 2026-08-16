"""
TeleRAG — Main FastAPI Application
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.config import get_settings
from backend.app.api.routes import router as api_router
from backend.app.storage.metadata_store import MetadataStore
from backend.app.storage.vector_store import VectorStore
from backend.app.retrieval.bm25 import BM25Store
from backend.app.reranking.reranker import Reranker

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events for the FastAPI app."""
    settings = get_settings()
    logger.info("Starting TeleRAG Backend...")
    
    # Initialize storage singletons
    logger.info("Initializing stores and models...")
    MetadataStore.initialize(settings.get_metadata_db_path())
    VectorStore.initialize(settings.get_vector_db_path(), settings.embedding_model)
    BM25Store.initialize(settings.get_bm25_index_path())
    Reranker.initialize()
    
    logger.info("All stores and models initialized.")

    yield
    
    logger.info("Shutting down TeleRAG Backend...")


app = FastAPI(
    title="TeleRAG — Mavenir 3GPP Standards Intelligence Assistant",
    version="0.1.0",
    description="Evidence-grounded RAG chatbot for 3GPP standards.",
    lifespan=lifespan
)

settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host=settings.backend_host, port=settings.backend_port, reload=True)
