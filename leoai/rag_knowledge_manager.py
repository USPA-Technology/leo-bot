# leoai/rag_knowledge_manager.py
import asyncio
import hashlib
import ipaddress
import json
import logging
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Protocol, Sequence
from uuid import NAMESPACE_URL, UUID, uuid5

import httpx
import numpy as np
from pydantic import BaseModel

from leoai.ai_core import get_embedding_model
from leoai.ai_knowledge_models import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_OVERLAP_TOKENS,
    KnowledgeSourceType,
    tokenized_chunk_text,
)
from leoai.db_utils import get_async_pg_conn, to_pgvector
from leoai.ai_knowledge_manager import MAX_DOC_TEXT_LENGTH

logger = logging.getLogger("KnowledgeRetriever")


class KnowledgeInputError(ValueError):
    """A source cannot be ingested because its URL or contents are invalid."""


class KnowledgeFetchError(RuntimeError):
    """The remote source could not be downloaded successfully."""


class KnowledgeUpdateResult(BaseModel):
    source_id: UUID
    visitor_id: str
    tenant_id: str
    source_type: KnowledgeSourceType
    url: str
    name: str
    status: str
    chunk_count: int
    embedding_dimensions: int


@dataclass(frozen=True)
class WebDocument:
    title: str
    text: str
    fetched_url: str
    links: tuple[str, ...] = ()


class KnowledgeEmbeddingModel(Protocol):
    @property
    def dimensions(self) -> int: ...

    @property
    def provider(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    def encode(
        self, sentences: Sequence[str], *, batch_size: int,
        normalize_embeddings: bool,
    ) -> np.ndarray: ...


class WebPageFetcher(Protocol):
    async def fetch(self, url: str) -> WebDocument: ...


class _WebPageParser(HTMLParser):
    """Prefer article/main content and discard scripts and navigation."""

    HIDDEN = {"script", "style", "noscript", "nav", "footer", "header", "svg"}
    BLOCKS = {"p", "div", "article", "main", "section", "li", "br", "h1", "h2", "h3", "h4"}
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
            "param", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, bool, bool]] = []
        self.title: list[str] = []
        self.content: list[str] = []
        self.article: list[str] = []
        self.links: list[str] = []

    def _append(self, text: str) -> None:
        if any(hidden for _, hidden, _ in self.stack):
            return
        self.content.append(text)
        if any(article for _, _, article in self.stack):
            self.article.append(text)

    def handle_starttag(self, tag: str, attrs) -> None:
        attributes = dict(attrs)
        if tag == "a" and isinstance(attributes.get("href"), str):
            self.links.append(attributes["href"])
        classes = (attributes.get("class") or "").split()
        hidden = tag in self.HIDDEN or "hidden" in attributes or attributes.get("aria-hidden") == "true"
        article = tag in {"article", "main"} or bool(
            {"post-body", "entry-content", "article-body"}.intersection(classes)
        )
        if tag not in self.VOID:
            self.stack.append((tag, hidden, article))
        if tag in self.BLOCKS:
            self._append("\n\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.BLOCKS:
            self._append("\n\n")
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if any(tag == "title" for tag, _, _ in self.stack):
            self.title.append(data)
        else:
            self._append(data)

    def document(self, url: str) -> WebDocument:
        text = "".join(self.article or self.content)
        paragraphs = [" ".join(part.split()) for part in text.split("\n\n")]
        return WebDocument(
            title=" ".join("".join(self.title).split()) or url,
            text="\n\n".join(part for part in paragraphs if part),
            fetched_url=url,
            links=tuple(self.links),
        )


class PublicWebPageFetcher:
    """Fetch bounded public HTTP(S) content, including validated redirects."""

    MAX_BYTES: int = 2_000_000
    MAX_REDIRECTS: int = 5

    @staticmethod
    def normalize_url(url: str) -> httpx.URL:
        try:
            parsed = httpx.URL(url)
        except httpx.InvalidURL as exc:
            raise KnowledgeInputError("Invalid source URL.") from exc
        if parsed.scheme not in {"http", "https"} or not parsed.host or parsed.userinfo:
            raise KnowledgeInputError("Source URL must be public HTTP(S), without credentials.")
        return parsed.copy_with(fragment=None)

    async def _public_address(self, url: httpx.URL) -> str:
        try:
            addresses = await asyncio.wait_for(
                asyncio.get_running_loop().getaddrinfo(
                    url.host, url.port or (443 if url.scheme == "https" else 80),
                    type=socket.SOCK_STREAM,
                ),
                timeout=10,
            )
        except (socket.gaierror, TimeoutError) as exc:
            raise KnowledgeFetchError("Could not resolve the source hostname.") from exc
        if not addresses or any(
            not ipaddress.ip_address(address[4][0]).is_global for address in addresses
        ):
            raise KnowledgeInputError("Source URL must not resolve to a private or local network.")
        # Pin the validated address so DNS changes cannot bypass the public-address check.
        return str(addresses[0][4][0])

    async def fetch(self, url: str) -> WebDocument:
        current = self.normalize_url(url)
        try:
            async with httpx.AsyncClient(
                timeout=20, follow_redirects=False, trust_env=False,
            ) as client:
                for _ in range(self.MAX_REDIRECTS + 1):
                    address = await self._public_address(current)
                    async with client.stream(
                        "GET", current.copy_with(host=address),
                        headers={
                            "Host": current.netloc.decode("ascii"),
                            "User-Agent": "LEO-BOT/1.0",
                            "Accept": "text/html,application/xhtml+xml,text/plain",
                        },
                        extensions={"sni_hostname": current.host},
                    ) as response:
                        if response.is_redirect:
                            location = response.headers.get("location")
                            if not location:
                                raise KnowledgeFetchError("Source redirect has no destination.")
                            current = self.normalize_url(str(current.join(location)))
                            continue
                        response.raise_for_status()
                        content_type = response.headers.get("content-type", "").split(";")[0].lower().strip()
                        if content_type not in {"text/html", "application/xhtml+xml", "text/plain"}:
                            raise KnowledgeInputError("Only HTML and plain-text web pages are supported.")
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            body.extend(chunk)
                            if len(body) > self.MAX_BYTES:
                                raise KnowledgeInputError("Source response exceeds the 2 MB download limit.")
                        try:
                            decoded = body.decode(response.encoding or "utf-8")
                        except (LookupError, UnicodeDecodeError) as exc:
                            raise KnowledgeInputError("Source text encoding is unsupported or invalid.") from exc
                        if content_type == "text/plain":
                            return WebDocument(str(current), decoded.strip(), str(current))
                        parser = _WebPageParser()
                        parser.feed(decoded)
                        parser.close()
                        return parser.document(str(current))
        except httpx.HTTPError as exc:
            raise KnowledgeFetchError("Source download failed.") from exc
        raise KnowledgeFetchError("Source has too many redirects.")


class KnowledgeCreator:
    """Generate embeddings first, then atomically replace one visitor-owned source."""

    def __init__(
        self,
        embedding_model: KnowledgeEmbeddingModel | None = None,
        fetcher: WebPageFetcher | None = None,
    ):
        self.embedding_model = embedding_model if embedding_model is not None else get_embedding_model()
        self.fetcher = fetcher if fetcher is not None else PublicWebPageFetcher()

    @staticmethod
    def _validate_visitor(visitor_id: str) -> str:
        visitor_id = visitor_id.strip()
        if not visitor_id or len(visitor_id) > 50:
            raise KnowledgeInputError("visitor_id must contain 1 to 50 characters.")
        return visitor_id

    async def upsert_url(
        self, url: str, *, visitor_id: str,
        source_type: KnowledgeSourceType = KnowledgeSourceType.WEB_PAGE,
        name: str | None = None,
        tenant_id: str = "default",
    ) -> KnowledgeUpdateResult:
        if source_type != KnowledgeSourceType.WEB_PAGE:
            raise KnowledgeInputError("URL ingestion currently supports source_type=web_page only.")
        visitor_id = self._validate_visitor(visitor_id)
        document = await self.fetcher.fetch(url)
        return await self.upsert_text(
            document.text, uri=str(PublicWebPageFetcher.normalize_url(url)),
            visitor_id=visitor_id, source_type=source_type,
            name=name or document.title,
            metadata={"fetched_url": document.fetched_url},
            tenant_id=tenant_id,
        )

    async def upsert_text(
        self, text: str, *, uri: str, visitor_id: str,
        source_type: KnowledgeSourceType = KnowledgeSourceType.WEB_PAGE,
        name: str,
        metadata: dict[str, Any] | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
        tenant_id: str = "default",
    ) -> KnowledgeUpdateResult:
        visitor_id = self._validate_visitor(visitor_id)
        if not text.strip() or not name.strip() or not uri.strip():
            raise KnowledgeInputError("Source text, name, and URI must be non-empty.")
        if len(text) > MAX_DOC_TEXT_LENGTH:
            raise KnowledgeInputError(f"Extracted source text exceeds {MAX_DOC_TEXT_LENGTH} characters.")
        if max_tokens <= 0 or not 0 <= overlap_tokens < max_tokens:
            raise KnowledgeInputError("Chunk overlap must be non-negative and smaller than the chunk size.")
        if self.embedding_model.dimensions != 768:
            raise RuntimeError("knowledge_chunks requires 768-dimensional embeddings.")

        chunks = tokenized_chunk_text(text, source_type, max_tokens, overlap_tokens)
        if not chunks:
            raise KnowledgeInputError("Source did not produce readable chunks.")
        embeddings = np.asarray(await asyncio.to_thread(
            self.embedding_model.encode, chunks,
            batch_size=32, normalize_embeddings=True,
        ), dtype=np.float32)
        if (
            embeddings.shape != (len(chunks), 768)
            or not np.isfinite(embeddings).all()
            or np.any(np.linalg.norm(embeddings, axis=1) == 0)
        ):
            raise RuntimeError("Embedding provider returned invalid chunk count, values, or dimensions.")

        source_id = uuid5(NAMESPACE_URL, json.dumps([tenant_id, visitor_id, source_type.value, uri]))
        source_metadata = {
            **(metadata or {}),
            "content_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "embedding_provider": self.embedding_model.provider,
            "embedding_model": self.embedding_model.model_name,
            "embedding_dimensions": 768,
        }
        rows = [
            (
                uuid5(source_id, str(index)), source_id, tenant_id, chunk,
                to_pgvector(vector.tolist()), index,
                json.dumps({"source_name": name.strip(), "uri": uri}),
            )
            for index, (chunk, vector) in enumerate(zip(chunks, embeddings))
        ]
        async with get_async_pg_conn() as conn:
            async with conn.transaction():
                # The upsert's row lock serializes concurrent replacements of this source.
                await conn.execute("""
                    INSERT INTO knowledge_sources (
                        id, user_id, tenant_id, source_type, name, uri, status, metadata
                    )
                    VALUES ($1,$2,$3,$4,$5,$6,'active',$7::jsonb)
                    ON CONFLICT (id) DO UPDATE SET
                        name=EXCLUDED.name, status=EXCLUDED.status,
                        metadata=EXCLUDED.metadata, updated_at=NOW();
                """, source_id, visitor_id, tenant_id, source_type.value,
                    name.strip(), uri, json.dumps(source_metadata))
                await conn.execute(
                    """
                    DELETE FROM knowledge_chunks
                    WHERE tenant_id=$1 AND source_id=$2
                    """,
                    tenant_id,
                    source_id,
                )
                await conn.executemany("""
                    INSERT INTO knowledge_chunks (
                        id, source_id, tenant_id, content, embedding, chunk_sequence, metadata
                    )
                    VALUES ($1,$2,$3,$4,$5::vector,$6,$7::jsonb);
                """, rows)
        logger.info("Upserted knowledge source %s for visitor %s with %d chunks",
                    source_id, visitor_id, len(chunks))
        return KnowledgeUpdateResult(
            source_id=source_id, visitor_id=visitor_id, tenant_id=tenant_id,
            source_type=source_type, url=uri, name=name.strip(), status="active",
            chunk_count=len(chunks), embedding_dimensions=768,
        )


class KnowledgeRetriever:
    def __init__(self, embedding_model):
        self.embedding_model = embedding_model

    async def retrieve(
        self, user_message: str, tenant_id: str, limit: int = 5, *, user_id: str
    ) -> str:
        if limit <= 0:
            raise ValueError("Document retrieval limit must be positive.")
        embedding = await asyncio.to_thread(
            self.embedding_model.encode, user_message, normalize_embeddings=True
        )
        vector = to_pgvector(embedding.tolist())

        async with get_async_pg_conn() as conn:
            rows = await conn.fetch("""
                SELECT kc.content, ks.name AS source_name, ks.uri
                FROM knowledge_chunks AS kc
                JOIN knowledge_sources AS ks
                  ON kc.tenant_id = ks.tenant_id AND kc.source_id = ks.id
                WHERE ks.tenant_id = $1 AND ks.user_id = $2 AND ks.status = 'active'
                  AND kc.tenant_id = $1
                ORDER BY kc.embedding <=> $3::vector
                LIMIT $4;
            """, tenant_id, user_id, vector, limit)
        if not rows:
            logger.info("No related knowledge found.")
            return ""
        chunks = [
            f"Source: {row['source_name']}\n"
            + (f"URI: {row['uri']}\n" if row["uri"] else "")
            + row["content"].strip()
            for row in rows if row["content"]
        ]
        text = "\n\n---\n\n".join(chunks)
        return text[:MAX_DOC_TEXT_LENGTH]

    async def retrieve_selected_place(
        self,
        selected_place: dict[str, Any],
        user_message: str,
        *,
        tenant_id: str = "default",
        limit: int = 3,
    ) -> str:
        """Retrieve the best knowledge chunks for the active selected place."""
        if limit <= 0:
            raise ValueError("Selected-place retrieval limit must be positive.")
        if not isinstance(selected_place, dict):
            raise ValueError("Selected place must be an object.")

        place_id = str(selected_place.get("id") or "").strip()
        place_name = str(selected_place.get("name") or "").strip()
        if not place_id and not place_name:
            return ""

        place_query_parts = [
            place_name,
            str(selected_place.get("address") or "").strip(),
            str(selected_place.get("category") or "").strip(),
            " ".join(
                str(tag).strip()
                for tag in selected_place.get("tags") or []
                if str(tag).strip()
            ),
            str(selected_place.get("description") or "").strip(),
        ]
        place_query = " ".join(part for part in place_query_parts if part)
        query = " ".join(part for part in (place_query, user_message.strip()) if part)
        embedding = await asyncio.to_thread(
            self.embedding_model.encode, query, normalize_embeddings=True
        )
        vector = to_pgvector(embedding.tolist())

        async with get_async_pg_conn() as conn:
            rows = await conn.fetch(
                """
                SELECT kc.content, ks.name AS source_name, ks.uri
                FROM knowledge_sources AS ks
                JOIN knowledge_chunks AS kc
                  ON kc.tenant_id = ks.tenant_id AND kc.source_id = ks.id
                WHERE ks.tenant_id IN ($1, 'global')
                  AND kc.tenant_id = ks.tenant_id
                  AND ks.status = 'active'
                  AND (
                      ($2 <> '' AND (
                          ks.metadata->>'geo_place_id' = $2
                          OR kc.metadata->>'geo_place_id' = $2
                      ))
                      OR to_tsvector(
                          'simple',
                          concat_ws(
                              ' ',
                              coalesce(ks.name, ''),
                              coalesce(ks.code_name, ''),
                              coalesce(ks.metadata::text, '')
                          )
                      ) @@ plainto_tsquery('simple', $3)
                      OR to_tsvector('simple', kc.content)
                          @@ plainto_tsquery('simple', $3)
                  )
                ORDER BY kc.embedding <=> $4::vector
                LIMIT $5;
                """,
                tenant_id,
                place_id,
                place_query,
                vector,
                limit,
            )

        chunks = [
            f"Source: {row['source_name']}\n"
            + (f"URI: {row['uri']}\n" if row["uri"] else "")
            + row["content"].strip()
            for row in rows
            if row["content"]
        ]
        return "\n\n---\n\n".join(chunks)[:MAX_DOC_TEXT_LENGTH]
