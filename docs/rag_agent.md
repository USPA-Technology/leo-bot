% LeoBot RAG Agent
% LeoBot maintainers
% 2026-10-10

# Overview

[`leoai/rag_agent.py`](../leoai/rag_agent.py) coordinates the retrieval-augmented
chat flow used by LeoBot. Parsing, response-formatting, and enrichment submission helpers live in
[`leoai/rag_agent_utils.py`](../leoai/rag_agent_utils.py), keeping the agent
module focused on workflow orchestration. Together, the modules support three
user-facing paths:

1. **Document chat** retrieves knowledge without mixing it with geolocation state.
2. **Nearby-place search** parses a category and metric radius, searches local
   data by coordinates, and queues background enrichment when there are no
   matches or fewer than requested. Existing matches remain in a partial
   response. The chat response remains plain text; the formatter also supports
   HTML when called directly.
3. **Standard chat** persists the message, builds context, optionally handles a
   place choice, builds a prompt, generates an answer, and persists the answer.

# Answer instruction contracts

[`leoai/rag_prompt_builder.py`](../leoai/rag_prompt_builder.py) supplies the
following instructions in both the generated prompt and the system instruction:

- `CURRENT_QUESTION_INSTRUCTIONS` prioritizes the current request, including
  questions prefixed by greetings and multi-part tasks. It resolves selections
  using displayed choices, not database IDs, and respects corrections and topic
  changes. It prohibits claiming completed actions without application evidence.
- `PLACE_FOLLOWUP_INSTRUCTIONS` keeps place follow-ups on the selected subject
  while it remains active, without treating nearby candidates as selections.
  Place-specific claims must match the supplied place evidence; unknown details,
  conflicting sources, and missing direction origins must not be invented.
- `DOCUMENT_CHAT_INSTRUCTIONS` keeps document Q&A separate from cached location
  state. Excerpts ground factual claims; history resolves references. Citations
  and quotations must come from supplied evidence, and missing retrieval evidence
  must not be described as proof that the entire collection lacks an answer.

Context and retrieved content are treated as data, not instructions. These are
generation guidance, not a substitute for application-level validation or
evidence that a model will always comply.

# Module responsibilities

## `leoai.rag_agent_utils`

This module has no agent state or direct database writes. It provides:

- classifying document and greeting messages locally, and using the configured
  `AIClient` to classify nearby-place intent and extract search categories;
- parsing place selections and requested result limits; and
- formatting nearby-place results, pickers, and confirmations as user-facing
  text or HTML; and
- submitting a bounded place discovery and knowledge-enrichment job to Dagster.

Nearby-intent classification runs only when a nearby-location phrase is
present, and runs outside the asyncio event loop. Its structured output is
validated and generic parent categories are removed when a specific category
was requested. The enrichment trigger performs a network request and returns
the accepted run ID without polling.
Location-cue detection removes Vietnamese diacritics before matching, so
common unaccented input such as `gần toi` still enters nearby classification.
The AI intent prompt interprets `quán mì/mỳ` as noodle places rather than a
generic request for religious locations or restaurants.

The helpers are imported into `rag_agent.py`, so existing imports such as
`from leoai.rag_agent import nearby_result_limit` remain compatible.

## `leoai.rag_agent`

This module owns the `ChatMessageState` workflow state and the `RAGAgent`
orchestrator. It coordinates the database, context manager, knowledge
retriever, prompt builder, Redis profile cache, and generation client.

`ChatMessageState` carries identifiers, message and touchpoint metadata,
location, retrieved context, place-selection state, prompt routing data, and
the final response.

# Public helpers

The following helpers are implemented in `rag_agent_utils.py` and re-exported
by `rag_agent.py` for backwards compatibility.

## `is_document_chat(context, persona_id)`

Returns `True` for the document-chat combination of the `agent` context and
`personal_assistant` persona.

## `is_greeting_message(message)`

Checks whether the message is a supported English or Vietnamese greeting.

## `selected_place_index(message, place_count)`

Parses a one-based choice such as `1`, `option 2`, or `chọn 3`, and returns a
zero-based index. Returns `None` for an invalid or out-of-range choice.

## `nearby_place_terms(message)`

Uses the configured `AIClient` to extract specific searchable categories such
as ramen, coffee, churches, temples, and markets. It favors precise terms over
generic parents (for example, ramen rather than restaurant/food).

## `is_nearby_place_question(message)`

Uses the configured `AIClient` to decide whether the message requests nearby
places. Messages without a nearby-location phrase return `False` without an
AI request. Nearby phrases are matched after Vietnamese accent normalization.

## `nearby_result_limit(message, explicit_limit=None)`

Resolves the requested number of results. An explicit API value wins over a
number parsed from the message. If no number is supplied,
`NEARBY_PLACES_LIMIT` is used. Invalid, non-positive, and boolean values raise
`ValueError`.

## `nearby_radius_meters(message)`

Parses a positive metric radius such as `1 km`, `500 meters`, or `1,5 km`.
If no radius is present, `NEARBY_PLACES_RADIUS_METERS` is used. The same radius
is applied to the local PostGIS query and the enrichment job.

## `geo_places_search_name(message)`

Extracts a focused discovery category, such as `coffee`, instead of sending the
full conversational question as a place name. Coffee queries use coffee/cafe
terms rather than also matching arbitrary restaurants.
Ramen questions use the specific `ramen` term rather than the broad restaurant
category, preventing unrelated convenience stores, fast-food outlets, or udon
shops from suppressing the no-results enrichment path.

## `trigger_geo_places_enrichment(name, latitude, longitude, radius, count=5, ...)`

Refactored from the submission portion of the church-place proof-of-concept
trigger. Submits the existing `geo_places_pipeline` asset job, selecting all
four assets (`process_places`, `process_brave_search`, `process_mass_schedule`,
and `process_knowledge`), then returns the run ID
as soon as Dagster accepts it. A count greater than five is capped at five.
Invalid input or a failed submission raises an exception; the helper does not
report success when no run was accepted.

Connection defaults come from `DAGSTER_HOST` (`localhost`), `DAGSTER_WEB_PORT`
(`3000`), `DAGSTER_REPOSITORY_LOCATION` (`dags_pipelines`), and
`DAGSTER_REPOSITORY` (`__repository__`). Explicit keyword arguments override
these settings. Each GraphQL request has a 15-second timeout.

## `format_nearby_places_answer(places, target_language, terms, answer_in_format)`

Formats nearby places as readable text or escaped HTML. Each result includes
its name, distance, optional address and description, and a Google Maps link
when HTML is requested.

## `format_place_picker(places, target_language)`

Formats up to five nearby places as a numbered selection list.

## `format_place_selection_confirmation(place, target_language)`

Formats the confirmation shown after a visitor chooses a place.

# `RAGAgent`

## `RAGAgent.__init__(gemini_client=None)`

Initializes the generation client, embedding model, database manager, context
manager, knowledge retriever, and prompt orchestrator. A client can be
provided by tests or callers; otherwise the default `GeminiClient` is used.

## `create_geolocation_touchpoint(...)`

Creates or updates a touchpoint containing a user's latitude and longitude.
The database manager owns the upsert behavior.

## `process_chat_message(...)`

Public asynchronous entry point for chat. It assembles a
`ChatMessageState`, invokes the cached workflow, and returns the response.
Document-chat and standard-chat routing happens inside the graph.

The workflow is assembled with these stages:

1. Route document chat or standard chat.
2. Validate coordinates and nearby-place parameters.
3. Search nearby places, or prepare the standard touchpoint.
   An incomplete nearby result list routes to background enrichment before its
   answer is saved.
4. Persist the user message and build conversation context.
5. Show a place picker, persist a place selection, or build a prompt.
6. Generate and, when appropriate, persist the answer.

## `_get_chat_graph()`

Builds the LangGraph workflow once and caches the compiled graph on the
instance. Subsequent messages reuse the same graph.

## `_route_chat_type(state)`

Routes document-chat requests to `_chat_document_node`; all other requests
continue through input validation.

## `_validate_input_node(state)`

Ensures latitude and longitude are supplied together. For nearby questions it
also stores the search terms and validated result limit.

## `_route_after_validation(state)`

Routes nearby-place questions to the search node and all other requests to the
standard touchpoint workflow.

## `_chat_document_node(state)`

Delegates document-chat processing and places its answer in workflow state.

## `_nearby_places_node(state)`

Queries the database for nearby places, handles unavailable location data,
formats matching data or requests location. It does not invoke enrichment when
location is unavailable.

## `_route_after_nearby_places(state)`

Routes to enrichment when the local result count is below the requested limit.
The trigger requests only the missing count, capped at five places. Complete
results and missing-location responses bypass enrichment.

## `_enrich_geo_places_node(state)`

Resolves coordinates directly or from a visitor-owned touchpoint, then calls
the shared Dagster trigger in a worker thread so the event loop is not blocked.
It keeps any already-found places in the response and adds a localized
search-queued notice after successful submission. It does not wait for Brave
search or knowledge generation.

## `_save_nearby_exchange_node(state)`

Persists the user message and the final nearby response without requesting
message embeddings, including a queued notice for incomplete results.

## `_prepare_touchpoint_node(state)`

Creates a geolocation touchpoint when coordinates are available. Otherwise it
uses the supplied touchpoint or the `web_leobot` fallback.

## `_save_user_message_node(state)`

Persists a standard-chat user message. Database logging failures are logged
without preventing the rest of the response pipeline.

## `_build_context_node(state)`

Builds the conversation summary and exposes user context, nearby places, and
the selected place to later workflow nodes.

## `_route_after_context(state)`

Routes a greeting with available places to the picker, a valid numbered choice
to place selection, and all other messages to prompt generation.

## `_place_picker_node(state)`

Stores the current place choices in the context summary, persists the picker
response, and returns the numbered list.

## `_place_selection_node(state)`

Validates and persists the selected place, then returns a localized
confirmation.

## `_build_prompt_node(state)`

Retrieves focused knowledge for a selected place, updates the profile cache
when a first name is available, and builds the prompt router.

## `_generate_answer_node(state)`

Generates the response through `_safe_generate`.

## `_save_answer_node(state)`

Persists generated text responses. Report-style prompts are intentionally not
persisted as ordinary chat messages.

## `_retrieve_selected_place_knowledge(selected_place, user_message)`

Calls the optional selected-place retriever with a small result limit. Returns
an empty string when the configured retriever does not provide that capability.

## `_process_document_chat(...)`

Persists the document-chat exchange on the isolated
`DOCUMENT_CHAT_TOUCHPOINT_ID`, retrieves relevant knowledge for non-greeting
questions, builds a document prompt, and generates the answer.

## `_safe_generate(prompt_router, temperature_score)`

Selects report or content generation, passes the appropriate generation
options, and supports both synchronous and asynchronous client methods without
blocking the event loop.

# Error and persistence behavior

- Latitude and longitude must be supplied together.
- Invalid nearby-place limits raise `ValueError`.
- Non-positive search radii are rejected; the HTTP endpoint responds with 400.
- Missing location data produces a localized request for the visitor to share
  their location.
- Required place-choice persistence failures raise `RuntimeError`.
- A failure while persisting a standard user message is logged and does not
  prevent response generation.
- The public pipeline logs unexpected failures and returns a user-facing
  error message. A failed Dagster submission never claims a search was queued.

# Background place enrichment

The on-demand chat path runs the full asset job in
[`dags_pipelines/geo_places_pipeline.py`](../dags_pipelines/geo_places_pipeline.py):

```text
process_places
├── process_brave_search ───┐
└── process_mass_schedule ──┴── process_knowledge
```

Discovery calls Brave Place Search, filters unrelated results, and uses PostGIS
`ST_DWithin` to enforce the radius. Brave's radius parameter alone is only a
location bias. At most five matching places are upserted into `geo_places`
using the requested category. `process_brave_search` and `process_knowledge`
use the same category/radius scope. `process_mass_schedule` executes as part of
the full job but skips non-church categories. Knowledge enrichment creates the
place-owned `knowledge_sources` row and vectorized `knowledge_chunks`.
Provider and database failures remain visible as failed Dagster assets/runs.

Example interaction:

```text
User: top 3 coffee shop near me in 1 km
Bot: I have no matching place data within your requested radius yet.
     I have queued a search to find and add places for you.
     Please ask again after the search finishes.
```

The existing chat API returns this notice in its `answer` field, so no frontend
response shape changes are required. A later question queries the database
again and returns available matching places. A queued run is not a promise
that the provider will find results or that enrichment will succeed.

Dagster must be running with the updated `dags_pipelines` code location and
database/Brave/AI credentials. See
[`dags_pipelines/README.md`](../dags_pipelines/README.md) for setup. The
[`test_poc/test_trigger_geo_places_tasks.py`](../test_poc/test_trigger_geo_places_tasks.py)
CLI reuses the shared trigger and retains polling only for manual testing.

# Export with Pandoc

From the repository root:

```bash
pandoc docs/rag_agent.md --standalone --toc -o docs/rag_agent.html
pandoc docs/rag_agent.md --standalone --toc -o docs/rag_agent.docx
pandoc docs/rag_agent.md --standalone --toc -o docs/rag_agent.pdf
```

PDF export requires a LaTeX engine such as `xelatex`. The generated files are
ignored by Git only if the project adds matching ignore rules; otherwise keep
exported artifacts outside the repository or remove them before committing.
