---
marp: true
theme: default
paginate: true
footer: "LEO Bot • Buổi 1"
---

<style>
section.compact-table table {
  font-size: 0.72em;
  line-height: 1.15;
}

section.compact-table th,
section.compact-table td {
  padding: 0.25em 0.4em;
}

section.compact-content {
  font-size: 0.88em;
}

section.compact-content pre {
  font-size: 0.82em;
}
</style>

# Buổi 1
## LEO Bot và Agentic Software

**Năng lực:** phân biệt LLM, GenAI, Agent và Agentic System; sau đó lần theo
một request từ API entry point đến response.

> Một câu hỏi không “đi thẳng” tới model. Nó đi qua validation, routing,
> context, retrieval, persistence và provider.

---

# Vì sao cần phân biệt các khái niệm?

Một hệ thống có thể dùng LLM nhưng **chưa phải Agent**.

- Gọi model một lần để viết câu trả lời: model/GenAI capability.
- Tìm chunks rồi nhét vào prompt: RAG pattern.
- Có API chat: application/channel.
- Có state, routing, tool/action, observation và policy: agentic behavior.

**Mục tiêu của khóa học:** nhìn thấy từng lớp trong code, không gắn nhãn
“agentic” chỉ vì repository có chữ `Agent`.

---

<!-- _class: compact-content -->

# AI → LLM → GenAI → Agentic

```text
Artificial Intelligence
└─ Machine Learning / Deep Learning
   └─ Foundation Model
      └─ LLM ──┐
               ├─ Generative AI: tạo text/code/JSON...
               └─ Agent runtime: state + decision + tools + feedback
```

- **AI:** miền rộng gồm hệ thống thực hiện nhiệm vụ “thông minh”.
- **LLM:** model học phân phối token và sinh/hiểu ngôn ngữ.
- **GenAI:** capability tạo nội dung mới; LLM là một dạng, không phải toàn bộ.
- **Agent:** runtime dùng model cùng state, tools và policy để hoàn thành goal.
- **Agentic system:** application có hành vi chọn bước, hành động, quan sát và
  dừng/chuyển bước trong một boundary được kiểm soát.

---

<!-- _class: compact-table -->

# Bảng phân biên nhanh

| Khái niệm | Có model? | Có state? | Có action/tool? | Có quyết định flow? |
|---|---:|---:|---:|---:|
| LLM call | Có | Không bắt buộc | Không | Không |
| GenAI feature | Thường có | Không bắt buộc | Không bắt buộc | Không bắt buộc |
| RAG | Có thể có | Retrieval state | Retriever | Thường cố định |
| Workflow | Không bắt buộc | Có thể có | Có thể có | Do code định trước |
| Agent | Thường có | Có | Có | Có, trong policy |
| Agentic application | Một hoặc nhiều | Có | Có | Có, bounded/hybrid |

**Agentic không đồng nghĩa:** tự trị tuyệt đối, có ý thức, multi-agent hoặc
được phép chạy code tùy ý.

---

# Tiêu chí nhận diện Agentic

Hỏi hệ thống 6 câu:

1. **Goal:** đang cố hoàn thành mục tiêu nào?
2. **State:** giữ lại thông tin nào giữa các bước/lần gọi?
3. **Decision:** ai chọn bước tiếp theo, model hay code?
4. **Action:** hệ thống có gọi database, API, job hoặc tool không?
5. **Observation:** kết quả action có quay lại state/context không?
6. **Guardrail:** auth, schema, timeout, retry và termination ở đâu?

Thiếu một capability không làm hệ thống “sai”, nhưng phải mô tả đúng mức độ
agentic thay vì thổi phồng autonomy.

---

# Agent loop trong LEO Bot

```text
Observe: question + channel/persona/context
    │
    ▼
IntentDetector (AIClient + JSON schema)
    │
    ├─ low confidence / needs clarification → ask, do not route
    ▼
Validated IntentDetectionResult
    │ primary_intent + purpose + entities + confidence
    ▼
Decide: document / location / general workflow
    │
    ▼
Act: retrieve / query / persist / generate
    │
    ▼
Observe: evidence / response / run_id
    │
    └──► continue to next node or END
```

Graph kết thúc rõ ràng; enrichment được quan sát ở request sau.
Channel chỉ mô tả transport (`web_widget`, `facebook_messenger`, `zalo_oa`);
nó không quyết định intent. Visitor, tenant và touchpoint IDs được giữ ngoài
prompt phân loại vì không cần thiết để xác định mục tiêu.

---

<!-- _class: compact-table -->

# Ánh xạ khái niệm vào code

| Core concept | Source of truth |
|---|---|
| LLM/GenAI provider | [`leoai/ai_core.py`](../../leoai/ai_core.py) |
| Agent state | `ChatMessageState` trong [`leoai/rag_agent.py`](../../leoai/rag_agent.py) |
| Orchestration/decision | `StateGraph`, conditional edges trong [`leoai/rag_agent.py`](../../leoai/rag_agent.py) |
| Intent classification | `IntentDetector` / `IntentDetectionResult` trong [`leoai/ai_intent_detection.py`](../../leoai/ai_intent_detection.py) |
| Memory/context | [`leoai/rag_context_manager.py`](../../leoai/rag_context_manager.py) |
| RAG | [`leoai/rag_knowledge_manager.py`](../../leoai/rag_knowledge_manager.py) |
| Tool/action boundary | [`leoai/rag_db_manager.py`](../../leoai/rag_db_manager.py), [`leoai/rag_agent_utils.py`](../../leoai/rag_agent_utils.py) |
| Background observation | [`dags_pipelines/geo_places_pipeline.py`](../../dags_pipelines/geo_places_pipeline.py) |

Tên `RAGAgent` chỉ có ý nghĩa khi các behavior này nối với nhau thành một
workflow có state và side effect được kiểm soát.

---

# Vì sao khóa học này có tính Agentic?

Lộ trình không chỉ dạy prompt hoặc gọi model:
**Understand → Model State → Route → Ground → Persist → Integrate → Enrich →
Secure → Test → Deliver**

- Trace decision flow, state, RAG, memory, tool và background job.
- Dùng security, evaluation và failure path để giới hạn autonomy.
- Bàn giao behavior bằng test, evidence và runbook.

Đây là khóa **agentic software development trên một bounded/hybrid agentic
application**, không phải khóa thuần LLM prompting.

---

# Điều gì chưa đủ để gọi là Agent?

| Chỉ có | Được gọi là | Chưa đủ vì |
|---|---|---|
| `client.generate_content(prompt)` | LLM/GenAI call | chưa có state/action |
| `retriever.retrieve(...)` | RAG component | chưa quyết định workflow |
| `workflow.add_node(...)` | workflow primitive | chưa có goal/observation |

Chỉ khi các primitive nối với state, routing, action, observation và guardrail
để phục vụ goal thì application mới có agentic behavior.

---

# Mục tiêu

- Xác định được entry point và các router của FastAPI.
- Phân biệt LLM/GenAI capability với Agentic orchestration.
- Phân biệt orchestration, AI provider, data store và background job.
- Dùng một request thật để tìm file triển khai và test liên quan.
- Vẽ được request flow đủ chi tiết để bắt đầu sửa một tính năng nhỏ.

**Repo baseline:** Python 3.12, FastAPI, LangGraph, PostgreSQL/pgvector,
PostGIS, Redis và Dagster.

---

# Bản đồ thành phần

```text
HTTP client
    │
    ▼
FastAPI router: POST /ask
    │
    ├─ request filter
    ├─ IntentDetector (question + safe RequestContext)
    │    ├─ low confidence → clarification, no RAG workflow
    │    └─ validated IntentDetectionResult
    ▼
RAGAgent.process_chat_message_with_metadata(result)
    │
    ├─ same result in ChatMessageState
    ├─ document / location / standard route
    ├─ build_prompt receives full result and purpose
    ├─ LangGraph workflow
    ├─ ContextManager / KnowledgeRetriever
    ├─ ChatDBManager → PostgreSQL + pgvector/PostGIS
    ├─ Redis visitor state / rate limit
    └─ AIClient → Google, OpenAI hoặc OpenRouter
```

**Background:** Dagster nhận job enrichment khi nearby search thiếu dữ liệu.

---

# Walkthrough: `/ask`

1. Router chuẩn hóa/validate `visitor_id` và câu hỏi.
2. Áp dụng Redis rate limit trước khi gọi model để request bị chặn không tạo
   model cost.
3. `IntentDetector.detect_async()` gửi câu hỏi cùng context cần thiết
   (`channel`, `context`, `persona_id`) tới `AIClient`, yêu cầu JSON có schema.
   Visitor/tenant/touchpoint IDs không được đưa vào prompt phân loại.
4. Validate `IntentDetectionResult`: intent, `purpose`, secondary intents,
   model-estimated confidence, entities và `needs_clarification`. Result dưới
   ngưỡng 0.55 luôn yêu cầu clarification; confidence này là estimate của model,
   không phải probability đã được hiệu chuẩn bằng evaluation dataset.
5. Nếu cần clarification, trả lời yêu cầu làm rõ và không chạy graph,
   retrieval, geospatial query hoặc generation.
6. Nếu được phép xử lý, router kiểm tra nearby parameters khi intent rõ ràng là
   `location_chat` và resolve touchpoint.
7. Router truyền nguyên result vào `RAGAgent`; không
   phân loại lại intent.
8. Graph route document/location/standard. `build_prompt` nhận toàn bộ
   `IntentDetectionResult`; purpose được dùng trực tiếp thay vì heuristic thứ hai.
9. Router đóng gói JSON response, có thể kèm `enrichment_run_id`.

```python
@router.post("/ask", response_class=JSONResponse)
async def handle_chat(msg: Message):
    ...
```

---

<!-- _class: compact-table -->

# Những ranh giới cần giữ

| Ranh giới | Trách nhiệm |
|---|---|
| Router | HTTP contract, validation, status/error |
| RAGAgent | orchestration và routing workflow |
| AIClient | provider-neutral model/embedding adapter |
| ContextManager | summary, memory và context refresh |
| ChatDBManager | persistence, tenant/user scope, geo query |
| Dagster | discovery/enrichment chạy nền |

**Quy tắc:** sửa behavior ở lớp sở hữu contract, không “vá” cùng một logic
ở cả router và agent.

---

# Demo trên lớp

## Lần theo một câu hỏi

**Input:** `Tìm 3 quán cà phê gần tôi trong bán kính 1 km`

- Đặt breakpoint/log tại `handle_chat`.
- Quan sát `IntentDetector` và JSON `location_chat` entities.
- Xem `find_nearby_places` dùng `ST_DWithin`.
- Nếu thiếu kết quả, ghi nhận `enrichment_run_id`.
- Mở test tương ứng trước khi sửa code.

**Expected:** biết request đang ở nhánh nào và file nào sở hữu bước đó.

---

# Kiểm chứng

```bash
pytest tests/test_document_chat.py
pytest tests/test_nearby_places.py
```

Đọc assertion để trả lời:

- Document chat có đọc cached geolocation không?
- Câu hỏi nearby có cần tọa độ không?
- Khi thiếu dữ liệu, hệ thống trả partial result hay im lặng thất bại?

**Bằng chứng hoàn thành:** sequence diagram + danh sách file/test liên quan.

---

# Takeaways & bài tập

- Entry point hiện tại: [`main_app.py`](../../main_app.py)
- Chat router: [`leobot_router/leobot_main_router.py`](../../leobot_router/leobot_main_router.py)
- Orchestrator: [`leoai/rag_agent.py`](../../leoai/rag_agent.py)
- Test bắt đầu từ: [`tests/test_document_chat.py`](../../tests/test_document_chat.py)

**Bài tập:** chọn một endpoint khác, viết source map gồm input, node xử lý,
dependency, persistence và test.
