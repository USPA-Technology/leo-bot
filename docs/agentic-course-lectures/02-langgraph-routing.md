---
marp: true
theme: default
paginate: true
footer: "LEO Bot • Buổi 2"
---

# Buổi 2
## LangGraph: State và Routing

**Năng lực:** giải thích được vì sao một input đi vào một nhánh cụ thể.

> Graph làm cho control flow có tên, có state và có điểm kiểm chứng.

---

# State của một message

`ChatMessageState` trong `leoai/rag_agent.py` mang:

- identity: `user_id`, `tenant_id`, `cdp_profile_id`
- input: `user_message`, `context`, `persona_id`
- intent: `primary_intent`, full `intent_result` (purpose, confidence, entities)
- location: tọa độ, touchpoint, radius
- retrieval: `terms`, `matching_places`, `summarized_context`
- decision: `selected_place`, `prompt_router`
- output: `response`, `enrichment_run_id_sink`

**Nguyên tắc:** node đọc state, trả phần state thay đổi; không tạo một
“global conversation state” ngoài contract này.

---

# Graph thực tế

Intent được phát hiện **trước** khi LangGraph chạy. Nếu
`needs_clarification=True`, RAG trả câu hỏi làm rõ và graph không chạy.

```text
IntentDetector (AIClient JSON)
 ├─ needs clarification ─────────────────────────► clarification response
 └─ accepted result → START
 ├─ document_chat ───────────────────────────────► END
 └─ validate_input
     ├─ nearby_places ─► enrich_geo_places ─► save_nearby_exchange ─► END
     │                 └► save_nearby_exchange ─────────────────────► END
     └─ prepare_touchpoint ─► save_user_message ─► build_context
          ├─ place_picker ─────────────────────────────────────────► END
          ├─ place_selection ──────────────────────────────────────► END
          └─ build_prompt ─► generate_answer ─► save_answer ───────► END
```

---

# Conditional routing

```python
workflow.add_conditional_edges(
    START,
    self._route_chat_type,
    {"document_chat": "document_chat",
     "standard_chat": "validate_input"},
)
```

- `IntentDetector` trong `leoai/ai_intent_detection.py` phân loại
  bằng `AIClient` và JSON schema, trả về `primary_intent`, `purpose`,
  model-estimated confidence, entities và clarification state trước khi graph
  chạy. Confidence dưới 0.55 bị đánh dấu cần clarification; đây chưa phải
  probability được hiệu chuẩn bằng labeled evaluation set.
  `RequestContext.channel` mô tả transport và không được dùng như intent.
- Router truyền cùng một `IntentDetectionResult` qua RAG; không chạy lại intent
  detector.
- Web route rate-limits sau validation nhẹ và trước `IntentDetector`, ngăn
  request bị throttle tiêu tốn model call.
- `location_chat` dùng `search_terms`, `place_type` và `search_name` trong
  `entities`; không chạy thêm nearby-intent classifier để lật lại quyết định
  location. Với legacy caller thiếu entities, fallback chỉ trích xuất terms
  nhưng vẫn giữ intent location. Nearby parser chỉ xử lý tham số radius/count.
- `build_context` quyết định picker, selection hay generate answer.
- `purpose` được truyền nguyên vẹn vào `build_prompt`, không chạy một bộ
  keyword classifier thứ hai.
- Câu hỏi phân loại chỉ nhận channel/context/persona cần thiết; visitor, tenant
  và touchpoint IDs không gửi tới model intent.

**Đừng suy luận route từ tên node; đọc hàm `_route_*` và test.**

---

# Demo: cùng một graph, ba input

| Input | Nhánh mong đợi | Điều cần quan sát |
|---|---|---|
| `Tóm tắt tài liệu này` | document chat | không đọc location |
| `Quán mì gần tôi` | nearby places | radius + PostGIS |
| `Giờ mở cửa của chỗ đó` | standard chat | selected place + prompt |

Test thêm:

- nearby nhưng không có tọa độ;
- intent confidence thấp: trả clarification và không truy cập retrieval/DB;
- structured location entities phải được dùng nguyên trạng, không phân loại lại;
- chọn `4` khi chỉ có 3 choices;
- input có một tọa độ nhưng thiếu tọa độ còn lại.

---

# Failure path và invariant

- `latitude` và `longitude` phải đi cùng nhau.
- Missing location không phải là “empty result”.
- `selected_place` chỉ xuất hiện sau selection hợp lệ.
- `nearby_places` là candidate list, không tự động là selected place.
- Enrichment chỉ được báo queued khi Dagster trả run ID.

Các invariant này nằm trong node/router, không nên chỉ kiểm tra bằng prompt.

---

# Kiểm chứng

```bash
pytest tests/test_document_chat.py
pytest tests/test_conversation_context.py
pytest tests/test_nearby_places.py
```

Học viên ghi lại cho mỗi test:

1. state input;
2. route được chọn;
3. side effect được phép;
4. side effect phải bị chặn.

---

# Core concept: graph là state machine

- **State:** dữ liệu dùng chung giữa các bước của một request.
- **Node:** một transformation hoặc side effect có tên.
- **Edge:** luật chuyển bước.
- **Conditional edge:** quyết định route dựa trên state hiện tại.
- **END:** termination rõ ràng, không chạy tiếp ngoài contract.

LangGraph biến control flow ngầm trong code thành graph có thể trace và test.

---

# Example: một input đi qua graph

**Input:** `Quán mì gần tôi`

```text
START
 → validate_input
 → nearby_places
 → enrich_geo_places (nếu thiếu places)
 → save_nearby_exchange
 → END
```

**Input document chat** đi thẳng qua `document_chat` và không đi vào geo path.

---

# Vì sao route này đúng?

- `primary_intent` tách document chat khỏi location state.
- `is_nearby_search` chỉ dẫn tới geo query sau validation.
- thiếu location trả lời yêu cầu chia sẻ vị trí, không giả làm empty result.
- `matching_places` thiếu so với `result_limit` mới được queue enrichment.
- mỗi side effect nằm ở node cụ thể nên có thể assert và mock độc lập.

Đây là agentic routing có giới hạn: model có thể giúp classify, nhưng invariant
cuối cùng vẫn do application kiểm soát.

---

# Verify: state, route và evidence

```bash
pytest tests/test_document_chat.py
pytest tests/test_conversation_context.py
pytest tests/test_nearby_places.py
```

Với mỗi case, ghi lại:

1. state đầu vào;
2. conditional edge đã chọn;
3. node tạo side effect;
4. output hoặc error chứng minh route đúng.

---

# Takeaways & bài tập

- Graph builder: [`leoai/rag_agent.py`](../../leoai/rag_agent.py)
- Prompt/routing contract: [`leoai/rag_prompt_builder.py`](../../leoai/rag_prompt_builder.py)
- Regression examples: [`tests/test_document_chat.py`](../../tests/test_document_chat.py)

**Bài tập:** thêm một test cho failure path của một route hiện có; chưa cần
thêm node mới.
