---
marp: true
theme: default
paginate: true
footer: "LEO Bot • Buổi 11"
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

# Buổi 11
## Persona và Context-aware Personalization

**Năng lực:** xây dựng quyết định cá nhân hóa dựa trên evidence và giới hạn
dữ liệu.

---

# Persona không phải nhãn cố định

Trong request/state hiện có:

- `persona_id`;
- `cdp_profile_id`;
- `user_profile` trong context summary;
- `intent_label` và `intent_confidence`;
- `tenant_id`, `user_id`, `touchpoint_id`.

Persona nên được xem là state có thời điểm và nguồn, không phải sự thật vĩnh
viễn về người dùng.

---

# Evidence trước inference

```text
observed:
  user hỏi "quán cà phê gần tôi"

retrieved:
  touchpoint coordinates + nearby places

inferred:
  có thể quan tâm coffee

decision:
  đề xuất place phù hợp với query hiện tại
```

Không biến inference thành profile fact nếu chưa có policy, provenance và
confidence phù hợp.

---

# Context contract trong prompt

`AgentOrchestrator` nhận:

- current question;
- `user_profile`;
- `user_context`;
- selected place và selected-place knowledge;
- conversation summary;
- target language và persona.

Current question có priority cao hơn context cũ; topic change và correction
phải thắng assumption từ summary.

---

# Context thiếu, cũ hoặc mâu thuẫn

| Tình huống | Hành vi an toàn |
|---|---|
| thiếu profile | trả lời theo evidence hiện có |
| context cũ | refresh hoặc nêu giới hạn |
| hai source conflict | nói rõ conflict |
| selected place chưa có | không tự chọn candidate |
| document mode | loại location state |

Consent/data retention là product policy cần xác định thêm; không nên giả định
đã được enforce chỉ vì có `cdp_profile_id`.

---

<!-- _class: dense -->

# Demo: hai bộ context

**Case A:** cùng câu hỏi, touchpoint có tọa độ và nearby places.

**Case B:** không có tọa độ hoặc context thuộc document chat.

So sánh:

1. route;
2. retrieved context;
3. prompt fields;
4. output claim;
5. persistence scope.

Code: [`leoai/rag_context_manager.py`](../../leoai/rag_context_manager.py),
[`leoai/rag_prompt_builder.py`](../../leoai/rag_prompt_builder.py).

---

# Kiểm chứng

```bash
pytest tests/test_conversation_context.py
pytest tests/test_document_chat.py
pytest tests/test_recommendation.py
```

Đọc test như policy:

- selection không cross-touchpoint;
- document chat không inherit location;
- profile/recommendation không bỏ qua input validation;
- tenant/user được truyền xuyên suốt.

---

# Takeaways & bài tập

- State/orchestration: [`leoai/rag_agent.py`](../../leoai/rag_agent.py)
- Profile state: [`leoai/rag_context_manager.py`](../../leoai/rag_context_manager.py)
- Personalization helper: [`leoai/leo_personalization.py`](../../leoai/leo_personalization.py)

**Bài tập:** viết hai test cho context thiếu và context mâu thuẫn; mỗi test
phải chỉ ra evidence được dùng và claim nào bị cấm.

---

# Core concept: personalization là constrained decision

Personalization không phải đoán người dùng rồi ghi đoán đó thành fact.

```text
observed evidence
  → scoped context
  → confidence/uncertainty
  → bounded recommendation
  → feedback hoặc correction
```

Persona là input có provenance và freshness, không phải quyền bỏ qua current
question hoặc security boundary.

---

# Example: cùng user, khác touchpoint

**Touchpoint A:** có tọa độ và nearby places.

**Touchpoint B:** document chat, không có location context.

Cùng câu hỏi “gợi ý cho tôi”, agent phải:

- dùng evidence của touchpoint đang active;
- không copy selected place từ A sang B;
- nêu giới hạn khi profile/context thiếu;
- cho phép câu hỏi mới override context cũ.

---

# Vì sao quyết định này đúng?

- observed data được phân biệt với inferred interest;
- `tenant_id`, `user_id`, `touchpoint_id` giữ scope;
- freshness/context refresh giảm personalization stale;
- conflict được nêu thay vì âm thầm chọn một source;
- current question có priority hơn persona assumption.

Consent và retention vẫn là product policy cần enforce riêng; không suy ra từ
việc request có `cdp_profile_id`.

---

# Verify: recommendation có evidence không?

```bash
pytest tests/test_conversation_context.py
pytest tests/test_document_chat.py
pytest tests/test_recommendation.py
```

Review output theo bốn câu:

1. quyết định dựa trên field nào?
2. field đó đến từ source nào?
3. confidence/uncertainty có được giữ không?
4. context khác hoặc missing context có làm thay đổi behavior an toàn không?
