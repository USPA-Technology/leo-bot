# Agentic Software Development

## Course agenda based on the LEO Bot codebase

- **Hình thức:** Học theo yêu cầu (on-demand)
- **Thời lượng:** 12 buổi × 60 phút
- **Đối tượng:** Kỹ sư phần mềm, backend engineers và giảng viên muốn dùng một
codebase thực tế để học cách thiết kế, xây dựng, kiểm thử và vận hành một
agentic application.

## Định hướng khóa học

Khóa học dùng LEO Bot làm hệ thống xuyên suốt. Học viên đọc, chạy và mở rộng
chính các thành phần đã có trong repository:

- FastAPI application và các router cho website, knowledge ingestion,
  Facebook Messenger, Zalo OA và admin.
- `RAGAgent` với workflow được xây bằng `langgraph.StateGraph`.
- `AIClient` và `RemoteEmbeddingModel` cho Google, OpenAI và OpenRouter.
- Context, conversation state, visitor state và rate limiting với Redis.
- PostgreSQL 18 với pgvector, PostGIS và pg_trgm.
- Knowledge ingestion, chunking, embeddings và tenant-scoped retrieval.
- Nearby-place search, grounded web search và place enrichment.
- Dagster assets/jobs cho geo-place enrichment và ArangoDB → PostgreSQL ETL.
- Jinja2 templates, browser geolocation và JavaScript client trong `resources/`.

Nội dung chỉ mô tả những framework, database, backend service, pipeline và
knowledge flow đang có trong mã nguồn hoặc dependency manifest của repository.
Mỗi buổi đều nối một khái niệm agentic với một file, API, database table hoặc
test có thể kiểm tra được.

## Thông tin học tập

### Mục tiêu đầu ra

Sau khóa học, học viên có thể:

1. Trace được request từ FastAPI endpoint qua router, `RAGAgent`, AI provider,
   database và Redis.
2. Giải thích và thay đổi một state graph có routing, validation, context,
   generation và persistence.
3. Cấu hình provider chat/reasoning/embedding mà không khóa application vào
   một nhà cung cấp duy nhất.
4. Xây một knowledge flow có source, chunk, embedding, metadata và
   tenant/visitor filtering.
5. Thêm một backend capability có kiểm soát vào workflow hiện có, chẳng hạn
   document chat, geolocation touchpoint hoặc nearby-place enrichment.
6. Viết regression tests cho input validation, retrieval, context, API và
   pipeline behavior.
7. Nhận diện các failure mode thực tế: thiếu credential, dữ liệu không đủ,
   location không hợp lệ, source URL không an toàn, provider failure, database
   failure và pipeline failure.

### Cách học

- **50–60 phút:** đọc kiến trúc, trace code và phân tích trade-off.
- **60–70 phút:** lab trên repository, test một vertical slice và review
  failure cases.
- Mỗi buổi cập nhật cùng một sản phẩm: LEO Bot location-aware assistant và
  document-chat workflow.

### Learning journey

**Understand → Model State → Route → Ground → Persist → Integrate → Enrich →
Secure → Test → Deliver**

## Lộ trình 12 buổi

### Buổi 1 — LEO Bot architecture và agentic software development

**Thời lượng:** 60 phút  
**Theory**

- Agentic software khác gì so với một hàm gọi model một lần.
- Phân biệt application layer, orchestration layer, AI integration, state,
  knowledge và infrastructure trong LEO Bot.
- Trace `create_app()` từ [main_app.py](../../main_app.py) qua các router và
  `leobot_lifespan`.
- Đọc cấu hình runtime trong [main_config.py](../../main_config.py),
  [pyproject.toml](../../pyproject.toml) và [requirements.txt](../../requirements.txt).
- Xác định boundary giữa website chat, document chat, nearby-place search,
  Facebook Messenger và Zalo OA.

**Lab**

- Chạy health endpoints và đọc API table trong [README.md](../../README.md).
- Vẽ request/data-flow diagram cho `POST /_leoai/ask`.
- Chỉ ra nơi request validation, AI generation, PostgreSQL access, Redis access
  và background enrichment xảy ra.

**Kết quả:** một architecture map có file và symbol cụ thể, không dựa trên
component giả định ngoài repository.

### Buổi 2 — LangGraph workflow và agent loop

**Thời lượng:** 60 phút  
**Theory**

- State graph là cách biến một conversation flow thành một hệ thống có trạng
  thái và điều kiện.
- Đọc `ChatMessageState`, `START`, `END`, nodes và conditional edges trong
  [leoai/rag_agent.py](../../leoai/rag_agent.py).
- Routing thực tế của LEO Bot:
  `document_chat` hoặc `standard_chat`; từ standard chat tiếp tục tới
  validation, nearby search hoặc conversation workflow.
- Các node chính: `prepare_touchpoint`, `save_user_message`,
  `build_context`, `place_picker`, `place_selection`, `build_prompt`,
  `generate_answer` và `save_answer`.
- Vì sao graph phải tách orchestration khỏi provider, database và prompt
  implementation.

**Lab**

- Chạy một document-chat request và một standard-chat request.
- Thêm hoặc sửa một conditional branch nhỏ, giữ nguyên state contract.
- Viết test cho route khi thiếu một trong hai tọa độ latitude/longitude và
  khi nearby search không có location.

**Kết quả:** hiểu agent loop của codebase là một workflow có state, route,
side effect và điểm kết thúc rõ ràng.

### Buổi 3 — AI provider abstraction và embeddings

**Thời lượng:** 60 phút  
**Theory**

- Provider-neutral interface trong [leoai/ai_core.py](../../leoai/ai_core.py).
- `AIClient`, `GeminiClient`, `generate_content()` và structured JSON output.
- Ba provider đã được cấu hình: `google`, `openai` và `openrouter`.
- Phân biệt chat model, reasoning model, embedding model và touchpoint
  embedding model.
- Batch encoding, normalized vectors, dimension validation và error
  propagation.
- Vì sao configuration phải nằm ở environment variables thay vì hard-code
  trong workflow.

**Lab**

- Đọc provider/model selection từ `AI_PROVIDER`, `AI_CHAT_MODEL`,
  `AI_REASONING_MODEL`, `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL` và
  `EMBEDDING_DIMENSIONS`.
- Dùng fake embedding/client trong tests để kiểm tra workflow mà không gọi
  hosted API.
- Viết test cho provider không được hỗ trợ, missing API key và vector sai
  dimension.

**Kết quả:** có thể thay đổi provider hoặc model mà không sửa các node
orchestration và retrieval contract.

### Buổi 4 — Context engineering, memory và visitor state

**Thời lượng:** 60 phút  
**Theory**

- Context của agent gồm current request, conversation messages, summary,
  profile, selected place và location facts.
- `ContextManager` trong
  [leoai/rag_context_manager.py](../../leoai/rag_context_manager.py): refresh
  interval, recent turns, semantic matches và summary persistence.
- `AgentOrchestrator` trong
  [leoai/rag_prompt_builder.py](../../leoai/rag_prompt_builder.py): current
  question priority, selected-place continuity và evidence boundaries.
- Redis visitor state: name, touchpoint, profile/session data và sorted-set
  rate limiting.
- Database conversation state: `chat_messages`, `chat_message_embeddings` và
  `conversational_context`.

**Lab**

- Trace một follow-up về selected place qua saved state và prompt construction.
- Kiểm tra document chat không sử dụng cached location hoặc nearby-place menu.
- Thiết kế test để chứng minh visitor A không đọc được conversation state của
  visitor B hoặc tenant khác.

**Kết quả:** context được xem là dữ liệu có scope, có freshness và có nguồn,
không phải một chuỗi hội thoại không giới hạn.

### Buổi 5 — Knowledge ingestion và RAG trên PostgreSQL

**Thời lượng:** 60 phút  
**Theory**

- Knowledge flow: URL → public fetch → HTML/plain-text extraction → tokenized
  chunks → embeddings → PostgreSQL → retrieval → prompt.
- `POST /_leoai/update-knowledge` trong
  [leobot_router/leobot_knowledge_router.py](../../leobot_router/leobot_knowledge_router.py).
- `KnowledgeCreator`, `PublicWebPageFetcher` và `KnowledgeRetriever` trong
  [leoai/rag_knowledge_manager.py](../../leoai/rag_knowledge_manager.py).
- Giới hạn source: public HTTP(S), validated redirects, content type, 2 MB
  download và 100,000 ký tự extracted text.
- `knowledge_sources` và `knowledge_chunks` trong
  [sql_scripts/leo360_schema.sql](../../sql_scripts/leo360_schema.sql), với
  pgvector, metadata, full-text index và tenant-scoped foreign key.
- Vì sao ingestion phải giữ knowledge cũ khi fetch, embedding hoặc database
  update thất bại.

**Lab**

- Gửi một authenticated URL-ingestion request.
- Kiểm tra source status, chunk count, embedding dimensions và visitor scope.
- Chạy document chat với `context="agent"` và
  `persona_id="personal_assistant"`.
- Viết test cho invalid URL, private/local address, unsupported content type,
  missing token và failed update.

**Kết quả:** một RAG path có evidence boundary, source metadata và isolation
được kiểm thử.

### Buổi 6 — Grounded place workflows: PostGIS và Brave Search

**Thời lượng:** 60 phút  
**Theory**

- Browser geolocation tạo touchpoint; touchpoint được lưu với coordinates,
  geometry, keywords và embedding.
- `ChatDBManager` trong [leoai/rag_db_manager.py](../../leoai/rag_db_manager.py):
  upsert touchpoint, resolve location và `find_nearby_places()`.
- PostGIS `ST_DWithin`, `ST_Distance`, geography indexes và nearest-first
  ordering.
- Tenant visibility: private tenant places cộng với shared `global` places.
- Nearby-place response là database-grounded; không gọi AI để bịa hoặc
  summarize kết quả local search.
- `BravePlaceSearchClient` và `BraveAgentSearch` cung cấp discovery/grounded
  web context cho enrichment, không thay thế local database.

**Lab**

- Tạo touchpoint từ browser hoặc API và kiểm tra nearby places.
- Chạy câu hỏi “near me” với result limit và radius; kiểm tra behavior khi
  thiếu location hoặc thiếu kết quả.
- Trace selected-place picker và follow-up như “history” hoặc “opening hours”.
- Viết regression test cho radius, tenant filter, result limit và HTML/text
  answer formatting.

**Kết quả:** biết khi nào dùng local deterministic query và khi nào enqueue
discovery/enrichment.

### Buổi 7 — Dagster pipelines, enrichment và CDP ETL

**Thời lượng:** 60 phút  
**Theory**

- Background work trong LEO Bot: chat không chờ enrichment hoàn tất.
- `geo_places_pipeline` trong
  [dags_pipelines/geo_places_pipeline.py](../../dags_pipelines/geo_places_pipeline.py):
  discovery, coordinate recovery, grounded search, Mass schedule và knowledge
  enrichment.
- Dagster assets, jobs, resources, config, retry policy và weekly schedule.
- Commit từng place/source để failure sau đó không rollback dữ liệu đã hợp lệ.
- `leo_cdp_to_leo_bot_etl` trong
  [dags_pipelines/arango_to_postgres_leo_cdp.py](../../dags_pipelines/arango_to_postgres_leo_cdp.py):
  keyset pagination, batch embeddings, upsert profiles/transactions và refresh
  metrics.
- Phân biệt pipeline simulation trong các causal DAG với production data flow.

**Lab**

- Materialize một scoped geo-place run theo cấu hình trong
  [dags_pipelines/README.md](../../dags_pipelines/README.md).
- Quan sát graph dependencies và retry behavior trong Dagster.
- Đọc run config của `segment_id`, `batch_size`, `search_name`, coordinates và
  `max_places`.
- Kiểm tra records được ghi vào `geo_places`, `knowledge_sources` và
  `knowledge_chunks`.

**Kết quả:** thiết kế được một background capability có bounded work,
retry và persistence rõ ràng.

### Buổi 8 — FastAPI API, web client và messaging channels

**Thời lượng:** 60 phút  
**Theory**

- Async request handling, Pydantic request/response models và HTTP error
  semantics.
- Website endpoints trong
  [leobot_router/leobot_main_router.py](../../leobot_router/leobot_main_router.py):
  `/ask`, `/visitor-info`, `/touchpoint/geolocation`, `/ping` và readiness.
- `resources/`: Jinja2 templates, browser geolocation, visitor profile,
  touchpoint cache và chat transport.
- Facebook Messenger và Zalo OA webhook adapters:
  nhận event → gọi cùng `RAGAgent` → gửi outbound message.
- Admin router, optional Keycloak integration và Redis-backed session.
- Rate limit, question length, empty input và coordinate validation là một
  phần của agent backend contract.

**Lab**

- Đọc request từ browser đến `/ask` và response rendering trong
  [resources/js/leocdp.chatbot.js](../../resources/js/leocdp.chatbot.js).
- Thêm một validation case hoặc response field mà không làm vỡ channel
  adapters.
- Dùng mock HTTP client để test Facebook/Zalo inbound và outbound flow.
- Kiểm tra `/ping` và `/is-ready` khi provider credential có hoặc không có.

**Kết quả:** một agent workflow có thể được phục vụ qua nhiều channel mà
không nhân bản business logic.

### Buổi 9 — Security, reliability và regression testing

**Thời lượng:** 60 phút  
**Theory**

- Bearer token protection cho knowledge ingestion và fail-closed khi secret
  chưa được cấu hình.
- Public URL validation chống private/local network access, unsafe redirect,
  oversized download và unsupported content.
- Tenant-scoped keys, composite foreign keys, tenant filters và optional
  PostgreSQL row-level security trong schema.
- Keycloak cho admin SSO khi được bật; Redis session TTL và logout flow.
- Explicit errors, logging, retry boundaries và không trả success-shaped
  fallback khi Dagster submission hoặc provider operation thất bại.
- Test layers: unit tests, async tests, database-gated tests, API behavior,
  frontend Node tests và pipeline tests.

**Lab**

- Chạy nhóm test liên quan đến knowledge, document chat, nearby places,
  place selection, context và AI core.
- Thêm một regression test cho lỗi phát hiện trong các buổi trước.
- Review tenant_id trong query, composite key trong schema và error response
  ở router.
- Tạo failure matrix: input, external API, AI provider, Redis, PostgreSQL và
  Dagster.

**Kết quả:** agentic feature được đánh giá bằng behavior và failure evidence,
không chỉ bằng một câu trả lời demo.

### Buổi 10 — Knowledge Graph cho context enrichment và intent prediction

**Thời lượng:** 60 phút  
**Theory**

- Knowledge graph bổ sung các quan hệ rõ ràng mà vector retrieval không thể
  hiện đầy đủ: visitor/tenant, conversation, profile, touchpoint, place,
  knowledge source/chunk, persona và intent.
- Vì sao knowledge quan trọng cho context enrichment: agent có thể chọn đúng
  entity, relationship, scope và provenance trước khi đưa dữ liệu vào prompt.
- Vì sao relationship và lịch sử giúp intent prediction: intent hiện tại có
  thể được phân tích cùng conversation context, selected place, touchpoint,
  profile và các intent/ confidence đã lưu.
- Đối chiếu graph view với dữ liệu đang có trong PostgreSQL:
  `chat_messages`, `conversational_context`, `touchpoints`,
  `knowledge_sources`, `knowledge_chunks`, `geo_places`,
  `customer_profile` và `transactional_context`.
- Tenant isolation, source provenance, freshness và conflict handling khi
  graph context được dùng để enrich prompt.

**Tech scope**

Repository hiện chưa có dependency hoặc implementation cho NetworkX, Apache
AGE hoặc Cypher. Vì vậy, không mô tả chúng như stack đang chạy. Lab dùng
Python, PostgreSQL, SQL, pgvector, PostGIS và schema hiện có để thiết kế graph
model, relationship query và context-enrichment contract. NetworkX, Apache AGE
và Cypher chỉ được xem là các phương án nghiên cứu cho một mở rộng tương lai,
không phải deliverable bắt buộc của codebase hiện tại.

**Lab / Demo**

1. Lập graph model từ các bảng và entity đang có, xác định node, edge,
   tenant scope, source và thời gian hiệu lực.
2. Thiết kế một context-enrichment query cho selected place hoặc document
   chat bằng PostgreSQL/SQL, kết hợp metadata, vector similarity hoặc
   PostGIS khi phù hợp.
3. Thiết kế một intent-prediction flow dùng conversation context,
   `intent_label`, `intent_confidence` và các relationship đã lưu.
4. Viết acceptance criteria và test cases cho provenance, missing relationship,
   tenant isolation, stale data và conflicting sources.
5. Trình bày cách chuyển design này thành một feature mới hoặc upgrade trong
   Capstone mà không làm thay đổi sai contract của `RAGAgent`.

**Kết quả:** học viên hiểu khi nào graph relationship giúp enrich context và
intent prediction tốt hơn, đồng thời tạo được một thiết kế khả thi trên
PostgreSQL/pgvector/PostGIS đang có trong LEO Bot.

### Buổi 11 — Persona cho Agent và context-aware personalization

**Thời lượng:** 60 phút  
**Theory**

- Phân biệt **persona của agent** với **persona của người dùng**:
  `persona_id` trong request chọn behavior/system prompt của agent, còn
  profile, goal, evidence, state và situation mô tả context của người dùng.
- Runtime hiện có: `Message.persona_id` đi qua `RAGAgent`, được
  `AgentOrchestrator` dùng để chọn `PersonaManagement` description trước khi
  build prompt.
- Vì sao personalization phải dựa trên context hiện tại, không chỉ trên một
  profile tĩnh: current question, conversation summary, touchpoint,
  selected place, consent, freshness và uncertainty đều ảnh hưởng đến câu trả
  lời hoặc recommendation.
- Database persona design trong
  [sql_scripts/leo360_schema.sql](../../sql_scripts/leo360_schema.sql):
  `persona_schemas` version hóa dimensions; `persona_consents` lưu consent
  append-only; `persona_goals` lưu goal và setpoint theo version;
  `persona_evidence` lưu provenance và missingness; `persona_states` lưu
  estimate theo thời gian cùng uncertainty; `persona_contexts` lưu situation
  có `valid_until`.
- Tách các lớp dữ liệu: identity/profile, long-lived goals, evidence,
  computed state, short-lived situation và recommendation decision.
- Tenant isolation, composite foreign keys, consent-at-execution,
  data minimization và nguyên tắc không xem “không có evidence” là “giá trị
  bằng không”.

**Lab / Demo**

1. Trace `persona_id` từ request, message persistence và prompt construction
   trong [leoai/leo_datamodel.py](../../leoai/leo_datamodel.py),
   [leoai/rag_agent.py](../../leoai/rag_agent.py) và
   [leoai/rag_prompt_builder.py](../../leoai/rag_prompt_builder.py).
2. Thiết kế database persona cho một use case của LEO Bot: xác định schema,
   dimensions, consent scopes, goals, evidence, states và expiring contexts.
3. Viết SQL/query plan để lấy persona context đúng tenant, đúng user và đúng
   thời điểm; không dùng state đã hết hạn hoặc evidence đã bị retract.
4. Thiết kế cách đưa persona context vào `ContextManager` và prompt mà không
   ghi đè current question hoặc selected-place evidence.
5. Viết acceptance criteria và tests cho personalization: missing evidence,
   conflicting evidence, expired context, withdrawn consent và tenant
   isolation.

**Kết quả:** học viên có thể thiết kế một database persona có provenance,
consent, uncertainty và temporal context, sau đó nối persona context vào agent
để cá nhân hóa câu trả lời một cách có kiểm soát.

### Buổi 12 — Capstone: xây tính năng mới hoặc nâng cấp LEO Bot

**Thời lượng:** 60 phút  
**Theory**

- Chuyển một nhu cầu người dùng hoặc failure case thành một feature request
  có acceptance criteria rõ ràng.
- Chọn đúng extension point trong LEO Bot: FastAPI router, `RAGAgent`
  workflow, AI provider/embedding adapter, context, knowledge retrieval,
  PostgreSQL/Redis hoặc Dagster pipeline.
- Thiết kế thay đổi theo request flow, state contract, database scope,
  tenant isolation và error behavior hiện có.
- Phân biệt một feature mới với một upgrade: thêm capability, cải thiện
  grounding/context, tăng độ tin cậy, hỗ trợ channel hoặc tối ưu pipeline.

**Lab / Demo**

Mỗi học viên hoặc nhóm chọn **một tính năng mới hoặc một nâng cấp cụ thể cho
LEO Bot**. Năm gợi ý trong phạm vi repository:

1. **Knowledge ingestion không mất dữ liệu:** nâng cấp
   `KnowledgeCreator` để xử lý một failure case cụ thể và chứng minh source
   hoặc chunks cũ vẫn được giữ khi fetch, embedding hoặc database update thất
   bại.
2. **Workflow branch mới cho `RAGAgent`:** thêm một nhánh LangGraph cho một
   loại request mới, gồm state fields, routing condition, response generation
   và persistence phù hợp.
3. **Context và visitor isolation:** nâng cấp `ContextManager` hoặc Redis
   visitor state để xử lý một follow-up/selected-place case tốt hơn, đồng thời
   thêm test chứng minh dữ liệu không bị trộn giữa visitor hoặc tenant.
4. **Nearby-place grounding:** cải thiện `find_nearby_places()` hoặc response
   formatting với radius, result limit, tenant scope hoặc source evidence, kèm
   regression test cho PostGIS behavior.
5. **Dagster enrichment/ETL reliability:** nâng cấp một asset/job trong
   `dags_pipelines` bằng run config, retry boundary, bounded work hoặc partial
   failure handling; kiểm tra kết quả ghi vào PostgreSQL.

Deliverable tối thiểu:

1. Feature request, user scenario và acceptance criteria.
2. Source map mô tả request path qua router, agent, provider, database,
   Redis hoặc pipeline liên quan.
3. Implementation có type/contract rõ ràng và dùng lại abstraction hiện có.
4. Regression tests cho happy path và ít nhất một failure path.
5. Database/query review cho tenant, source metadata, vector hoặc geospatial
   scope nếu feature có persistence.
6. Demo trước/sau, response evidence và ghi chú giới hạn còn lại.

**Kết quả:** học viên tạo và bàn giao được một feature mới hoặc một upgrade
thực sự cho LEO Bot, có code, test, evidence và giới hạn được giải thích rõ
thay vì chỉ trình bày một prompt demo.

## Repository map dùng trong lớp

| Chủ đề | Source of truth |
| --- | --- |
| Application startup và configuration | [main_app.py](../../main_app.py), [main_config.py](../../main_config.py) |
| Agent workflow | [leoai/rag_agent.py](../../leoai/rag_agent.py) |
| AI providers và embeddings | [leoai/ai_core.py](../../leoai/ai_core.py) |
| Context và prompt rules | [leoai/rag_context_manager.py](../../leoai/rag_context_manager.py), [leoai/rag_prompt_builder.py](../../leoai/rag_prompt_builder.py) |
| Chat, touchpoint và nearby SQL | [leoai/rag_db_manager.py](../../leoai/rag_db_manager.py) |
| Knowledge ingestion và retrieval | [leoai/rag_knowledge_manager.py](../../leoai/rag_knowledge_manager.py), [leobot_router/leobot_knowledge_router.py](../../leobot_router/leobot_knowledge_router.py) |
| HTTP and channel adapters | [leobot_router/](../../leobot_router/) |
| Browser UI and transport | [resources/](../../resources/) |
| Schema, vectors, geospatial data, tenancy | [sql_scripts/leo360_schema.sql](../../sql_scripts/leo360_schema.sql) |
| Dagster jobs and assets | [dags_pipelines/](../../dags_pipelines/) |
| Tests and runnable commands | [README.md](../../README.md), [tests/](../../tests/) |

## Suggested stack trong repository

- Python `>=3.12,<3.13`
- FastAPI, Uvicorn, Pydantic, Jinja2 và `httpx`
- LangGraph `StateGraph`
- Google GenAI, OpenAI SDK và OpenRouter qua OpenAI-compatible client
- PostgreSQL 18, pgvector, PostGIS và pg_trgm
- `psycopg`, `psycopg2`, `asyncpg` và Redis
- Dagster, Dagster GraphQL và Python ArangoDB client
- Brave Place Search / grounded web context integration
- `pytest`, `pytest-asyncio` và Node test cho browser client

## Phạm vi kết thúc khóa học

Khóa học kết thúc ở một agent backend có workflow, context, retrieval,
geospatial grounding, persistence, channel integration, tests và background
pipeline integration theo đúng khả năng của LEO Bot. Các phần được xem là
ngoài phạm vi nếu không có implementation tương ứng trong repository. Mọi
đề xuất mở rộng ở buổi cuối phải bắt đầu từ một interface, table, router,
pipeline hoặc test đang tồn tại.
