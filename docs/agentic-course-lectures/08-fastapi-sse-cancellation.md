---
marp: true
theme: default
paginate: true
footer: "LEO Bot • Buổi 8"
---

# Buổi 8
## FastAPI, SSE và Cancellation

**Năng lực:** hiểu vòng đời request streaming và các trạng thái kết thúc.

> Trong repo hiện tại, SSE dùng để stream trạng thái Dagster enrichment; endpoint
> chat `/ask` vẫn trả JSON response.

---

# API contract hiện có

```text
POST /ask
  └─ JSON: question, visitor_id, context, location...
  └─ JSON: answer, touchpoint_id, optional enrichment_run_id

GET /_leoai/geo-places/enrichment/{run_id}/events
  └─ text/event-stream
  └─ Dagster status changes
```

Đừng gọi `/ask` là token streaming nếu chưa có generator model output.

---

# SSE frame

```text
retry: 5000

data: {"run_id":"...", "status":"STARTED"}

: keep-alive

data: {"run_id":"...", "status":"SUCCESS"}
```

- `data:` là event mặc định;
- `event: status_error` báo lỗi đọc status;
- comment `: keep-alive` giữ connection;
- terminal status kết thúc generator.

---

# Server lifecycle

```python
async def status_events():
    last_status = None
    yield "retry: 5000\n\n"
    while True:
        status = await asyncio.to_thread(
            get_geo_places_enrichment_status, run_id
        )
        ...
        if status in TERMINAL_DAGSTER_STATUSES:
            return
        await asyncio.sleep(ENRICHMENT_STATUS_POLL_SECONDS)
```

Blocking GraphQL call được đẩy ra thread, không chặn event loop.

---

# Disconnect và cleanup

Client có thể đóng connection giữa hai lần poll. Khi mở rộng generator:

- bắt `asyncio.CancelledError` ở boundary phù hợp;
- không nuốt exception ngoài ý muốn;
- dừng polling và giải phóng resource;
- không hủy Dagster run chỉ vì client disconnect nếu contract không yêu cầu;
- log `run_id` để trace.

**Cancellation của client và cancellation của job là hai khái niệm khác nhau.**

---

# Demo

1. Submit nearby search thiếu dữ liệu.
2. Mở EventSource tới `enrichment_status_url`.
3. Quan sát status thay đổi và keep-alive.
4. Đóng tab giữa chừng.
5. Kiểm tra server không giữ polling vô hạn.

Frontend client tham khảo:
[`resources/js/leocdp.chatbot.js`](../../resources/js/leocdp.chatbot.js).

---

# Error semantics

| Tình huống | Kết quả nên thấy |
|---|---|
| run đang chạy | status events + keep-alive |
| Dagster `SUCCESS` | event cuối rồi stream đóng |
| Dagster `FAILURE` | event failure rồi stream đóng |
| GraphQL client error | `status_error`, log exception, stream đóng |
| run ID không hợp lệ | lỗi phải nhìn thấy, không fake success |

---

# Kiểm chứng & bài tập

```bash
pytest tests/test_geo_places_pipeline.py
pytest tests/test_document_chat.py
```

Code anchors:
[`leobot_router/leobot_main_router.py`](../../leobot_router/leobot_main_router.py),
[`leoai/rag_agent_utils.py`](../../leoai/rag_agent_utils.py).

**Bài tập:** thêm test cho terminal failure hoặc client disconnect; ghi rõ
resource nào phải được cleanup và job có bị hủy hay không.

---

# Core concept: request và event stream khác nhau

- **HTTP request:** nhận input, xử lý và trả response.
- **SSE stream:** giữ một HTTP connection để gửi các event theo thời gian.
- **Job status:** trạng thái của Dagster run, không phải trạng thái của browser.
- **Cancellation:** client ngừng nhận stream; không mặc định hủy background job.

Một stream tốt có event format, keep-alive, terminal state và error semantics.

---

# Example: status event lifecycle

```text
submit job
  → accepted run_id
  → EventSource connects
  → STARTED / RUNNING
  → keep-alive while polling
  → SUCCESS | FAILURE | CANCELED
  → generator returns
```

Router dùng `StreamingResponse(..., media_type="text/event-stream")` và poll
Dagster ngoài event loop bằng `asyncio.to_thread`.

---

# Vì sao thiết kế này đúng?

- client nhận được trạng thái mà không phải refresh toàn trang;
- keep-alive giúp proxy/browser biết connection còn sống;
- chỉ status thay đổi mới tạo data event, giảm noise;
- terminal status đóng stream, tránh polling vô hạn;
- GraphQL error phát ra `status_error` và được log.

Không nên giả định `/ask` đang stream token khi contract hiện tại trả JSON.

---

# Verify: event và cancellation

```bash
pytest tests/test_geo_places_pipeline.py
pytest tests/test_document_chat.py
```

Kiểm tra bằng browser/client:

1. nhận event đầu tiên;
2. nhận keep-alive;
3. nhận terminal event;
4. đóng client giữa chừng;
5. xác nhận server cleanup mà không fake `SUCCESS`.
