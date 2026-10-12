# 🤖 LeoBot — AI Chat Assistant for Businesses & Users

![LeoBot Screenshot](screenshot/leobot.png)

**LeoBot** is a FastAPI-based AI chatbot platform for intelligent, real-time conversations across multiple channels — including **websites**, **Facebook Messenger**, and **Zalo Official Accounts**.
It integrates seamlessly with **LEO CDP (Customer Data Platform)** to serve both **admins** and **end-users**, delivering contextual, personalized answers powered by **RAG (Retrieval-Augmented Generation)** and advanced AI models like **Google Gemini**.

---

## 🌐 Live Chatbot Demo

Try the chatbot in action:
👉 [https://leobot.leocdp.com](https://leobot.leocdp.com)

LeoBot uses the configured AI provider for natural, context-aware responses.

---

## 🚀 Features

* **Multi-channel support:** Website chat, Facebook Messenger, and Zalo OA.
* **Provider-configurable AI:** Google Gemini, OpenAI, or OpenRouter, with
  configurable chat, reasoning, and embedding models.
* **RAG and document chat:** Visitor-scoped knowledge retrieval, persistent
  conversation context, and authenticated web-page ingestion.
* **Nearby place discovery:** Optional browser geolocation, bilingual
  recommendations based on nearby place categories, and radius-aware PostGIS
  search.
* **Background place enrichment:** Dagster searches for missing nearby results
  and enriches discovered places with grounded web context and place knowledge.
* **FastAPI backend and Redis rate limiting:** Async API routes and per-visitor
  request throttling.
* **Custom personas and touchpoints:** Context-aware conversations across
  profiles, roles, and channels.
* **Prebuilt frontend demos:** Localized Jinja2 interfaces and embeddable chat
  examples.

---

## 🧠 Architecture Overview

The FastAPI routers expose the web, webhook, and knowledge-ingestion APIs.
[`leoai/rag_agent.py`](leoai/rag_agent.py) coordinates document chat,
nearby-place search, place selection, and standard conversation workflows;
[`leoai/ai_core.py`](leoai/ai_core.py) selects the configured AI and embedding
providers. PostgreSQL/PostGIS stores touchpoints, places, and visitor knowledge,
while Redis stores visitor state and enforces message rate limits.

Nearby searches first query local place data. When the requested list is
incomplete, the agent can submit the existing Dagster geo-places pipeline to
discover and enrich more places without blocking the chat response. The web UI
is split between [`leocdp.chatbot.js`](resources/js/leocdp.chatbot.js) for chat
transport and [`leocdp.agents.js`](resources/js/leocdp.agents.js) for localized
page behavior and location-aware recommendations.

---

## 🧩 Key Components

### RAGAgent

Routes document chat, nearby-place lookup and enrichment, place selection, and
standard conversation generation.

### Webhooks

* `/fb-webhook` — Facebook Messenger
* `/zalo-webhook` — Zalo Official Account

### Redis Rate Limiting

Uses a sorted-set time window to prevent excessive messaging per user.

---

## 🛠️ Setup and Installation

### 1. Clone the Repository

```bash
git clone https://github.com/trieu/leo-bot
cd leo-bot
```

### 2. Start PostgreSQL + pgvector (via Docker)

Make sure **Docker CLI** is installed:

```bash
docker --version
```

Then start the database:

```bash
./dockers/pgsql/start_pgsql_pgvector.sh
```

This script:

* Launches a PostgreSQL 18 container (`pgsql18_vector`)
* Mounts a persistent volume (`pgdata_vector18`)
* Enables **pgvector** and **postgis** extensions
* Creates the `leo360` database and schema
* Handles collation version fixes automatically

The schema uses PostgreSQL 18's native `uuidv7()` default for generated
knowledge source, chunk, `geo_places`, and `weather_data` IDs. `geo_places.id`
and `weather_data.id` are UUIDs in a fresh database (not the previous
`BIGSERIAL` type), so the development database must be recreated to use the
new definitions. Python-generated model, touchpoint, and session IDs are also
UUIDv7.

To **reset the database**, run:

```bash
./dockers/pgsql/start_pgsql_pgvector.sh --reset-db
```

The PostgreSQL 16 to 18 upgrade is a fresh initialization: `--reset-db` removes
the old `pgsql16_vector` container and `pgdata_vector` volume before creating
the PostgreSQL 18 database. This permanently deletes the old database data.

You can connect manually:

```bash
psql -h localhost -p 5433 -U postgres -d leo360
```

### 3. Configure Environment

Copy the repository's environment template, then edit `.env`:

```bash
cp .env.example.txt .env
```

The [`.env.example.txt`](.env.example.txt) file is the canonical full
configuration. The AI section below matches its Google defaults; configure
model IDs and credentials together when selecting a different provider.

```bash
# Core LEO BOT
LEOBOT_DEV_MODE=true
HOSTNAME=leobot.example.com
LEO_DATA_ENRICHMENT_KEY=
AI_PROVIDER=google
AI_CHAT_MODEL=gemini-3.5-flash-lite
AI_CHAT_TEMPERATURE=0.7
AI_REASONING_MODEL=gemini-3.8-flash
GEMINI_TEXT_MODEL_ID=gemini-3.5-flash-lite
GEMINI_API_KEY=
OPENAI_API_KEY=
OPENROUTER_API_KEY=
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

# Embeddings default to the same provider as AI_PROVIDER unless explicitly set.
EMBEDDING_PROVIDER=google
EMBEDDING_MODEL=gemini-embedding-001
EMBEDDING_API_KEY=
EMBEDDING_DIMENSIONS=768
TOUCHPOINT_EMBEDDING_PROVIDER=google
TOUCHPOINT_EMBEDDING_MODEL=gemini-embedding-001
TOUCHPOINT_EMBEDDING_DIMENSIONS=768
PGSQL_DB_URL=postgresql://postgres:password@localhost:5433/leo360

# Gemini API key; Google Cloud credentials below are optional and separate
# GOOGLE_APPLICATION_CREDENTIALS is only for Google Cloud APIs such as translation
GOOGLE_APPLICATION_CREDENTIALS= 
GEMINI_API_KEY=

# Set Redis HOST and PORT 
REDIS_USER_SESSION_HOST=localhost
REDIS_USER_SESSION_PORT=6379

# Set SMTP email information
SMTP_HOST=""
SMTP_PORT=587    
SMTP_USER="" 
SMTP_PASSWORD=""  
USE_TLS=true 

# in dev, disable HTTPS check certification
PYTHONHTTPSVERIFY=1

# Keycloak for leobot client at DEV mode
KEYCLOAK_ENABLED=false
KEYCLOAK_URL=https://leoid.example.com
KEYCLOAK_REALM=master
KEYCLOAK_CLIENT_ID=leobot
KEYCLOAK_CLIENT_SECRET=""
KEYCLOAK_CALLBACK_URL=https://leobot.example.com/_leoai/sso/callback
KEYCLOAK_VERIFY_SSL=false

# Set your Facebook Page Access here
FB_VERIFY_TOKEN=""
FB_PAGE_ACCESS_TOKEN=""
```

**AI provider setup:**

| `AI_PROVIDER` | Default chat model | Default reasoning model | API key |
| --- | --- | --- | --- |
| `google` | `gemini-3.5-flash-lite` | `gemini-3.8-flash` | `GEMINI_API_KEY` |
| `openai` | `gpt-4.1-mini` | `gpt-5.6-luna` | `OPENAI_API_KEY` |
| `openrouter` | `openai/gpt-4.1-mini` | `openai/gpt-5.6-luna` | `OPENROUTER_API_KEY` |

The model defaults above apply when `AI_CHAT_MODEL` and `AI_REASONING_MODEL`
are empty. The checked-in template explicitly sets Google model IDs, so changing
only `AI_PROVIDER` and its API key is not enough: update both model IDs to
models supported by the selected provider, or clear them to use that provider's
defaults. `GEMINI_TEXT_MODEL_ID` is a Google-only fallback and can override both
Google model defaults if the general `AI_*_MODEL` values are empty.

Embeddings are configured separately from chat. The template explicitly sets
both `EMBEDDING_PROVIDER` and `TOUCHPOINT_EMBEDDING_PROVIDER` to `google`. When
moving all AI traffic to OpenAI or OpenRouter, change both settings and their
model IDs too; otherwise the embedding paths still need `GEMINI_API_KEY`.
`EMBEDDING_API_KEY`, when set, overrides the selected provider key for
embeddings. Keep both embedding dimensions at `768` to match the current
PostgreSQL vector columns.

| Embedding provider | Default model |
| --- | --- |
| `google` | `gemini-embedding-001` |
| `openai` | `text-embedding-3-small` |
| `openrouter` | `openai/text-embedding-3-small` |

For example, to switch the template to OpenAI, set `AI_PROVIDER=openai`,
`AI_CHAT_MODEL=gpt-4.1-mini`, `AI_REASONING_MODEL=gpt-5.6-luna`,
`EMBEDDING_PROVIDER=openai`, `EMBEDDING_MODEL=text-embedding-3-small`,
`TOUCHPOINT_EMBEDDING_PROVIDER=openai`, and
`TOUCHPOINT_EMBEDDING_MODEL=text-embedding-3-small`; provide `OPENAI_API_KEY`.

Get `GEMINI_API_KEY` at [Google AI Studio](https://aistudio.google.com/app/library).
`GOOGLE_APPLICATION_CREDENTIALS` is only for Google Cloud services such as
translation; it is not the Gemini API key. Google Cloud translation requires
service-account credentials from the
[Google Cloud Console](https://console.cloud.google.com/apis/api/translate.googleapis.com/credentials).

---

### 4. Python Environment (Ubuntu Example)

```bash
sudo apt install python-is-python3 python3.12-venv
python3.12 -m venv env
source env/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

This project uses Python **3.12** for both development and production. The
startup scripts reject environments running another Python minor version.

After installation, refresh your shell.

---


### 5. Run LeoBot

Production mode:

```bash
./start_app.sh
```

This starts PostgreSQL, the Dagster **cluster** (webserver and daemon), and the
FastAPI chatbot. It waits for Dagster and the chatbot health endpoint before
reporting success. Dagster webserver and daemon logs are written under `logs/`;
managed service PID files are kept in the ignored `.dagster-pids/` directory.

Stop or restart both the chatbot and Dagster cluster with:

```bash
./stop_app.sh
./restart_app.sh
```

Stopping the application leaves PostgreSQL running. `restart_app.sh` runs the
lifecycle commands as the `leocdp` service account; set
`LEOBOT_SERVICE_USER` to override it when needed. The scripts use the repository
directory they are installed in and can be invoked from any working directory.

To initialize or refresh the 50 Ho Chi Minh City sample places:

```bash
./start_app.sh --seed-data
```

For development-only resets, the seeding helper also supports:

```bash
./start-seeding-data.sh --clear-all yes
./start-seeding-data.sh --drop-db-and-start-new yes
```

`--clear-all yes` truncates every non-system table and restarts owned sequences
before seeding. `--drop-db-and-start-new yes` drops and recreates `leo360`,
applies `sql_scripts/leo360_schema.sql`, then seeds. These options are mutually
exclusive; both require the literal `yes` confirmation and destroy existing
data.

To replace the old PostgreSQL 16 data with a fresh PostgreSQL 18 database:

```bash
./start_app.sh --reset-db
```

The reset option is destructive and must be passed explicitly.

Development mode:

```bash
./start_dev.sh
```

`start_dev.sh` starts the chatbot only; to enable background nearby-place
enrichment in development, start the Dagster cluster separately with
`./start_dagster.sh --cluster`.

Development mode with sample place data:

```bash
./start_dev.sh --seed-data
```

LeoBot will run at `0.0.0.0:8888`.
Open your browser and visit your configured `HOSTNAME` to test.

---

## 🌐 API Endpoints

| Endpoint            | Method   | Description                      |
| ------------------- | -------- | -------------------------------- |
| `/_leoai/ask`              | POST     | Main chatbot endpoint            |
| `/_leoai/is-ready`         | GET/POST | Configured AI provider readiness check |
| `/_leoai/touchpoint/geolocation` | POST | Create/update a geolocation touchpoint, return nearby places and localized recommendations |
| `/_leoai/fb-webhook`       | GET/POST | Facebook Messenger webhook       |
| `/_leoai/zalo-webhook`     | POST     | Zalo OA webhook                  |
| `/_leoai/ping`             | GET      | Basic health check               |
| `/_leoai/visitor-info` | GET      | Retrieve visitor info from Redis |
| `/_leoai/update-knowledge` | POST | Bearer-token-protected URL ingestion into visitor-owned knowledge sources/chunks |

The geolocation response includes `recommended_actions`, a JSON array of
bilingual quick actions based on nearby place categories. The browser renders
these actions from the API response; when nearby category data is unavailable,
the API provides general discovery suggestions.

### Import a web page into document chat

Configure `LEO_DATA_ENRICHMENT_KEY` in the server's `.env` with a long,
random secret (for example, generate one with `openssl rand -hex 32`). Store
the same value in the external agent's secret manager; do not commit it.
`/_leoai/update-knowledge` requires this value in the
`Authorization: Bearer <token>` header. If the key is unset on the server, the
endpoint fails closed with `503`; a missing or incorrect token receives `401`.

Send an authenticated **POST**, not a GET, to the query-parameter endpoint:

```bash
curl \
  --header "Authorization: Bearer $LEO_DATA_ENRICHMENT_KEY" \
  --request POST --get \
  --data-urlencode 'source_type=web_page' \
  --data-urlencode 'visitor_id=7e7c56b6b2a74869a1b79659711f44d5' \
  --data-urlencode 'url=https://www.bigdatavietnam.org/2026/04/rag-vs-cag-giai-quyet-iem-mu-cua-ai-voi.html' \
  'https://leobot.leocdp.com/_leoai/update-knowledge'
```

Required: `url` and `visitor_id`. `source_type` defaults to `web_page` (the only
URL ingestion type currently supported); `name` optionally overrides the page
title. The response contains `source_id`, visitor/tenant identifiers, URL/title,
`status: "active"`, `chunk_count`, and `embedding_dimensions: 768`.

`KnowledgeCreator` extracts readable HTML/plain text, splits it with the existing
chunker, and generates embeddings using `EMBEDDING_*`. The same URL, source type,
and visitor reuse a stable source ID. A successful update atomically replaces
the source's previous chunks; fetch, embedding, or database failures do not
replace existing knowledge. Sources belong to the supplied visitor in the
`default` tenant and can be retrieved with `context="agent"` and
`persona_id="personal_assistant"` using that same `visitor_id`.

Downloads are restricted to public HTTP(S) addresses, including redirects.
PDFs/binary sources are not supported by this endpoint. The download limit is
2 MB; extracted text over 100,000 characters is rejected rather than truncated.
No database migration or additional Python dependencies are needed.

```bash
env/bin/python -m pytest -q tests/test_knowledge_creator.py
RUN_KNOWLEDGE_DB_TESTS=1 env/bin/python -m pytest -q tests/test_knowledge_creator.py
```

### Nearby-place questions

`/_leoai/ask` recognizes requests such as “what are churches near me?”,
“top 3 churches is near me”, and “top 20 churches nearby”. The count in the
question is passed as a SQL parameter, not fixed in the query. If no count is
specified, `NEARBY_PLACES_LIMIT` supplies the default.

Requests with **both** `context="agent"` and `persona_id="personal_assistant"`
use document chat instead. This mode has a separate `document_agent` conversation
key, ignores cached geolocation and place selections, and does not offer nearby
place menus. Non-greeting questions retrieve active knowledge excerpts belonging
to the visitor in the default tenant; greetings invite questions or document
content. If no excerpts are available, the prompt asks for the relevant document
rather than assuming location context. Other context/persona combinations keep
the existing location-aware behavior. `temperature_score` is passed to generation.

```json
{
  "visitor_id": "visitor-id",
  "question": "top 10 churches near me",
  "latitude": 10.747904,
  "longitude": 106.6467328,
  "answer_in_language": "en",
  "answer_in_format": "html"
}
```

An optional positive integer `result_limit` overrides the count in the question.
The search uses supplied coordinates or the visitor's saved touchpoint, keyword
matches in place names/categories/descriptions/tags, and PostGIS radius/distance
filtering. Results are nearest-first; there may be fewer than requested within
`NEARBY_PLACES_RADIUS_METERS`. Missing location prompts the visitor to share it.
HTML answers contain an escaped ordered list (`<ol>` / `<li>`); `text` answers
remain numbered plain text. Each bold place name in an HTML answer links to a
Google Search for its name and address. Nearby searches query PostgreSQL
directly without AI generation, summarization, or embedding requests.

If the local search returns fewer places than requested, the RAG agent submits
the existing Dagster `geo_places_pipeline` to discover more. The run requests
only the missing count, capped at five additional places. Any places already
found remain in the answer alongside a notice that more are being searched for.
The API does not wait for the run; a later question checks the database again.
Dagster submission failures are surfaced instead of returning a success-shaped
queued notice. Start Dagster with `./start_dagster.sh` and configure its worker
environment as described in [`dags_pipelines/README.md`](dags_pipelines/README.md).

When a greeting presents the five-place picker, the backend saves the exact
numbered choices. Choosing `4` saves that place as `selected_place` for the
visitor/touchpoint conversation. Short follow-ups such as “history”, “lịch sử”,
or “opening hours” use the selected place as their subject, even after summary
refreshes or nearby-result reordering. Numeric replies can explicitly change the
selection. The prompt distinguishes stored place facts from uncertain background
information; selection alone does not provide verified historical dates/hours.

Offline tests:

```bash
env/bin/python -m pytest -q \
  tests/test_nearby_places.py \
  tests/test_place_selection.py \
  tests/test_geo_places_enrichment.py
env/bin/python -m pytest -q tests/test_conversation_context.py tests/test_ai_core.py
env/bin/python -m pytest -q tests/test_document_chat.py
node --test tests/leocdp.chatbot.test.cjs
```

Optional PostGIS validation uses a temporary schema that is rolled back:

```bash
RUN_NEARBY_DB_TESTS=1 env/bin/python -m pytest -q tests/test_nearby_places.py
```

Selection persistence can also be tested against PostgreSQL with fake embeddings
in a rollback-only schema:

```bash
RUN_CONVERSATION_DB_TESTS=1 env/bin/python -m pytest -q tests/test_conversation_context.py
```

Document retrieval has a separate rollback-only database check:

```bash
RUN_DOCUMENT_DB_TESTS=1 env/bin/python -m pytest -q tests/test_document_chat.py
```

---

## 🧰 Developer Notes

* Built on **FastAPI** with full async I/O.
* Message context stored in **Redis**.
* Hosted embeddings via Google GenAI, OpenAI, or OpenRouter.
* Touchpoint metadata embeddings use a separate 768-dimensional configuration;
  existing chat/context embeddings remain 768-dimensional.
* Compatible with **pgvector** and other vector databases.
* The browser chatbot can request HTML5 geolocation permission. Coordinates are
  stored as PostGIS touchpoints, and nearby rows from `geo_places` are included in
  the conversation context. If permission is denied, normal chat continues
  without location context.

To extend LeoBot:

* Add webhook routes for new channels (Telegram, LINE, etc.)
* Create custom response modules in `rag_agent`
* Integrate new LLM APIs or plugins

---

## 🧪 Testing

Run automated tests:

```bash
pytest
```

Or test manually:

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"visitor_id": "demo", "question": "Hello!", "persona_id": "test"}'
```

---

## 🧭 Author & Resources

**Author:** [Trieu Nguyen](https://github.com/trieu)
**YouTube:** [@bigdatavn](https://www.youtube.com/@bigdatavn)
**Demo:** [https://leobot.leocdp.com](https://leobot.leocdp.com)

---

## 🌱 Future Roadmap

* [ ] Support Telegram, LINE, and WhatsApp
* [ ] Add knowledge-graph search (PostgreSQL + pgvector)
* [ ] Streaming chat via SSE/WebSocket
* [ ] AI analytics dashboard for admins
* [ ] Plugin SDK for external integrations

---

## 📜 License

MIT License — free to use, modify, and share.
Attribution is appreciated but not required..

---

## 💡 Vision

LeoBot embodies the union of **Dataism** and **AI pragmatism** — an assistant that connects people and data through natural conversation.
It’s not just automation; it’s augmentation — amplifying human understanding through intelligent dialogue.
