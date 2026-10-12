---
marp: true
theme: default
paginate: true
footer: "LEO Bot • Buổi 10"
---

# Buổi 10
## Knowledge Graph và Context Enrichment

**Năng lực:** chọn data model dựa trên truy vấn, không mặc định dùng graph
database.

---

# Một sự thật quan trọng về repo

LEO Bot hiện dùng:

- PostgreSQL cho relational data;
- PostGIS cho `geom`, distance và radius query;
- pgvector cho semantic similarity;
- Dagster để enrich knowledge;
- Arango xuất hiện ở pipeline/POC, không phải graph traversal chính của chat.

**Knowledge graph trong buổi này là cách mô hình hóa quan hệ và decision
trade-off; không giả định repo đã có graph DB production.**

---

# Các entity và relationship

```text
tenant ─owns─► visitor
visitor ─has─► touchpoint
touchpoint ─near─► geo_place
geo_place ─has─► knowledge_source
knowledge_source ─contains─► knowledge_chunk
chat_message ─belongs_to─► touchpoint
```

Mỗi cạnh cần provenance: tenant, user, source URI, timestamp hoặc query scope.

---

# Relational query đang giải quyết bài toán nào?

`ChatDBManager` dùng:

```sql
ST_DWithin(geom::geography, point::geography, radius)
ORDER BY geom::geography <-> point::geography
LIMIT result_limit
```

Đây là lựa chọn tốt cho “địa điểm gần tọa độ trong bán kính”, có index và
transaction rõ ràng.

---

# Khi graph traversal đáng cân nhắc?

| Query | Phù hợp |
|---|---|
| gần một tọa độ, radius cố định | PostGIS |
| top-k semantic chunks | pgvector |
| entity nhiều hop, path/provenance phức tạp | graph model có thể phù hợp |
| upsert theo tenant/source/chunk | PostgreSQL transaction |

Đừng thêm graph DB chỉ vì từ “relationship” xuất hiện trong requirement.

---

# Demo: enrichment tạo thêm context

1. `geo_places` có place nhưng thiếu knowledge.
2. Dagster tìm nguồn, chunk và embed.
3. `KnowledgeRetriever.retrieve_selected_place` truy xuất chunk theo place.
4. `RAGAgent._build_prompt_node` thêm `selected_place_knowledge`.
5. Prompt nêu nguồn và giữ place scope.

Code anchors:
[`leoai/rag_db_manager.py`](../../leoai/rag_db_manager.py),
[`leoai/rag_knowledge_manager.py`](../../leoai/rag_knowledge_manager.py).

---

# Kiểm chứng trade-off

```bash
pytest tests/test_nearby_places.py
pytest tests/test_geo_places_enrichment.py
pytest tests/test_geo_places_pipeline.py
```

Câu hỏi review:

- query có enforce tenant/user không?
- khoảng cách dùng cùng radius với enrichment không?
- source/chunk có giữ provenance không?
- enrichment fail có làm mất dữ liệu cũ không?

---

# Takeaways & bài tập

- Geo data model: [`leoai/rag_db_manager.py`](../../leoai/rag_db_manager.py)
- Pipeline: [`dags_pipelines/geo_places_pipeline.py`](../../dags_pipelines/geo_places_pipeline.py)
- Related design notes: [`dags_pipelines/README.md`](../../dags_pipelines/README.md)

**Bài tập:** viết một ADR ngắn cho một truy vấn nhiều quan hệ: relational,
PostGIS, pgvector hay graph; nêu data shape, index, provenance và failure mode.

---

# Core concept: graph view và storage không giống nhau

Knowledge graph là cách mô hình hóa **entity + relationship + provenance**.
Nó không bắt buộc phải dùng graph database.

```text
graph view: visitor ─has► touchpoint ─near► place
storage:    PostgreSQL + PostGIS + pgvector
query:      SQL / spatial distance / vector similarity
```

Chọn storage theo query, consistency, index và vận hành thực tế.

---

# Example: place context enrichment

```text
selected_place
  → place identity + tenant scope
  → knowledge_sources
  → knowledge_chunks
  → retrieve_selected_place(...)
  → selected_place_knowledge
  → prompt
```

Relationship giúp chọn đúng entity; vector retrieval giúp chọn đúng evidence
textual cho câu hỏi hiện tại.

---

# Vì sao mô hình hiện tại đúng?

- PostGIS tối ưu nearby/radius query;
- pgvector tối ưu semantic chunk retrieval;
- PostgreSQL transaction giữ source/chunk nhất quán;
- tenant/user/source URI giữ provenance;
- enrichment có thể mở rộng knowledge mà không đổi chat contract.

Chỉ dùng graph DB khi query nhiều-hop và path/provenance thực sự cần nó.

---

# Verify: relationship đến prompt

```bash
pytest tests/test_nearby_places.py
pytest tests/test_geo_places_enrichment.py
pytest tests/test_geo_places_pipeline.py
```

Trace một place:

1. identity trong `geo_places`;
2. source/chunk được tạo;
3. retrieval được scope;
4. evidence xuất hiện trong prompt;
5. failure không làm mất dữ liệu cũ.
