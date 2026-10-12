---
marp: true
theme: default
paginate: true
footer: "LEO Bot • Buổi 3"
---

<style>
section.dense {
  padding: 42px 64px;
  line-height: 1.1;
}

section.dense h1 {
  margin-bottom: 0.55em;
}

section.dense h2 {
  margin-top: 0.55em;
  margin-bottom: 0.25em;
}

section.dense p,
section.dense ul,
section.dense ol,
section.dense pre,
section.dense table {
  margin-top: 0.35em;
  margin-bottom: 0.35em;
}
</style>

# Buổi 3
## LLM Provider và Structured Output

**Năng lực:** không đưa output model vào business logic trước khi kiểm tra
schema, kích thước và lỗi provider.

---

<!-- _class: dense -->

# Provider abstraction trong repo

`leoai/ai_core.py` chọn provider từ environment:

```text
AI_PROVIDER = google | openai | openrouter
EMBEDDING_PROVIDER = google | openai | openrouter
```

- Chat: `AIClient`
- Embedding: `RemoteEmbeddingModel`
- Google dùng `google-genai`.
- OpenAI/OpenRouter dùng OpenAI-compatible client.
- Model ID và dimensions được cấu hình, không hard-code trong router.

---

<!-- _class: dense -->

# Chat model khác embedding model

| Thành phần | Đầu vào | Đầu ra | Dùng ở đâu |
|---|---|---|---|
| Chat/reasoning model | prompt + context | text/JSON | trả lời, classify, enrich |
| Embedding model | text | vector 768 chiều | retrieval, context search |

**Không trộn contract:** vector dùng cho `<=>`/`<#>`; text dùng cho prompt.

```python
embedding = model.encode(text, normalize_embeddings=True)
```

---

# Structured output là một contract

```python
text = client._generate_response(
    prompt,
    json_schema=WEATHER_FORECAST_SCHEMA,
)
```

`AIClient`:

- Google: `response_mime_type=application/json` + response schema.
- OpenAI-compatible: `response_format={"type": "json_object"}`.
- Ứng dụng vẫn phải parse, validate shape và kiểm tra domain invariant.

**JSON hợp lệ chưa chắc là dữ liệu hợp lệ.**

---

<!-- _class: dense -->

# Hai lớp validation

## Provider boundary

- provider được hỗ trợ;
- API key tồn tại;
- response không rỗng;
- schema được chuyển đổi đúng format.

## Application boundary

- vector đúng `(n, 768)`, finite, non-zero;
- category/radius/result limit hợp lệ;
- output không được biến thành “success” khi provider lỗi.

Lỗi phải được log/propagate theo contract, không fallback im lặng.

---

<!-- _class: dense -->

# Demo: response đúng và sai

**Case A:** JSON đúng schema nhưng `intent_confidence = 1.7`.

**Case B:** provider trả empty text hoặc thiếu field bắt buộc.

Quan sát:

1. `AIClient` trả gì?
2. helper nào validate tiếp?
3. test nào chứng minh failure không đi vào business logic?

Code anchors:
[`leoai/ai_core.py`](../../leoai/ai_core.py),
[`leoai/ai_data_schema.py`](../../leoai/ai_data_schema.py).

---

<!-- _class: dense -->

# Kiểm chứng embedding

```bash
pytest tests/test_ai_core.py
pytest tests/test_rag.py
```

Checklist:

- input rỗng có bị từ chối không?
- batch response có được sắp xếp theo `index` không?
- shape có đúng dimensions không?
- normalization có xử lý zero norm không?
- provider lỗi có bị che bởi chuỗi trả lời giả không?

---

<!-- _class: dense -->

# Core concept: adapter + output contract

Provider adapter che giấu khác biệt SDK, nhưng không được che giấu contract:

```text
application request
      │
      ▼
AIClient / RemoteEmbeddingModel
      │
      ▼
provider SDK
      │
      ▼
validated text, JSON hoặc vector
```

Tách **provider error**, **schema error** và **domain error** để biết phải
retry, báo lỗi hay dừng workflow.

---

# Example: cùng interface, nhiều provider

```python
client = AIClient(provider=AI_PROVIDER)
text = client.generate_content(prompt)
vector = get_embedding_model().encode(
    text,
    normalize_embeddings=True,
)
```

`AIClient` chọn Google, OpenAI hoặc OpenRouter; caller không cần biết SDK nào
đang chạy. Embedding adapter vẫn phải trả vector đúng dimensions.

---

# Vì sao abstraction này đúng?

- đổi provider không làm router và graph biết thêm SDK detail;
- structured output có một application boundary sau provider response;
- embedding shape/finite/non-zero được kiểm tra trước khi ghi pgvector;
- empty response và unsupported provider không biến thành success giả;
- test có thể inject client/model mà không gọi API thật.

Correctness nằm ở contract sau adapter, không chỉ ở việc SDK gọi thành công.

---

<!-- _class: dense -->

# Verify: provider output có thể chứng minh

```bash
pytest tests/test_ai_core.py
pytest tests/test_rag.py
```

Demo ba kết quả:

1. response hợp lệ theo schema;
2. JSON hợp lệ nhưng sai domain;
3. provider lỗi hoặc vector sai shape.

**Expected:** mỗi case có behavior khác nhau và không đưa dữ liệu invalid vào
business logic.

---

# Takeaways & bài tập

- Provider adapter: [`leoai/ai_core.py`](../../leoai/ai_core.py)
- Schema/domain: [`leoai/ai_data_schema.py`](../../leoai/ai_data_schema.py)
- Regression: [`tests/test_ai_core.py`](../../tests/test_ai_core.py)

**Bài tập:** viết một test cho provider error hoặc timeout, xác định rõ
expected exception/log và chứng minh dữ liệu không được chuyển tiếp.
