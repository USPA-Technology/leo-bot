from leoai.ai_knowledge_models import KnowledgeChunk, KnowledgeSource


def test_knowledge_models_generate_uuidv7_ids():
    source = KnowledgeSource(user_id="user", tenant_id="tenant", name="source")
    chunk = KnowledgeChunk(
        tenant_id=source.tenant_id,
        source_id=source.id,
        content="chunk",
        embedding=[],
    )

    assert source.id.version == 7
    assert chunk.id.version == 7
    assert source.source_type == "other"
