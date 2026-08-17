"""
TeleRAG — Metadata Store (SQLite)
"""
import json
import logging
import sqlite3
from pathlib import Path
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)


class MetadataStore:
    """Singleton wrapper for SQLite DB to track ingestion and chunk metadata."""
    _instance = None

    @classmethod
    def initialize(cls, db_path: Path):
        if cls._instance is None:
            cls._instance = cls(db_path)

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            raise RuntimeError("MetadataStore not initialized. Call initialize() first.")
        return cls._instance

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        logger.info(f"MetadataStore initialized at {self.db_path}")

    def _get_conn(self):
        # Return a fresh connection since sqlite objects created in a thread can only be used in that same thread
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS documents (
                specification TEXT,
                version TEXT,
                release TEXT,
                source_filename TEXT,
                sha256 TEXT,
                status TEXT,
                page_count INTEGER,
                chunk_count INTEGER,
                ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (specification, release, version)
            );

            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id TEXT PRIMARY KEY,
                specification TEXT,
                version TEXT,
                release TEXT,
                section TEXT,
                page INTEGER,
                text TEXT,
                chunk_index INTEGER
            );
            """)

    def update_document_status(self, spec_data: dict):
        """Update or insert document ingestion status."""
        with self._get_conn() as conn:
            conn.execute("""
            INSERT OR REPLACE INTO documents
            (specification, version, release, source_filename, sha256, status, page_count, chunk_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                spec_data["specification"],
                spec_data["version"],
                spec_data["release"],
                spec_data.get("source_filename", ""),
                spec_data.get("sha256", ""),
                spec_data.get("status", "pending"),
                spec_data.get("page_count", 0),
                spec_data.get("chunk_count", 0)
            ))

    def store_chunks(self, chunks: List[dict]):
        """Store chunk metadata and text (useful for BM25 or verification fallback).
        chunks format: {'chunk_id': ..., 'specification': ..., 'version': ..., 'release': ..., 'section': ..., 'page': ..., 'text': ..., 'chunk_index': ...}
        """
        if not chunks:
            return

        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.executemany("""
            INSERT OR IGNORE INTO chunks
            (chunk_id, specification, version, release, section, page, text, chunk_index)
            VALUES (:chunk_id, :specification, :version, :release, :section, :page, :text, :chunk_index)
            """, chunks)

    def get_document_stats(self) -> List[Dict]:
        """Get stats for all ingested documents."""
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT * FROM documents ORDER BY specification")
            return [dict(row) for row in cursor.fetchall()]

    def get_chunk(self, chunk_id: str) -> Optional[Dict]:
        """Retrieve a chunk by ID."""
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT * FROM chunks WHERE chunk_id = ?", (chunk_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_chunks_by_ids(self, chunk_ids: List[str]) -> Dict[str, Dict]:
        """Retrieve chunks by ID, preserving efficient batched lookup."""
        if not chunk_ids:
            return {}

        placeholders = ",".join("?" for _ in chunk_ids)
        with self._get_conn() as conn:
            cursor = conn.execute(
                f"SELECT * FROM chunks WHERE chunk_id IN ({placeholders})",
                chunk_ids,
            )
            return {row["chunk_id"]: dict(row) for row in cursor.fetchall()}

    def get_chunk_ids_for_scope(self, release: str, specifications: List[str]) -> List[str]:
        """Get chunk IDs matching the active release/specification query scope."""
        with self._get_conn() as conn:
            if specifications:
                placeholders = ",".join("?" for _ in specifications)
                cursor = conn.execute(
                    f"""
                    SELECT chunk_id FROM chunks
                    WHERE release = ? AND specification IN ({placeholders})
                    """,
                    [str(release), *specifications],
                )
            else:
                cursor = conn.execute(
                    "SELECT chunk_id FROM chunks WHERE release = ?",
                    (str(release),),
                )
            return [row["chunk_id"] for row in cursor.fetchall()]

    def get_chunk_ids_for_spec(self, specification: str) -> List[str]:
        """Get all chunk IDs belonging to a specification."""
        with self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT chunk_id FROM chunks WHERE specification = ?",
                (specification,)
            )
            return [row["chunk_id"] for row in cursor.fetchall()]

    def delete_document(self, specification: str) -> int:
        """Delete a document and all its chunks from the metadata store.
        Returns the number of chunks deleted."""
        chunk_ids = self.get_chunk_ids_for_spec(specification)
        with self._get_conn() as conn:
            conn.execute("DELETE FROM chunks WHERE specification = ?", (specification,))
            conn.execute("DELETE FROM documents WHERE specification = ?", (specification,))
        logger.info(f"Deleted document {specification} and {len(chunk_ids)} chunks from metadata store")
        return len(chunk_ids)

    def get_document_count(self) -> int:
        """Get the total number of successfully indexed documents."""
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT COUNT(*) as cnt FROM documents WHERE status = 'indexed'")
            row = cursor.fetchone()
            return row["cnt"] if row else 0

    def delete_failed_documents(self) -> int:
        """Remove documents with a non-indexed status (failed/processing).
        Safe to call — only removes metadata rows, never touches chunks."""
        with self._get_conn() as conn:
            cursor = conn.execute(
                "DELETE FROM documents WHERE status != 'indexed'"
            )
            deleted = cursor.rowcount
        if deleted:
            logger.info(f"Cleaned up {deleted} failed/processing document record(s) from metadata.")
        return deleted
