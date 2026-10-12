---
marp: true
theme: default
paginate: true
footer: "LEO Bot • Buổi 5"
---

<style>
section.dense {
  padding: 30px 64px;
  line-height: 1.1;
}

section.dense pre {
  margin-top: 0.35em;
  margin-bottom: 0.35em;
}
</style>

# Buổi 5
## RAG: Retrieval và Grounding

**Năng lực:** kiểm tra câu trả lời có được hỗ trợ bởi evidence truy xuất hay
không.

---

<!-- _class: dense -->

# Pipeline RAG trong LEO Bot

```text
source URL/text
    │
    ▼
validate + fetch
    │
    ▼
chunk theo token + overlap
    │
    ▼
embedding 768 chiều
    │
    ▼
knowledge_sources + knowledge_chunks
    │
    ▼
query embedding → pgvector similarity
    │
    ▼
Source/URI/chunk đưa vào document prompt
```

---

# Ingestion contract

`KnowledgeCreator.upsert_text` kiểm tra:

- `visitor_id`, text, URI và name không rỗng;
- giới hạn kích thước tài liệu;
- overlap nhỏ hơn chunk size;
- embedding đúng 768 chiều, finite, non-zero;
- replace chunks trong một transaction.

`source_id` ổn định theo tenant, visitor, type và URI.

---

# Retrieval contract

`KnowledgeRetriever.retrieve`:

```sql
WHERE ks.tenant_id = $1
  AND ks.user_id = $2
  AND ks.status = 'active'
ORDER BY kc.embedding <=> $3::vector
LIMIT $4
```

Output giữ `Source:` và `URI:` để prompt có thể cite evidence.

**Không có row:** trả chuỗi rỗng; prompt phải nói rõ evidence hiện có không
đủ, không suy ra “toàn bộ collection không có đáp án”.

---

# Grounding không phải chỉ là top-k

Khi đọc output, hỏi bốn câu:

1. Chunk nào hỗ trợ claim?
2. Source/URI nào được giữ lại?
3. Có conflict hoặc gap không?
4. Câu trả lời có thêm kiến thức ngoài evidence mà không đánh dấu không?

`DOCUMENT_CHAT_INSTRUCTIONS` trong
[`leoai/rag_prompt_builder.py`](../../leoai/rag_prompt_builder.py) đặt các
quy tắc này vào prompt, nhưng test vẫn cần kiểm tra behavior.

---

# Demo lab

Chuẩn bị hai nguồn nhỏ:

- **Guide A:** có giờ mở cửa và địa chỉ.
- **Guide B:** có thông tin khác hoặc thiếu dữ kiện.

Chạy:

1. query có evidence;
2. query không có evidence;
3. query có hai nguồn conflict.

Quan sát retrieved chunks, source URI và câu trả lời cuối.

---

# Kiểm chứng

```bash
pytest tests/test_document_chat.py
pytest tests/test_rag.py
```

Expected:

- retrieval scope theo `tenant_id` + `user_id`;
- source/URI xuất hiện trong context;
- document chat không đọc nearby place state;
- empty retrieval không biến thành claim chắc chắn.

---

# Core concept: RAG là pipeline evidence

RAG không chỉ là “top-k similarity”:

1. **Ingest:** nhận source có identity và metadata.
2. **Chunk/embed:** chuyển nội dung thành các đơn vị truy xuất ổn định.
3. **Retrieve:** lọc scope rồi xếp hạng theo vector distance.
4. **Ground:** đưa chunk + source/URI vào prompt và giới hạn claim.

Retrieval và generation là hai contract khác nhau.

---

# Example: câu hỏi document

```text
question
  → embedding
  → knowledge_chunks của đúng tenant/user
  → Source + URI + content
  → DOCUMENT_CHAT_INSTRUCTIONS
  → answer có evidence hoặc nói rõ thiếu evidence
```

`KnowledgeRetriever.retrieve` không tự trả lời; nó trả context có provenance
cho prompt builder.

---

# Vì sao grounding này đúng?

- user/tenant filter ngăn lấy chunk của người khác;
- `status = 'active'` loại source không còn hiệu lực;
- source name/URI cho phép truy vết claim;
- empty retrieval tạo một giới hạn rõ ràng;
- prompt cấm biến document content thành instruction hoặc tự bịa citation.

Một câu trả lời “nghe đúng” nhưng không có chunk hỗ trợ vẫn là failure.

---

<!-- _class: dense -->

# Verify: từ chunk đến claim

```bash
pytest tests/test_document_chat.py
pytest tests/test_rag.py
```

Tạo một bảng kiểm:

| Bước | Bằng chứng |
|---|---|
| Query | câu hỏi và tenant/user |
| Retrieval | chunk, score/order, source URI |
| Prompt | excerpt được đưa vào |
| Answer | claim được hỗ trợ hoặc gap được nêu |

---

# Takeaways & bài tập

- Ingestion/retrieval: [`leoai/rag_knowledge_manager.py`](../../leoai/rag_knowledge_manager.py)
- Document route: [`leobot_router/leobot_knowledge_router.py`](../../leobot_router/leobot_knowledge_router.py)
- Prompt contract: [`leoai/rag_prompt_builder.py`](../../leoai/rag_prompt_builder.py)

**Bài tập:** tạo 5–10 câu hỏi đánh giá retrieval; ghi expected source,
evidence tối thiểu và behavior khi thiếu nguồn.
