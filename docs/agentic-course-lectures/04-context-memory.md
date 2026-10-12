---
marp: true
theme: default
paginate: true
footer: "LEO Bot • Buổi 4"
---

# Buổi 4
## Context Engineering và Memory

**Năng lực:** xác định context nào được đưa vào model và vì sao.

> Context là dữ liệu có phạm vi, thời điểm và nguồn; không phải “mọi thứ từng
> nói với bot”.

---

# Bốn nguồn context

| Nguồn | Ví dụ trong LEO Bot | Vai trò |
|---|---|---|
| Conversation history | `chat_messages` | continuity |
| Retrieved evidence | semantic matches | hỗ trợ claim |
| Tool/data result | nearby places | state tạm thời |
| Persistent memory | `conversational_context` | summary/profile |

`touchpoint_id` và `tenant_id` là boundary, không phải metadata trang trí.

---

# ContextManager refresh loop

```text
load saved summary
      │
      ├─ fresh? ───────────────► preserve summary
      │
      └─ stale/missing
          ├─ embed current question
          ├─ load recent turns + semantic matches
          ├─ summarize thành JSON
          └─ persist summary nếu hợp lệ
```

Repo đặt `DELTA_TO_REFRESH_CONTEXT = 10s` cho refresh decision.

---

# State location phải có phạm vi

Location keys gồm:

```text
selected_place
place_choices
selected_place_knowledge
nearby_places
latitude / longitude
```

Document chat gọi `build_context_summary(..., include_location=False)`.

**Mục tiêu:** câu hỏi tài liệu không bị cached geolocation làm lệch prompt.

---

# Evidence khác inference

Summary prompt có:

- `user_profile`;
- `context_summary`;
- `context_keywords`;
- `intent_label`;
- `intent_confidence`.

Nhưng summary do model tạo vẫn là dữ liệu cần kiểm tra. Khi JSON sai hoặc
thiếu `user_context`, `ContextManager` giữ context cũ và log warning.

---

# Demo: context cũ và context sai phạm vi

1. Gửi nearby query để có `selected_place`.
2. Gửi document query ở context `agent` + `personal_assistant`.
3. Kiểm tra prompt không chứa selected place/location.
4. Sửa timestamp để ép refresh.
5. Quan sát recent turns và semantic matches được gộp, deduplicate theo hash.

Code: [`leoai/rag_context_manager.py`](../../leoai/rag_context_manager.py).

---

# Kiểm chứng

```bash
pytest tests/test_conversation_context.py
pytest tests/test_document_chat.py
```

Các assertion quan trọng:

- touchpoint khác không thừa hưởng selection;
- document mode không đọc location;
- context summary được persist đúng tenant/user/touchpoint;
- retrieval history không vượt scope conversation.

---

# Core concept: context là evidence có scope

Context tốt phải có:

- **source:** lấy từ message, retrieval, touchpoint hay profile;
- **scope:** tenant, user, touchpoint và mode;
- **freshness:** timestamp/TTL và refresh rule;
- **provenance:** biết đâu là observed fact, đâu là model summary;
- **policy:** field nào được phép vào prompt.

Memory không phải là “ném toàn bộ lịch sử vào model”.

---

# Example: document mode loại location

```python
await context.build_context_summary(
    user_id,
    DOCUMENT_CHAT_TOUCHPOINT_ID,
    profile_id,
    question,
    include_location=False,
)
```

Trong `AgentOrchestrator.build_document_prompt`, các field như
`selected_place`, `nearby_places`, `latitude` và `longitude` tiếp tục bị lọc.

---

# Vì sao cách này đúng?

- history giúp continuity nhưng không được vượt user/touchpoint scope;
- refresh khi stale giúp giảm context cũ;
- location state không làm lệch document Q&A;
- summary lỗi thì giữ context đã lưu thay vì ghi dữ liệu hỏng;
- current question vẫn có priority cao hơn assumption từ memory.

Đây là memory có policy và boundary, không phải persistence mù.

---

# Verify: context trước khi prompt

```bash
pytest tests/test_conversation_context.py
pytest tests/test_document_chat.py
```

In hoặc assert ba artifact:

1. saved summary;
2. `user_context` sau khi áp dụng scope;
3. prompt cuối đưa vào model.

Nếu document prompt chứa selected place từ geo session, context contract đã
bị phá vỡ dù câu trả lời nghe hợp lý.

---

# Takeaways & bài tập

- Memory owner: [`leoai/rag_context_manager.py`](../../leoai/rag_context_manager.py)
- Persistence owner: [`leoai/rag_db_manager.py`](../../leoai/rag_db_manager.py)
- Test: [`tests/test_conversation_context.py`](../../tests/test_conversation_context.py)

**Bài tập:** viết một context policy cho use case mới: nguồn nào được phép
dùng, TTL bao nhiêu, thiếu evidence thì trả lời thế nào.
