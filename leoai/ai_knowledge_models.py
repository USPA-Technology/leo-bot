
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, constr
from enum import Enum
import re

from typing import Any, Dict, List, Optional
from uuid import UUID
from datetime import datetime, timezone
from uuid6 import uuid7

# ---------------------------------------------------------------------
# Enum Models
# ---------------------------------------------------------------------
class KnowledgeSourceType(str, Enum):
    # Textual & Document Sources
    BOOK_SUMMARY = "book_summary"               # extracted or summarized from books
    REPORT_ANALYTICS = "report_analytics"       # business or market reports
    UPLOADED_DOCUMENT = "uploaded_document"     # user-uploaded PDFs, Word docs, etc.
    WEB_PAGE = "web_page"                       # scraped website content
    RESEARCH_PAPER = "research_paper"           # scientific or academic publication
    KNOWLEDGE_BASE_ARTICLE = "knowledge_base_article"  # internal or external wiki, FAQ, SOP

    # Data & Technical Sources
    DATASET = "dataset"                         # structured tabular data (CSV, JSON, SQL)
    CODE_REPOSITORY = "code_repository"         # source code or API docs
    API_DOCUMENTATION = "api_documentation"     # REST/GraphQL API reference or schema
    SYSTEM_LOG = "system_log"                   # application or infrastructure logs

    # Conversational & Social Sources
    CONVERSATION_LOG = "conversation_log"       # chatbot or customer support transcripts
    MEETING_TRANSCRIPT = "meeting_transcript"   # AI-generated meeting notes or Zoom calls
    SOCIAL_MEDIA_POST = "social_media_post"     # tweets, LinkedIn posts, or public threads

    # Media & Multimodal Sources
    VIDEO_TRANSCRIPT = "video_transcript"       # text extracted from video
    AUDIO_TRANSCRIPT = "audio_transcript"       # text extracted from podcast or call
    OTHER = "other"                             # fallback for anything unclassified


class ProcessingStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    ACTIVE = "active"
    FAILED = "failed"
    ARCHIVED = "archived"


# ---------------------------------------------------------------------
# Pydantic Table Models
# ---------------------------------------------------------------------
class KnowledgeSource(BaseModel):
    id: UUID = Field(default_factory=uuid7)
    user_id: constr(strip_whitespace=True, min_length=1) # type: ignore
    tenant_id: constr(strip_whitespace=True, min_length=1) # type: ignore
    source_type: KnowledgeSourceType = Field(default=KnowledgeSourceType.OTHER)
    name: str
    code_name: Optional[str] = ""
    uri: Optional[str] = None
    status: ProcessingStatus = Field(default=ProcessingStatus.PENDING)
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class KnowledgeChunk(BaseModel):
    id: UUID = Field(default_factory=uuid7)
    tenant_id: constr(strip_whitespace=True, min_length=1) # type: ignore
    source_id: UUID
    content: str
    embedding: List[float]
    chunk_sequence: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------
DEFAULT_MAX_TOKENS = 200 
DEFAULT_OVERLAP_TOKENS = 40

def token_count(text: str) -> int:
    """Return a lightweight whitespace-token estimate for text chunk sizing."""
    return len(text.split())


def smart_split(text: str, source_type: KnowledgeSourceType) -> List[str]:
    """
    Split text based on the structure of the source type.
    Each type uses natural delimiters or semantic cues.
    """
    if not text:
        return []

    if source_type in {
        KnowledgeSourceType.BOOK_SUMMARY,
        KnowledgeSourceType.REPORT_ANALYTICS,
        KnowledgeSourceType.RESEARCH_PAPER,
        KnowledgeSourceType.KNOWLEDGE_BASE_ARTICLE,
        KnowledgeSourceType.WEB_PAGE,
    }:
        # Split by paragraphs or Markdown headings
        return re.split(r"\n{2,}|(?=^#{1,6}\s)", text, flags=re.MULTILINE)

    elif source_type in {
        KnowledgeSourceType.CONVERSATION_LOG,
        KnowledgeSourceType.MEETING_TRANSCRIPT,
        KnowledgeSourceType.SOCIAL_MEDIA_POST,
    }:
        # Split by speaker turns, timestamps, or message markers
        return re.split(r"(?<=\n)(?:\[?\d{1,2}:\d{2}|\w+:|\s*-\s)", text)

    elif source_type in {
        KnowledgeSourceType.CODE_REPOSITORY,
        KnowledgeSourceType.API_DOCUMENTATION,
    }:
        # Split by function/class blocks, or sections like "### Endpoint"
        return re.split(r"(?=^def\s|^class\s|^###\s|^#\s)", text, flags=re.MULTILINE)

    elif source_type == KnowledgeSourceType.SYSTEM_LOG:
        # Split by log lines or timestamps
        return re.split(r"(?=\n\d{4}-\d{2}-\d{2}|\nINFO|\nWARN|\nERROR)", text)

    elif source_type == KnowledgeSourceType.DATASET:
        # Split by CSV-like or JSON array chunks
        return re.split(r"\n(?=\[|\{|\d+,)", text)

    else:
        # Fallback: generic paragraph-based split
        return text.split("\n\n")


def tokenized_chunk_text(
    text: str,
    source_type: KnowledgeSourceType = KnowledgeSourceType.OTHER,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> List[str]:
    """
    Context-aware text chunker for all knowledge source types.

    Features:
    - Dynamically splits text based on KnowledgeSourceType.
    - Preserves context with token overlap.
    - Gracefully handles long segments.
    """
    if not text:
        return []

    sections = [s.strip() for s in smart_split(text, source_type) if s.strip()]
    chunks: List[str] = []
    current = ""
    current_tokens = 0

    for sec in sections:
        sec_tokens = token_count(sec)
        # Add section to current chunk if fits
        if current_tokens + sec_tokens <= max_tokens:
            current += ("\n\n" + sec) if current else sec
            current_tokens += sec_tokens
        else:
            if current:
                chunks.append(current)
            # Split oversized section into token windows
            tokens = sec.split()
            while len(tokens) > max_tokens:
                part_tokens = tokens[:max_tokens]
                chunks.append(" ".join(part_tokens))
                tokens = tokens[max_tokens - overlap_tokens :]
            current = " ".join(tokens)
            current_tokens = token_count(current)

    if current:
        chunks.append(current)

    return chunks