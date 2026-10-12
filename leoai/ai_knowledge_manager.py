# leoai/knowledge_manager.py
"""
Knowledge management for LEO CDP Assistant RAG.

Features:
- Pydantic models for KnowledgeSource and KnowledgeChunk (mirrors SQL schema)
- Async KnowledgeManager with CRUD for sources and chunks
- Batch chunk insertion (efficient)
- Vector similarity search using pgvector (ORDER BY embedding <-> $1)
- Simple text chunker utility
- EmbeddingProvider protocol (abstracts actual embedding implementation)
- Defensive logging and clear error handling

Assumptions:
- A function `get_async_pg_conn()` exists and returns an asyncpg-compatible connection
  that supports `async with get_async_pg_conn() as conn:` and `await conn.fetch(...)`.
- Postgres has pgvector extension installed and `knowledge_chunks.embedding` is of type VECTOR(768).
- You may need to adapt some SQL parameter binding based on your async driver.
"""

from __future__ import annotations

import asyncio
import json
import logging

from typing import Any, Dict, Iterable, List, Optional, Protocol, Tuple, Union
from uuid import UUID
from uuid6 import uuid7
from datetime import datetime, timezone


# Import your project's DB connection helper
from leoai.ai_core import GeminiClient
from leoai.ai_knowledge_models import DEFAULT_MAX_TOKENS, DEFAULT_OVERLAP_TOKENS, KnowledgeChunk, KnowledgeSource, KnowledgeSourceType, ProcessingStatus, tokenized_chunk_text
from leoai.db_utils import DEFAULT_EMBED_DIM, get_async_pg_conn, parse_embedding, parse_metadata, to_pgvector

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

# ---------------------------------------------------------------------
# Constants & Limits
# ---------------------------------------------------------------------
MAX_DOC_TEXT_LENGTH = 100_000
BATCH_INSERT_SIZE = 256  # number of chunks to insert in one transaction

# ---------------------------------------------------------------------
# Embedding Provider Protocol (abstract)
# ---------------------------------------------------------------------


class EmbeddingProvider(Protocol):
    """
    Minimal interface for an embedding provider.
    Implement this protocol with your actual embedding client (OpenAI, Cohere, local, etc.)
    """

    async def embed_texts(self, texts: Iterable[str]) -> List[List[float]]:
        ...


def _ensure_embedding_shape(embedding: List[float], dim: int = DEFAULT_EMBED_DIM) -> None:
    if not isinstance(embedding, list):
        raise ValueError("embedding must be a list of floats")
    if len(embedding) != dim:
        raise ValueError(
            f"embedding must be of length {dim}; got {len(embedding)}")


# ---------------------------------------------------------------------
# KnowledgeManager
# ---------------------------------------------------------------------
class KnowledgeManager:
    """
    Async manager for knowledge sources and chunks.
    Works with Postgres + pgvector assumed for similarity search.
    """

    def __init__(self, embedding_dim: int = DEFAULT_EMBED_DIM, batch_size: int = BATCH_INSERT_SIZE):
        self.embedding_dim = embedding_dim
        self.batch_size = batch_size

    # ---------------------------
    # Sources CRUD
    # ---------------------------
    async def create_source(self, source: KnowledgeSource) -> KnowledgeSource:
        """
        Insert a new knowledge source into DB and return the saved object with timestamps.
        """
        sql = """
        INSERT INTO knowledge_sources
            (id, user_id, tenant_id, source_type, name, code_name, uri, status, metadata, created_at, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW(), NOW())
        RETURNING id, created_at, updated_at;
        """
        try:
            # Ensure enums are passed as strings
            source_type = getattr(source.source_type, "value", source.source_type)
            status_value = getattr(source.status, "value", source.status)
            #
            async with get_async_pg_conn() as conn:
                row = await conn.fetchrow(
                    sql,
                    str(source.id),
                    source.user_id,
                    source.tenant_id,
                    source_type,
                    source.name,
                    source.code_name or "",
                    source.uri,
                    status_value,
                    json.dumps(source.metadata) if source.metadata else None,
                )
                if not row:
                    raise RuntimeError("Failed to create knowledge source.")
                source.id = str(row["id"])
                source.created_at = row["created_at"]
                source.updated_at = row["updated_at"]
                logger.info("Created knowledge source %s", source.id)
                return source
        except Exception as exc:
            logger.exception("Error creating knowledge source: %s", exc)
            raise

    async def get_source(
        self, source_id: Union[UUID, str], *, tenant_id: str
    ) -> Optional[KnowledgeSource]:
        sql = """
        SELECT id, user_id, tenant_id, source_type, name, code_name, uri, status, metadata, created_at, updated_at
        FROM knowledge_sources
        WHERE id = $1 AND tenant_id = $2;
        """
        try:
            async with get_async_pg_conn() as conn:
                row = await conn.fetchrow(sql, str(source_id), tenant_id)
                if not row:
                    return None
                src = KnowledgeSource(
                    id=UUID(row["id"]),
                    user_id=row["user_id"],
                    tenant_id=row["tenant_id"],
                    source_type=KnowledgeSourceType(row["source_type"]),
                    name=row["name"],
                    code_name=row.get("code_name"),
                    uri=row.get("uri"),
                    status=ProcessingStatus(row["status"]),
                    metadata=row.get("metadata"),
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
                return src
        except Exception as exc:
            logger.exception(
                "Error fetching knowledge source %s: %s", source_id, exc)
            raise

    async def list_sources(
        self,
        user_id: str,
        tenant_id: str,
        source_type: Optional[KnowledgeSourceType] = None,
        status: Optional[ProcessingStatus] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[KnowledgeSource]:
        base = """
        SELECT id, user_id, tenant_id, source_type, name, code_name, uri, status, metadata, created_at, updated_at
        FROM knowledge_sources
        WHERE user_id = $1 AND tenant_id = $2
        """
        params: List[Any] = [user_id, tenant_id]
        idx = 3
        if source_type:
            base += f" AND source_type = ${idx}"
            params.append(source_type.value)
            idx += 1
        if status:
            base += f" AND status = ${idx}"
            params.append(status.value)
            idx += 1
        base += f" ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx + 1};"
        params.extend([limit, offset])

        try:
            async with get_async_pg_conn() as conn:
                rows = await conn.fetch(base, *params)
                result = []
                for row in rows:
                    result.append(KnowledgeSource(
                        id=UUID(row["id"]),
                        user_id=row["user_id"],
                        tenant_id=row["tenant_id"],
                        source_type=KnowledgeSourceType(row["source_type"]),
                        name=row["name"],
                        code_name=row.get("code_name"),
                        uri=row.get("uri"),
                        status=ProcessingStatus(row["status"]),
                        metadata=row.get("metadata"),
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                    ))
                return result
        except Exception as exc:
            logger.exception("Error listing knowledge sources: %s", exc)
            raise

    async def update_source_status(
        self, source_id: Union[UUID, str], status: ProcessingStatus, *,
        tenant_id: str,
    ) -> bool:
        sql = """
        UPDATE knowledge_sources
        SET status = $1, updated_at = NOW()
        WHERE id = $2 AND tenant_id = $3
        RETURNING id;
        """
        try:
            async with get_async_pg_conn() as conn:
                row = await conn.fetchrow(
                    sql, status.value, str(source_id), tenant_id
                )
                return bool(row)
        except Exception as exc:
            logger.exception(
                "Error updating status for source %s: %s", source_id, exc)
            raise

    async def delete_source(
        self, source_id: Union[UUID, str], *, tenant_id: str
    ) -> bool:
        """
        Delete a source (cascades to chunks via ON DELETE CASCADE).
        """
        sql = """
        DELETE FROM knowledge_sources
        WHERE id = $1 AND tenant_id = $2
        RETURNING id;
        """
        try:
            async with get_async_pg_conn() as conn:
                row = await conn.fetchrow(sql, str(source_id), tenant_id)
                return bool(row)
        except Exception as exc:
            logger.exception("Error deleting source %s: %s", source_id, exc)
            raise

    # ---------------------------
    # Chunks operations
    # ---------------------------
    async def add_chunks(
        self,
        chunks: Iterable[KnowledgeChunk],
        batch_size: Optional[int] = None
    ) -> int:
        """
        Insert chunks in batches. Returns number of chunks inserted.
        Uses pgvector for the embedding column. Assumes `knowledge_chunks.embedding` is of type VECTOR.
        """
        batch_size = batch_size or self.batch_size
        chunks = list(chunks)
        if not chunks:
            return 0

        # validate embeddings
        for c in chunks:
            _ensure_embedding_shape(c.embedding, self.embedding_dim)

        total_inserted = 0
        insert_sql = """
        INSERT INTO knowledge_chunks
            (id, tenant_id, source_id, content, embedding, chunk_sequence, metadata, created_at)
        VALUES ($1, $2, $3, $4, $5::vector, $6, $7, NOW())
        ON CONFLICT (id) DO NOTHING;
        """
        try:
            async with get_async_pg_conn() as conn:
                # Use transaction for batch safety
                async with conn.transaction():
                    for i in range(0, len(chunks), batch_size):
                        batch = chunks[i:i + batch_size]
                        # Prepared single statement repeated to avoid long multi-value SQL building
                        for c in batch:
                            await conn.execute(
                                insert_sql,
                                str(c.id),
                                c.tenant_id,
                                str(c.source_id),
                                c.content,
                                # asyncpg should map Python list to vector if pgvector is configured.
                                to_pgvector(c.embedding),
                                c.chunk_sequence,
                                json.dumps(c.metadata) if c.metadata else None,
                            )
                        total_inserted += len(batch)
            logger.info("Inserted %d chunks (batches of %d).",
                        total_inserted, batch_size)
            return total_inserted
        except Exception as exc:
            logger.exception("Error inserting chunks: %s", exc)
            raise

    async def get_chunks_by_source(self,
                                   source_id: Union[UUID, str],
                                   *,
                                   tenant_id: str,
                                   limit: int = 100,
                                   offset: int = 0,
                                   order_by_sequence: bool = True
                                   ) -> List["KnowledgeChunk"]:
        order = "chunk_sequence ASC" if order_by_sequence else "created_at DESC"
        sql = f"""
        SELECT id, tenant_id, source_id, content, embedding, chunk_sequence, metadata, created_at
        FROM knowledge_chunks
        WHERE tenant_id = $1 AND source_id = $2
        ORDER BY {order}
        LIMIT $3 OFFSET $4;
        """
        try:
            async with get_async_pg_conn() as conn:
                rows = await conn.fetch(
                    sql, tenant_id, str(source_id), limit, offset
                )
                result = []
                for r in rows:
                    chunk = KnowledgeChunk(
                        id=str(r["id"]),
                        tenant_id=r["tenant_id"],
                        source_id=str(r["source_id"]),
                        content=r["content"],
                        embedding=parse_embedding(
                            r["embedding"], self.embedding_dim),
                        chunk_sequence=r.get("chunk_sequence"),
                        metadata=parse_metadata(r.get("metadata")),
                        created_at=r["created_at"],
                    )
                    result.append(chunk)
                return result
        except Exception as exc:
            logger.exception(
                "Error fetching chunks for source %s: %s", source_id, exc)
            raise

    async def search_similar_chunks(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        *,
        tenant_id: str,
        user_id: Optional[str] = None,
        min_score: Optional[float] = None
    ) -> List[Tuple[KnowledgeChunk, float]]:
        """
        Perform a vector similarity search using pgvector operator `<->`.
        Returns list of tuples: (KnowledgeChunk, distance_score). Lower distance = more similar.
        """

        _ensure_embedding_shape(query_embedding, self.embedding_dim)

        # Wrap embedding for pgvector
        query_vec = to_pgvector(query_embedding)

        # Build base query
        base_sql = """
        SELECT kc.id, kc.tenant_id, kc.source_id, kc.content, kc.embedding, kc.chunk_sequence, kc.metadata, kc.created_at,
            (kc.embedding <-> $1) AS distance
        FROM knowledge_chunks kc
        JOIN knowledge_sources ks
          ON ks.tenant_id = kc.tenant_id AND ks.id = kc.source_id
        """
        params: List[Any] = [query_vec, tenant_id]
        where_clauses: List[str] = [
            f"kc.tenant_id = ${len(params)}",
            f"ks.tenant_id = ${len(params)}",
        ]
        if user_id:
            params.append(user_id)
            where_clauses.append(f"ks.user_id = ${len(params)}")

        base_sql += " WHERE " + " AND ".join(where_clauses)

        base_sql += f" ORDER BY distance ASC LIMIT ${len(params) + 1};"
        params.append(top_k)

        try:
            async with get_async_pg_conn() as conn:
                rows = await conn.fetch(base_sql, *params)
                results: List[Tuple[KnowledgeChunk, float]] = []
                for r in rows:
                    dist = float(
                        r["distance"]) if r["distance"] is not None else float("inf")
                    if min_score is not None and dist > min_score:
                        continue
                    chunk = KnowledgeChunk(
                        id=str(r["id"]),
                        tenant_id=r["tenant_id"],
                        source_id=str(r["source_id"]),
                        content=r["content"],
                        embedding=parse_embedding(
                            r["embedding"], self.embedding_dim),
                        chunk_sequence=r.get("chunk_sequence"),
                        metadata=json.loads(r["metadata"]) if r.get(
                            "metadata") else {},
                        created_at=r["created_at"],
                    )
                    results.append((chunk, dist))
                return results
        except Exception as exc:
            logger.exception("Error in vector search: %s", exc)
            raise

    async def count_chunks_for_source(
        self, source_id: Union[UUID, str], *, tenant_id: str
    ) -> int:
        sql = """
        SELECT COUNT(*) FROM knowledge_chunks
        WHERE tenant_id = $1 AND source_id = $2;
        """
        try:
            async with get_async_pg_conn() as conn:
                row = await conn.fetchval(sql, tenant_id, str(source_id))
                return int(row or 0)
        except Exception as exc:
            logger.exception(
                "Error counting chunks for source %s: %s", source_id, exc)
            raise

    async def remove_chunks_for_source(
        self, source_id: Union[UUID, str], *, tenant_id: str
    ) -> int:
        sql = """
        DELETE FROM knowledge_chunks
        WHERE tenant_id = $1 AND source_id = $2
        RETURNING id;
        """
        try:
            async with get_async_pg_conn() as conn:
                rows = await conn.fetch(sql, tenant_id, str(source_id))
                return len(rows)
        except Exception as exc:
            logger.exception(
                "Error removing chunks for source %s: %s", source_id, exc)
            raise

    # ---------------------------
    # Helpers: chunking + embedding pipeline
    # ---------------------------
    async def ingest_text_document(
        self,
        text: str,
        source: KnowledgeSource,
        embedding_provider: EmbeddingProvider,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
    ) -> Tuple[KnowledgeSource, int]:
        """
        High-level ingestor:
         - create source entry if needed
         - split text into chunks
         - compute embeddings (in batches)
         - store chunks
         - set source status to ACTIVE on success

        Returns (source, inserted_chunks_count).
        """
        if not text:
            raise ValueError("text must be provided")

        # truncate very long docs to protect embedding costs
        if len(text) > MAX_DOC_TEXT_LENGTH:
            logger.warning(
                "Document length %d exceeds MAX_DOC_TEXT_LENGTH; it will be truncated.", len(text))
            text = text[:MAX_DOC_TEXT_LENGTH]

        # create or ensure source exists
        created_source = await self.create_source(source)

        # chunking text using token
        chunks_text = tokenized_chunk_text(
            text, source.source_type, max_tokens, overlap_tokens)
        logger.debug("Document chunked into %d chunks", len(chunks_text))

        # embed in batches (we'll choose a conservative batch size)
        EMB_BATCH = 32
        all_embeddings: List[List[float]] = []
        for i in range(0, len(chunks_text), EMB_BATCH):
            batch_texts = chunks_text[i:i + EMB_BATCH]
            emb_batch = await embedding_provider.embed_texts(batch_texts)
            # validation
            for emb in emb_batch:
                _ensure_embedding_shape(emb, self.embedding_dim)
            all_embeddings.extend(emb_batch)

        # prepare chunk models
        chunk_models: List[KnowledgeChunk] = []
        for idx, (chunk_text, emb) in enumerate(zip(chunks_text, all_embeddings)):
            chunk_models.append(KnowledgeChunk(
                id=uuid7(),
                tenant_id=created_source.tenant_id,
                source_id=created_source.id,
                content=chunk_text,
                embedding=emb,
                chunk_sequence=idx,
                metadata={"source_name": created_source.name}
            ))

        # batch insert
        inserted = await self.add_chunks(chunk_models)

        # mark source active if inserted successfully
        if inserted > 0:
            await self.update_source_status(
                created_source.id, ProcessingStatus.ACTIVE,
                tenant_id=created_source.tenant_id,
            )
        else:
            await self.update_source_status(
                created_source.id, ProcessingStatus.FAILED,
                tenant_id=created_source.tenant_id,
            )

        return created_source, inserted

    # ---------------------------
    # Convenience / Admin
    # ---------------------------
    async def archive_source(
        self, source_id: Union[UUID, str], *, tenant_id: str
    ) -> bool:
        return await self.update_source_status(
            source_id, ProcessingStatus.ARCHIVED, tenant_id=tenant_id
        )

    async def mark_source_failed(
        self, source_id: Union[UUID, str], *, tenant_id: str,
        reason: Optional[str] = None,
    ) -> bool:
        # optionally store reason in metadata
        try:
            src = await self.get_source(source_id, tenant_id=tenant_id)
            if not src:
                return False
            metadata = src.metadata or {}
            if reason:
                metadata["last_error"] = {
                    "message": reason, "at": datetime.now(timezone.utc).isoformat()}
            # Update metadata and status atomically
            sql = """
            UPDATE knowledge_sources
            SET status = $1, metadata = $2, updated_at = NOW()
            WHERE id = $3 AND tenant_id = $4
            RETURNING id;
            """
            async with get_async_pg_conn() as conn:
                row = await conn.fetchrow(
                    sql,
                    ProcessingStatus.FAILED.value,
                    json.dumps(metadata),
                    str(source_id),
                    tenant_id,
                )
                return bool(row)
        except Exception as exc:
            logger.exception(
                "Error marking source failed %s: %s", source_id, exc)
            raise


# -----------------------------------------------
# Embedding provider wrapper for GeminiClient
# -----------------------------------------------
class GeminiEmbeddingProvider:
    def __init__(self):
        self.client = GeminiClient()

    async def embed_texts(self, texts: Iterable[str]) -> List[List[float]]:
        embeddings = []
        for text in texts:
            # If GeminiClient embedding is sync, wrap it in asyncio.to_thread
            emb_vector = await asyncio.to_thread(self.client.get_embedding, text)
            embeddings.append(emb_vector)
        return embeddings
