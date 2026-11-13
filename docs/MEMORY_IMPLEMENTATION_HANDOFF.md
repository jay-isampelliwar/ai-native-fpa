# Memory Management Implementation Handoff

> **Status: built.** This is the original plan, kept for history. The design below was followed,
> but some details changed when it was built:
>
> | Plan in this document | What the code does |
> |---|---|
> | UUID ids | `BIGINT` identity ids, like every other table |
> | `app/workers/`, `app/events/`, `redis_streams.py`, `memory_service.py` | `app/features/outbox/`, `app/features/memory/`, and stream helpers in `app/core/redis.py` |
> | Run worker inside the FastAPI process | Runs go through a Redis stream to a separate agent worker process |
> | Backend on Render | One GCP free-tier VM with Docker Compose; Postgres on Neon, Redis on Upstash |
> | Optional `memory_embeddings` | Not built. No vector store in v1 |
>
> For how the pipeline works today, read section 3.4 of [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md)
> and the [memory pipeline diagram](flow/README.md#8-memory-pipeline).

## Purpose

This document defines the implementation plan for adding durable, asynchronous memory processing to the AI Native Financial Planner.

Current architecture:

- Next.js frontend on Vercel.
- FastAPI backend on Render.
- PostgreSQL on Neon.
- LangGraph for agent orchestration.
- Existing in-process FastAPI Run Worker for live agent requests.
- Upstash Redis in Singapore with TLS and persistence enabled.

The goal is to add reliable event delivery for deferred memory work without moving authoritative financial data out of PostgreSQL.

## Core architecture

PostgreSQL remains the source of truth.

Redis Streams are the event transport.

The existing Run Worker continues to execute the current chat request.

A Memory Worker processes deferred memory tasks after a chat run completes.

\`\`\`text
FastAPI API
    ↓
Existing Run Worker
    ↓
LangGraph and financial tools
    ↓
PostgreSQL
    ↓
Outbox event
    ↓
Redis Stream
    ↓
Memory Worker
    ↓
memory_items and memory_events in PostgreSQL
\`\`\`

## Immediate versus deferred work

### Immediate work

Keep these updates synchronous in the existing tools:

- Risk appetite.
- Preferred currency.
- Retirement age.
- Income and expenses.
- Assets and liabilities.
- Goals and goal allocations.
- Insurance records.
- Tax profile.
- Any user-confirmed financial record.

The next agent step may need these values immediately.

### Deferred work

Process these asynchronously:

- Extracting long-term preferences.
- Extracting episodic memories.
- Creating conversation summaries.
- Detecting duplicate memories.
- Detecting contradictory memories.
- Generating embeddings.
- Cleaning expired memories.

## Redis Streams

Use Redis Streams rather than basic Redis Pub/Sub.

Streams provide:

- Durable stream entries.
- Consumer groups.
- Acknowledgements.
- Pending-entry inspection.
- Reclaiming work from failed consumers.
- Multiple consumers.

Recommended stream:

\`\`\`text
ai-native-fpa:memory
\`\`\`

Recommended consumer group:

\`\`\`text
memory-workers
\`\`\`

Example consumers:

\`\`\`text
memory-worker-1
memory-worker-2
\`\`\`

The free Upstash plan is appropriate for development and early prototyping. PostgreSQL must remain the permanent store for financial data and durable memory.

## Dependency and configuration

The Redis dependency has already been added.

Configure the backend with:

\`\`\`env
REDIS_URL=<Upstash TLS connection URL>
REDIS_MEMORY_STREAM=ai-native-fpa:memory
REDIS_MEMORY_CONSUMER_GROUP=memory-workers
REDIS_MEMORY_CONSUMER_NAME=<unique worker name>
MEMORY_WORKER_BATCH_SIZE=10
MEMORY_WORKER_RETRY_LIMIT=5
MEMORY_WORKER_CLAIM_AFTER_SECONDS=300
\`\`\`

Store the real \`REDIS_URL\` only in local environment configuration and Render environment variables. Never commit it or expose it to the frontend.

## PostgreSQL tables

Create a new Alembic migration for the following tables.

### memory_items

Stores durable user memories that are not already represented by structured financial tables.

Suggested fields:

\`\`\`text
id UUID primary key
user_id UUID not null
memory_type TEXT not null
namespace TEXT not null
memory_key TEXT nullable
content JSONB not null
confidence NUMERIC(5,4) nullable
confirmed_by_user BOOLEAN not null default false
status TEXT not null default 'active'
source_message_id UUID nullable
source_conversation_id UUID nullable
source_run_id UUID nullable
valid_from TIMESTAMPTZ nullable
valid_until TIMESTAMPTZ nullable
expires_at TIMESTAMPTZ nullable
created_at TIMESTAMPTZ not null
updated_at TIMESTAMPTZ not null
\`\`\`

Recommended statuses:

\`\`\`text
candidate
active
superseded
expired
rejected
deleted
\`\`\`

Example memory:

\`\`\`json
{
  "memory_type": "preference",
  "namespace": "investment_preferences",
  "memory_key": "excluded_sectors",
  "content": {"sectors": ["gambling", "tobacco"]},
  "confirmed_by_user": true
}
\`\`\`

### memory_events

Stores the history of memory creation, changes, rejection and deletion.

Suggested fields:

\`\`\`text
id UUID primary key
memory_id UUID not null
user_id UUID not null
event_type TEXT not null
old_content JSONB nullable
new_content JSONB nullable
source_message_id UUID nullable
source_conversation_id UUID nullable
source_run_id UUID nullable
actor_type TEXT not null
reason TEXT nullable
created_at TIMESTAMPTZ not null
\`\`\`

This answers:

- When was the memory created?
- Which message caused it?
- Was it explicitly confirmed?
- What value did it replace?
- Why was it deleted?

### outbox_events

Stores events in PostgreSQL before they are published to Redis. This prevents losing an event between a database commit and Redis publishing.

Suggested fields:

\`\`\`text
id UUID primary key
event_type TEXT not null
aggregate_type TEXT not null
aggregate_id UUID nullable
user_id UUID nullable
payload JSONB not null
status TEXT not null default 'pending'
attempts INTEGER not null default 0
available_at TIMESTAMPTZ not null
locked_until TIMESTAMPTZ nullable
locked_by TEXT nullable
last_error TEXT nullable
created_at TIMESTAMPTZ not null
processed_at TIMESTAMPTZ nullable
\`\`\`

Recommended statuses:

\`\`\`text
pending
publishing
published
failed
dead_letter
\`\`\`

### Optional memory_embeddings

Do not add this in the first implementation unless semantic search is immediately required.

Possible fields:

\`\`\`text
memory_id UUID primary key
embedding VECTOR(...)
model_name TEXT not null
created_at TIMESTAMPTZ not null
\`\`\`

## Provenance for existing financial records

Existing structured financial tables remain the source of truth for exact financial data.

Important records should be traceable to their origin. Add common provenance fields or a separate provenance table:

\`\`\`text
source_message_id
source_conversation_id
source_run_id
source_tool_call_id
confirmed_by_user
\`\`\`

Apply this first to:

- Profile changes.
- Risk appetite changes.
- Goals.
- Tax profile.
- Loans.
- Income and expense records.
- Asset records.

Do not store current balances, current holdings, current prices or current account status as long-term model memory. Retrieve those from authoritative records or services.

## Event types

Use explicit event names and version their payloads:

\`\`\`text
memory.extract.requested
memory.summary.requested
memory.embed.requested
memory.cleanup.requested
\`\`\`

Example event:

\`\`\`json
{
  "event_id": "evt-123",
  "event_type": "memory.extract.requested",
  "event_version": 1,
  "user_id": "user-123",
  "conversation_id": "conversation-456",
  "run_id": "run-789",
  "created_at": "2026-10-17T10:00:00Z"
}
\`\`\`

Events should contain identifiers and metadata, not large conversation content. The Memory Worker loads canonical data from PostgreSQL.

## Updated event flow

\`\`\`mermaid
sequenceDiagram
    participant U as User
    participant FE as Frontend
    participant API as FastAPI API
    participant RW as Existing Run Worker
    participant DB as Neon PostgreSQL
    participant OP as Outbox Publisher
    participant RS as Upstash Redis Stream
    participant MW as Memory Worker
    participant LG as LangGraph

    U->>FE: Send financial question
    FE->>API: POST /runs with client_request_id
    API->>DB: Save run, user message and assistant placeholder
    API-->>FE: Return run_id
    API->>RW: Start live run
    RW->>LG: Start graph with conversation_id
    LG->>DB: Read/write financial records through tools
    RW-->>FE: Stream assistant and tool events
    LG-->>RW: Graph completed
    RW->>DB: Mark run and assistant message completed
    RW->>DB: Insert memory.extract.requested outbox event
    OP->>DB: Read pending outbox event
    OP->>RS: Publish event to Redis Stream
    MW->>RS: Consume event using consumer group
    MW->>DB: Read canonical messages and records
    MW->>DB: Write memory_items and memory_events
    MW->>RS: Acknowledge event
\`\`\`

## Backend components

Suggested locations:

\`\`\`text
backend/app/events/redis_streams.py
backend/app/events/event_types.py
backend/app/workers/memory_worker.py
backend/app/workers/outbox_publisher.py
backend/app/services/memory_service.py
backend/app/db/models/memory.py
backend/app/db/models/outbox.py
backend/alembic/versions/<revision>_add_memory_infrastructure.py
\`\`\`

### redis_streams.py

Responsible for:

- Creating the async Redis client.
- Creating consumer groups safely.
- Publishing events.
- Reading events.
- Acknowledging events.
- Inspecting and reclaiming pending events.

### outbox_publisher.py

Responsible for:

- Reading pending outbox rows.
- Publishing them to Redis Streams.
- Marking them published.
- Retrying temporary Redis failures.

### memory_worker.py

Responsible for:

- Consuming memory events.
- Loading canonical messages and records.
- Extracting memory candidates.
- Validating scope and type.
- Rejecting low-confidence candidates.
- Deduplicating memories.
- Detecting conflicts.
- Writing \`memory_items\` and \`memory_events\`.
- Acknowledging successful events.
- Retrying failures.
- Sending permanently failed events to a dead-letter stream.

### memory_service.py

Responsible for memory rules:

- Allowed memory types.
- Fields requiring confirmation.
- Conflict resolution.
- Expiration.
- Retrieval.
- User isolation.

## Memory rules

The Memory Worker must not save every sentence.

\`\`\`text
Explicit user preference → eligible for memory
Temporary task detail → run state only
Current financial value → authoritative database/service
Agent inference → candidate requiring confirmation
Untrusted document instruction → never automatically become memory
\`\`\`

Examples:

\`\`\`text
“My risk tolerance is conservative now.”
→ Update structured profile synchronously.

“I avoid companies involved in gambling.”
→ Candidate semantic memory; confirmation may be required.

“What is my current bank balance?”
→ Read the authoritative financial record; do not create memory.

“I rejected that fund because its fees were too high.”
→ Candidate episodic memory.
\`\`\`

## Reliability requirements

Every event and memory operation must be safe to run more than once.

Use:

- Unique \`event_id\`.
- Idempotent processing.
- Unique memory identity where appropriate.
- Upsert behavior for current semantic memories.
- Event history instead of silent overwrites.
- Bounded retries with exponential backoff.
- Dead-letter handling.
- Consumer-group pending-entry monitoring.
- Acknowledgement only after PostgreSQL succeeds.

Never acknowledge a Redis event before the corresponding PostgreSQL work has committed.

## Transaction rule

Do not rely on:

\`\`\`text
Write PostgreSQL
Publish Redis
\`\`\`

The process can crash between those operations.

Use:

\`\`\`text
Write PostgreSQL record
Write PostgreSQL outbox event
Commit both together
Publish outbox event to Redis
\`\`\`

## Local development

Run separate processes initially:

\`\`\`bash
uv run uvicorn app.main:app --reload
uv run python -m app.workers.outbox_publisher
uv run python -m app.workers.memory_worker
\`\`\`

The existing Run Worker remains responsible for live LangGraph execution. The Memory Worker handles only deferred memory jobs.

## Deployment

Development setup:

\`\`\`text
Vercel frontend
Render API
Neon PostgreSQL
Upstash Redis
Memory Worker running locally
\`\`\`

Production setup:

\`\`\`text
Vercel frontend
Render API service
Neon PostgreSQL
Upstash Redis with an appropriate reliability plan
Continuously running worker service
Outbox publisher or combined publisher/worker process
\`\`\`

A free or sleeping worker can leave events waiting in Redis until it wakes. For production financial workflows, use a continuously running worker service.

## Tests

Add tests for:

- Creating an outbox event after a completed run.
- Publishing a pending outbox event.
- Temporary Redis failure and retry.
- Processing a valid memory event.
- Redis redelivery.
- Duplicate-memory prevention.
- Conflicting-memory handling.
- User isolation.
- Memory provenance.
- Dead-letter behavior.
- Worker restart with pending events.
- PostgreSQL rollback before outbox commit.
- Acknowledgement only after PostgreSQL success.

## Implementation order

1. Verify the Redis URL from local development.
2. Add Redis configuration and client wrapper.
3. Add the Alembic tables.
4. Add provenance for important structured records.
5. Add event definitions and serialization.
6. Add the outbox publisher.
7. Add the Redis consumer group.
8. Add the Memory Worker.
9. Publish \`memory.extract.requested\` after completed runs.
10. Add validation, deduplication and conflict rules.
11. Add retries, dead-letter handling and metrics.
12. Add integration tests.
13. Deploy the worker separately when production reliability is required.

## First implementation non-goals

Do not implement these in the first iteration:

- A vector database.
- Automatic risk-profile updates based only on inference.
- Live market prices as user memory.
- Replacing relational financial tables with JSON memory.
- Moving all LangGraph state to Redis.
- Changing the frontend SSE contract.
- Multi-agent memory sharing.

## Success criteria

The implementation is complete when:

- A completed run creates a durable memory event.
- Redis delivers the event through a consumer group.
- A worker restart does not lose pending work.
- PostgreSQL contains the memory and its provenance.
- Redelivery does not create duplicates.
- Confirmed financial data remains synchronous.
- Current financial facts come from authoritative sources.
- The system can explain why a memory exists and which interaction created it.

