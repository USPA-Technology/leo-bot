---
marp: true
theme: default
paginate: true
footer: "LEO Bot • Buổi 12"
---

<style>
section.dense {
  padding: 42px 64px;
  line-height: 1.1;
}

section.dense pre,
section.dense ol {
  margin-top: 0.35em;
  margin-bottom: 0.35em;
}
</style>

# Buổi 12
## Capstone Review: Từ Code đến Bàn giao

**Năng lực:** trình bày, demo và kiểm chứng một AI feature có phạm vi rõ ràng.

> Capstone tốt không chỉ có câu trả lời đẹp; nó có contract, test, evidence,
> failure path và hướng dẫn chạy lại.

---

# Acceptance criteria

Feature phải trả lời được:

- input/API contract là gì?
- route/workflow nào xử lý?
- model/provider nào được gọi?
- context/retrieval nào được phép dùng?
- data nào được persist, theo tenant/user nào?
- failure path và timeout ra sao?
- test nào chứng minh expected behavior?

---

# Demo flow 15 phút

```text
problem statement
    ▼
architecture + boundary
    ▼
happy-path demo
    ▼
test/evaluation output
    ▼
one controlled failure
    ▼
trade-off + next step
```

Chuẩn bị code nền, fixture, dữ liệu mẫu và command trước giờ học.

---

# Một capstone bám repo

Ví dụ: **nearby-place answer có grounded enrichment**

1. `POST /ask` nhận query + location.
2. `RAGAgent` route nearby search.
3. PostGIS trả places hiện có.
4. Nếu thiếu, Dagster trả `run_id`.
5. SSE stream status.
6. Knowledge chunks được retrieve ở lần hỏi sau.
7. Test location, tenant, partial result, failure.

---

# Evidence package

Nộp cùng feature:

- source map và sequence diagram;
- danh sách file thay đổi;
- API example/request-response;
- test command + output;
- retrieved source/URI hoặc fixture;
- log/run ID của background job;
- known limitations và rollback/retry note.

**Không commit secret hoặc credential thật vào slide, fixture hay README.**

---

# Review theo rubric khóa học

| Hạng mục | Trọng số |
|---|---:|
| Hiểu codebase/kiến trúc | 20% |
| Thay đổi đúng yêu cầu | 25% |
| Test/kiểm chứng | 20% |
| Security/xử lý lỗi | 15% |
| Code/design decision | 10% |
| Tài liệu/bàn giao | 10% |

Điểm không dựa trên việc model tạo câu trả lời nghe hợp lý.

---

# Kiểm chứng thực hành

```bash
pytest tests/test_document_chat.py
pytest tests/test_conversation_context.py
pytest tests/test_nearby_places.py
pytest tests/test_geo_places_pipeline.py
```

Chọn selector nhỏ đúng feature trước; chỉ chạy full suite khi targeted tests
đã cho tín hiệu cần mở rộng.

---

# Final review questions

- Có phân biệt code hiện tại và phần đề xuất không?
- Có test cho happy path, invalid input và provider/job failure không?
- Có giữ tenant/user/touchpoint boundary không?
- Có expected output tái lập được không?
- Người khác clone repo có biết chạy, quan sát và debug không?

---

# Kết thúc khóa học

Sau 12 buổi, học viên cần có thể:

- lần theo request trong LEO Bot;
- thực hiện một thay đổi nhỏ có kiểm soát;
- cập nhật test cho behavior quan trọng;
- nhận diện rủi ro context, tool, data và security;
- bàn giao feature bằng evidence, limitation và runbook.

**Bài tập cuối:** hoàn thiện README, known limitations và hướng dẫn chạy lại
capstone từ một môi trường sạch.

---

# Core concept: capstone là vertical slice

Một capstone agentic không chỉ là prompt + screenshot. Nó phải đi xuyên qua
vertical slice:

```text
API → orchestration → state/context → model/retrieval
    → action/persistence → test → observable evidence
```

Acceptance criteria phải đo behavior, boundary và failure path.

---

# Example: nearby enrichment feature

**Goal:** trả nearby places hiện có và queue enrichment khi thiếu.

1. router validate request/location;
2. `RAGAgent` chọn nearby branch;
3. PostGIS trả partial result;
4. Dagster nhận bounded job và trả run ID;
5. SSE stream status;
6. lần hỏi sau lấy knowledge chunks đã enrich.

Đây là một vertical slice có user value và side effect rõ ràng.

---

# Vì sao capstone được xem là đúng?

- contract được kiểm tra ở từng boundary;
- happy path và failure path đều có expected behavior;
- evidence nối được response với DB, job và source;
- security scope không bị bỏ qua để demo nhanh;
- người khác có thể chạy lại bằng command và fixture.

Feature chỉ “hoạt động” khi behavior có thể tái lập và bàn giao.

---

<!-- _class: dense -->

# Verify: review evidence package

```bash
pytest tests/test_document_chat.py
pytest tests/test_conversation_context.py
pytest tests/test_nearby_places.py
pytest tests/test_geo_places_pipeline.py
```

Reviewer cần giữ lại:

1. request/response;
2. state/route trace;
3. test output;
4. source hoặc retrieved evidence;
5. log/run ID;
6. known limitation và rollback note.
