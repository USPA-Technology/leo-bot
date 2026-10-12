"""Authenticated knowledge ingestion for visitor-scoped document chat."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import HttpUrl, StringConstraints

from leoai.ai_knowledge_models import KnowledgeSourceType
from leoai.rag_knowledge_manager import (
    KnowledgeCreator, KnowledgeFetchError, KnowledgeInputError, KnowledgeUpdateResult,
)
from main_config import require_data_enrichment_key

logger = logging.getLogger(__name__)
router = APIRouter()
creator = KnowledgeCreator()


@router.post("/_leoai/update-knowledge", response_model=KnowledgeUpdateResult)
@router.post("/update-knowledge", response_model=KnowledgeUpdateResult)
async def update_knowledge(
    url: Annotated[HttpUrl, Query()],
    visitor_id: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50), Query()
    ],
    source_type: Annotated[KnowledgeSourceType, Query()] = KnowledgeSourceType.WEB_PAGE,
    name: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    _: None = Depends(require_data_enrichment_key),
):
    try:
        return await creator.upsert_url(
            str(url), visitor_id=visitor_id, source_type=source_type, name=name
        )
    except KnowledgeInputError as exc:
        logger.warning("Knowledge ingestion input rejected for visitor %s: %s", visitor_id, exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KnowledgeFetchError as exc:
        logger.warning("Knowledge source download failed for visitor %s: %s", visitor_id, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Knowledge ingestion failed for visitor %s", visitor_id)
        raise HTTPException(status_code=500, detail="Knowledge ingestion failed; no update was committed.") from exc
