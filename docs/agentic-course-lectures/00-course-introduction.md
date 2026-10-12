---
marp: true
theme: default
paginate: true
footer: "LEO Bot • Course Introduction"
---

<style>
section.dense {
  padding: 34px 64px;
  line-height: 1.1;
}

section.dense h1 {
  margin-bottom: 0.55em;
}

section.dense p,
section.dense ul,
section.dense ol,
section.dense table {
  margin-top: 0.35em;
  margin-bottom: 0.35em;
}
</style>

# Agentic Software Development
## Giới thiệu khóa học

### Học trên chính codebase LEO Bot

**Hình thức:** on-demand  
**Thời lượng:** 12 buổi × 60 phút  
**Đối tượng:** software engineers, backend engineers và giảng viên

---

# Course at a glance

Khóa học giúp học viên học cách:

- thiết kế và đọc một agentic application;
- trace request từ API đến AI provider, database và background pipeline;
- thay đổi workflow có state, routing, context và persistence;
- kiểm thử behavior, failure path và security boundary;
- bàn giao một feature có code, test, evidence và limitation.

**Sản phẩm xuyên suốt:** LEO Bot location-aware assistant và document-chat
workflow.

---

<!-- _class: dense -->

# Vì sao dùng LEO Bot làm lớp học?

LEO Bot là một codebase thực tế có đủ các boundary cần học:

- FastAPI application và nhiều channel/router;
- `RAGAgent` với `langgraph.StateGraph`;
- AI providers và embeddings;
- context, memory, Redis visitor state;
- PostgreSQL, pgvector, PostGIS và pg_trgm;
- knowledge ingestion, retrieval và grounded enrichment;
- Dagster jobs/assets và ArangoDB → PostgreSQL ETL.

Mỗi khái niệm được nối với source, API, table, pipeline hoặc test có thể mở
và kiểm chứng.

---

<!-- _class: dense -->

# Core concept: Agentic Software Development

Một agentic application không chỉ gọi model một lần.

Nó nối các capability thành một workflow có:

- **goal:** nhiệm vụ cần hoàn thành;
- **state:** thông tin giữa các bước;
- **routing:** chọn bước tiếp theo;
- **grounding:** lấy evidence phù hợp;
- **action:** gọi database, API hoặc background job;
- **guardrail:** validation, authorization, error và termination.

Khóa học tập trung vào behavior của toàn hệ thống, không chỉ vào prompt.

---

# Example: một vertical slice của LEO Bot

```text
POST /_leoai/ask
  → FastAPI router
  → RAGAgent / LangGraph
  → context + retrieval
  → AI provider hoặc PostGIS
  → persistence / Dagster enrichment
  → response + evidence/status
```

Học viên không chỉ xem câu trả lời cuối; họ trace được state, decision,
side effect và failure path của request.

---

# Vì sao cách học này hiệu quả?

- code thật làm rõ ranh giới giữa LLM, RAG, agent, API và infrastructure;
- mỗi buổi giới hạn vào một năng lực kỹ thuật;
- lab đi qua một vertical slice có thể chạy và test;
- failure case được xem là một phần của design;
- cùng một sản phẩm giúp kiến thức nối tiếp thay vì các demo rời rạc.

**Nguyên tắc:** không mô tả framework hoặc component không có trong source code
hoặc dependency manifest.

---

# Learning outcomes

Sau khóa học, học viên có thể:

1. Trace request qua FastAPI, router, `RAGAgent`, AI provider, database và
   Redis.
2. Giải thích và thay đổi state graph có routing, validation, context,
   generation và persistence.
3. Cấu hình chat/reasoning/embedding provider mà không khóa application vào
   một nhà cung cấp.
4. Xây knowledge flow có source, chunk, embedding, metadata và tenant filter.

---

<!-- _class: dense -->

# Learning outcomes tiếp theo

Học viên cũng có thể:

5. Thêm backend capability có kiểm soát: document chat, geolocation touchpoint
   hoặc nearby-place enrichment.
6. Viết regression test cho input validation, retrieval, context, API và
   pipeline behavior.
7. Nhận diện failure mode: credential, dữ liệu thiếu, location sai, URL không
   an toàn, provider, database và pipeline failure.

**Đầu ra quan trọng:** giải thích được bằng evidence, không chỉ trình diễn
được một response.

---

# Learning journey

```text
Understand
    → Model State
    → Route
    → Ground
    → Persist
    → Integrate
    → Enrich
    → Secure
    → Test
    → Deliver
```

Mỗi bước nối với một phần của LEO Bot và chuẩn bị cho bước kế tiếp.

---

# Cách học trong mỗi buổi

## Theory — 50–60 phút

Đọc kiến trúc, trace code và phân tích trade-off.

## Lab — 60–70 phút

Chạy repository, test một vertical slice và review failure cases.

Mỗi buổi cập nhật cùng location-aware assistant và document-chat workflow,
không tạo một sample project tách rời.

---

# Lộ trình 12 buổi: nền tảng

| Buổi | Trọng tâm |
|---:|---|
| 1 | LEO Bot architecture và agentic software development |
| 2 | LangGraph workflow và agent loop |
| 3 | AI provider abstraction và embeddings |
| 4 | Context engineering, memory và visitor state |

**Kết quả giai đoạn:** hiểu application boundary, state, provider và context
trước khi thêm knowledge hoặc side effect.

---

# Lộ trình 12 buổi: grounding và integration

| Buổi | Trọng tâm |
|---:|---|
| 5 | Knowledge ingestion và RAG trên PostgreSQL |
| 6 | Grounded place workflows: PostGIS và Brave Search |
| 7 | Dagster pipelines, enrichment và CDP ETL |
| 8 | FastAPI API, web client và messaging channels |

**Kết quả giai đoạn:** nối retrieval, geospatial grounding, background job và
channel adapter thành một backend agent hoàn chỉnh hơn.

---

# Lộ trình 12 buổi: reliability và delivery

| Buổi | Trọng tâm |
|---:|---|
| 9 | Security, reliability và regression testing |
| 10 | Knowledge Graph cho context enrichment và intent prediction |
| 11 | Persona, consent và context-aware personalization |
| 12 | Capstone: xây tính năng mới hoặc nâng cấp LEO Bot |

**Kết quả giai đoạn:** thiết kế feature có provenance, isolation, test,
failure evidence và khả năng bàn giao.

---

<!-- _class: dense -->

# Repository map

| Chủ đề | Source of truth |
|---|---|
| Startup/configuration | [`main_app.py`](../../main_app.py), [`main_config.py`](../../main_config.py) |
| Agent workflow | [`leoai/rag_agent.py`](../../leoai/rag_agent.py) |
| Providers/embeddings | [`leoai/ai_core.py`](../../leoai/ai_core.py) |
| Context/prompt | [`leoai/rag_context_manager.py`](../../leoai/rag_context_manager.py), [`leoai/rag_prompt_builder.py`](../../leoai/rag_prompt_builder.py) |
| Chat/geo SQL | [`leoai/rag_db_manager.py`](../../leoai/rag_db_manager.py) |
| Knowledge/RAG | [`leoai/rag_knowledge_manager.py`](../../leoai/rag_knowledge_manager.py) |
| Jobs/assets | [`dags_pipelines/`](../../dags_pipelines/) |

---

# Capstone và deliverables

Mỗi học viên hoặc nhóm chọn một feature mới hoặc một upgrade cụ thể:

- feature request, user scenario và acceptance criteria;
- source map của request path;
- implementation dùng abstraction hiện có;
- regression tests cho happy path và failure path;
- database/query review cho tenant, vector hoặc geospatial scope;
- demo trước/sau, response evidence và limitation còn lại.

Capstone phải là thay đổi thật cho LEO Bot, không chỉ là prompt demo.

---

# Course completion

Khóa học hoàn thành khi học viên có thể:

- giải thích architecture và decision flow;
- thay đổi một capability mà không phá contract;
- chứng minh behavior bằng test và evidence;
- nhận diện giới hạn, rủi ro và failure mode;
- bàn giao feature để người khác chạy lại và debug.

> **Agentic Software Development = hiểu hệ thống, kiểm soát hành động và
> bàn giao bằng bằng chứng.**
