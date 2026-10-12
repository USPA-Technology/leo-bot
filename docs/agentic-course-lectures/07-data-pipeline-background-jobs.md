---
marp: true
theme: default
paginate: true
footer: "LEO Bot • Buổi 7"
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

# Buổi 7
## Data Pipeline và Background Job

**Năng lực:** mô tả một tác vụ dữ liệu chạy, thất bại và chạy lại an toàn.

---

# Hai loại background flow

## Dagster data pipeline

Discovery và enrichment geo places, sau đó ghi `geo_places`,
`knowledge_sources`, `knowledge_chunks`.

## Redis profile worker

Producer `LPUSH` profile job vào Redis; worker đọc, gọi CDP client và ghi log
success/failure.

**Cùng là background job nhưng khác ownership, retry và observability.**

---

<!-- _class: dense -->

# Geo enrichment flow

```text
nearby query thiếu places
        │
        ▼
trigger_geo_places_enrichment()
        │ trả accepted run_id
        ▼
Dagster asset job
  process_places
  process_brave_search
  process_mass_schedule
  process_knowledge
        │
        ▼
PostgreSQL/PostGIS + pgvector
```

Chat response không chờ job hoàn thành; client poll/stream status bằng run ID.

---

# Retry và idempotency

Một job có thể thất bại sau khi đã ghi một phần dữ liệu. Thiết kế phải trả lời:

- asset nào đã commit?
- run lại có duplicate place/source/chunk không?
- record nào còn đủ điều kiện retry?
- lỗi provider có làm mất dữ liệu cũ không?

Pipeline trong repo dùng identity ổn định, upsert/delete có phạm vi và giữ lại
record cũ khi enrichment mới thất bại.

---

# Demo failure có kiểm soát

1. Chạy một scope nhỏ, tối đa 5 places.
2. Mô phỏng search/provider failure.
3. Xem Dagster run status và event log.
4. Chạy lại cùng scope.
5. So sánh số record trước/sau, đặc biệt `knowledge_chunks`.

**Expected:** failure hiển thị là failure; không báo thành công hình thức.

---

<!-- _class: dense -->

# Redis worker: contract khác

```python
await redis.lpush(queue_name, json.dumps(profile_dict))
```

Worker cần:

- payload là object hợp lệ;
- log enqueue/success/failure;
- xử lý exception không làm mất dấu job;
- test được bằng dependency injection, không cần service thật.

Code: [`leocdp/profile_queue.py`](../../leocdp/profile_queue.py),
[`leocdp/profile_worker.py`](../../leocdp/profile_worker.py).

---

# Kiểm chứng

```bash
pytest tests/test_dagster_pipelines.py
pytest tests/test_geo_places_pipeline.py
```

Checklist:

- run ID chỉ xuất hiện sau khi submit thành công;
- retry không nhân bản dữ liệu;
- một place lỗi không nhất thiết rollback toàn bộ place đã commit;
- status cuối có thể là `SUCCESS`, `FAILURE` hoặc `CANCELED`.

---

# Core concept: async job là một contract khác

Request đồng bộ cần latency thấp và response ngay.

Background job cần:

- accepted identifier;
- trạng thái có thể quan sát;
- retry/idempotency;
- commit boundary;
- failure không bị che.

Đưa việc nặng sang queue/Dagster không tự động làm nó reliable.

---

# Example: partial result + enrichment

```text
/ask
  → nearby_places
  → có một phần kết quả
  → queue Dagster
  → trả answer + run_id
  → SSE status
  → lần hỏi sau retrieve dữ liệu mới
```

Chat không chờ toàn bộ web search và enrichment hoàn tất.

---

# Vì sao pipeline này đúng?

- user nhận được partial answer thay vì timeout;
- `run_id` nối request với background execution;
- asset/upsert identity hạn chế duplicate;
- failure của provider vẫn nhìn thấy trong Dagster;
- knowledge chỉ được retrieve sau khi job đã ghi dữ liệu hợp lệ.

Đây là cách tách latency của interaction khỏi latency của enrichment.

---

<!-- _class: dense -->

# Verify: chạy lại có an toàn không?

```bash
pytest tests/test_dagster_pipelines.py
pytest tests/test_geo_places_pipeline.py
```

So sánh trước/sau khi retry:

1. run status;
2. số `geo_places`;
3. số `knowledge_sources/chunks`;
4. log của record lỗi.

Nếu số record tăng do duplicate thay vì upsert, idempotency contract chưa đúng.

---

# Takeaways & bài tập

- Pipeline: [`dags_pipelines/geo_places_pipeline.py`](../../dags_pipelines/geo_places_pipeline.py)
- Trigger: [`leoai/rag_agent_utils.py`](../../leoai/rag_agent_utils.py)
- Pipeline docs: [`dags_pipelines/README.md`](../../dags_pipelines/README.md)

**Bài tập:** viết runbook một trang cho một lỗi pipeline: triệu chứng, query
kiểm tra, điều kiện retry, cách xác nhận dữ liệu không bị trùng.
