---
marp: true
theme: default
paginate: true
footer: "LEO Bot • Buổi 6"
---

<style>
section.dense {
  padding: 42px 64px;
  line-height: 1.1;
}

section.dense pre {
  margin-top: 0.35em;
  margin-bottom: 0.35em;
}
</style>

# Buổi 6
## Tool Calling và MCP

**Năng lực:** thiết kế tool interface có input contract và kiểm soát quyền
thực thi.

> Model có thể đề xuất hành động; application mới là nơi validate và thực thi.

---

# Phạm vi thực tế của repo

LEO Bot hiện có các **tool-like application boundary**:

- `KnowledgeCreator.upsert_url/upsert_text` cho knowledge ingestion;
- `trigger_geo_places_enrichment` gửi job sang Dagster;
- `ChatDBManager.find_nearby_places` thực thi geo query;
- `AIClient` tạo structured output cho intent/category.

**Repo chưa có MCP server hoặc native model tool registry.** Buổi này dùng
contract hiện có để thiết kế boundary, không gọi một API MCP không tồn tại.

---

# Một tool contract tốt

```text
name: geo_places_enrichment
input:
  name: non-empty category
  latitude: -90..90
  longitude: -180..180
  radius: positive metric value
  count: integer 1..5
output:
  accepted run_id
errors:
  invalid input / unavailable location / submission failure
```

Contract phải nói rõ auth, timeout, idempotency và side effect.

---

# Model decision ≠ execution

```text
user request
  │
  ▼
intent/schema validation
  │
  ├─ no tool needed ─► answer
  │
  └─ tool requested
       ├─ authorization + tenant scope
       ├─ validate input
       ├─ execute application function
       └─ return evidence/run_id to model or user
```

Không gửi raw model arguments thẳng xuống database.

---

# MCP: khi nào cân nhắc?

MCP hữu ích khi cần một protocol chuẩn để expose nhiều capability cho nhiều
client/agent. Nhưng với LEO Bot:

- boundary hiện tại đang là Python function + FastAPI/Dagster;
- authorization và tenant scope đã nằm trong application;
- thêm MCP server là thay đổi kiến trúc, không phải refactor tên hàm.

**Decision rule:** chỉ thêm MCP khi có consumer/protocol requirement cụ thể.

---

# Demo: ingestion boundary

Theo dõi `POST` knowledge route:

1. bearer token được kiểm tra bởi `require_data_enrichment_key`;
2. URL phải là public HTTP(S), không credentials/private network;
3. nội dung được chunk/embed/transactional upsert;
4. lỗi `KnowledgeInputError` hoặc `KnowledgeFetchError` phải nhìn thấy.

Code anchors:
[`leobot_router/leobot_knowledge_router.py`](../../leobot_router/leobot_knowledge_router.py),
[`leoai/rag_knowledge_manager.py`](../../leoai/rag_knowledge_manager.py).

---

<!-- _class: dense -->

# Kiểm chứng tool contract

```bash
pytest tests/test_knowledge_creator.py
pytest tests/test_geo_places_pipeline.py
pytest tests/test_nearby_places.py
```

Case tối thiểu:

- URL private/redirect không hợp lệ;
- embedding sai dimensions;
- count > 5 bị giới hạn;
- Dagster submission fail không được báo “queued”;
- visitor/tenant không sở hữu dữ liệu bị từ chối.

---

# Core concept: decision không phải execution

Một agentic application cần tách:

```text
model/application decision
  → schema validation
  → authorization + tenant scope
  → application function
  → evidence hoặc run_id
```

Model có thể đề xuất tool; chỉ application mới được tạo side effect.

---

# Example: geo enrichment tool boundary

`trigger_geo_places_enrichment` nhận category, tọa độ, radius và count.

- input được giới hạn trước khi gửi;
- Dagster trả accepted `run_id`;
- chat response giữ partial places nếu đã có;
- client theo dõi trạng thái ở endpoint SSE riêng.

Đây là application action có contract, không phải model tự chạy database.

---

# Vì sao contract này đúng?

- auth nằm trước ingestion/action;
- input lỗi bị reject thay vì gửi raw arguments;
- count bị cap để giới hạn chi phí và phạm vi;
- submission failure không tạo success-shaped response;
- run ID tạo provenance cho side effect bất đồng bộ.

Nếu sau này thêm MCP, các invariant này vẫn phải nằm ở server/application
boundary, không được giao cho prompt.

---

# Verify: contract và failure evidence

```bash
pytest tests/test_knowledge_creator.py
pytest tests/test_geo_places_pipeline.py
pytest tests/test_nearby_places.py
```

Mỗi test cần trả lời: ai được phép gọi, input nào hợp lệ, side effect nào
được tạo và bằng chứng nào chứng minh action đã accepted.

---

# Takeaways & bài tập

- Auth boundary: [`main_config.py`](../../main_config.py)
- Enrichment trigger: [`leoai/rag_agent_utils.py`](../../leoai/rag_agent_utils.py)
- Background tool: [`dags_pipelines/geo_places_pipeline.py`](../../dags_pipelines/geo_places_pipeline.py)

**Bài tập:** viết tool contract cho một capability mới, kèm input schema,
authorization check, timeout, failure path và test list. Không cần triển khai
MCP server.
