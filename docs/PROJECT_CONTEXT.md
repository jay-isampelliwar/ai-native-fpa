# Project Context — AI Native Financial Planner

Snapshot of the code on `main` at commit `16003e3` (17 October 2026).
Written as input for designing production-grade memory management for the agent.

Everything here was read from the code. Where a doc in the repo disagrees with the code, the code wins.
Those stale docs are listed in section 7.

---

## 1. Project overview

### 1.1 Purpose

A personal financial planner for Indian households, driven by chat.

- The user talks to an agent named **Preeti**.
- Preeti saves the user's financial details into Postgres as structured rows.
- Preeti answers questions from those rows and runs exact calculations through tools.
- The model is told never to do maths itself. Every number must come from a tool.

### 1.2 Financial use case

| Area | What is stored | Tables |
|---|---|---|
| Profile | Name, DOB, city, risk appetite, retirement age, life expectancy | `users` |
| Family | Spouse, children, parents, dependants | `family_members` |
| Cash flow | Regular income, regular expenses, one-off transactions | `income_sources`, `expenses`, `transactions` |
| Assets | Bank accounts, FD/RD, EPF/PPF/NPS/VPF, property, gold, vehicles | `bank_accounts`, `fixed_deposits`, `retirement_accounts`, `physical_assets` |
| Liabilities | Loans, credit cards | `loans`, `credit_cards` |
| Protection | Term, health, life, ULIP, vehicle policies | `insurance_policies` |
| Planning | Goals, goal-to-asset allocations, rate assumptions, tax regime | `goals`, `goal_allocations`, `assumptions`, `tax_profile` |
| Onboarding | Per-section status: pending / provided / none / declined | `data_coverage` |
| Market data (not wired to agent) | Stock and mutual fund master lists | `stocks`, `mutual_funds`, `holdings`, `sip_plans` |
| Tracking (not wired) | Net worth by date | `net_worth_snapshots` |

Currency is INR. Amounts are `Numeric(14, 2)`. Rates are `Numeric(5, 2)` percent values.

### 1.3 User types and roles

- **One role only:** a signed-in individual who owns their own data.
- No admin, advisor, family-sharing or organisation roles exist.
- Authorization is row scoping by `user_id`. There is no RBAC.
- Note: the system prompt says Preeti helps "finance teams and business owners".
  The tools and tables are personal finance. This mismatch is worth fixing.

### 1.4 Technologies

**Backend** — Python 3.13, managed with `uv` (`backend/pyproject.toml`)

| Concern | Choice |
|---|---|
| HTTP | FastAPI + Uvicorn |
| Agent | LangGraph `StateGraph` + `ToolNode`, LangChain tools |
| Model | OpenAI via `langchain-openai`, `CHAT_MODEL` default `gpt-4o-mini` |
| Database | PostgreSQL, SQLAlchemy 2 async, psycopg 3 driver |
| Migrations | Alembic, `0001` to `0013` |
| Auth | Argon2 (`pwdlib`) passwords, HS256 JWT (`pyjwt`) in an httpOnly cookie |
| Streaming | Server-sent events from an in-process pub/sub |
| Installed, not used yet | `langgraph-checkpoint-postgres`, `langsmith`, `tenacity`, `pycryptodome`, `openpyxl`, `pdfplumber` |

**Frontend** — Next.js 16.3.4, React 19.2.8, TypeScript, Tailwind 4, Recharts, Framer Motion, KaTeX, pnpm.

**Services** — Postgres and the OpenAI API. No Redis, no queue, no object storage, no vector store.

### 1.5 Repository structure

```
ai-native-fpa/
├── backend/
│   ├── app/
│   │   ├── main.py              FastAPI app, lifespan builds the graph
│   │   ├── api/                 router.py (mounts /api), deps.py (current user)
│   │   ├── core/config.py       Settings from env
│   │   ├── db/                  session.py (engine, Base), enums.py, models/
│   │   ├── agent/               graph.py, nodes.py, state.py, context.py, prompt.py, tools/
│   │   ├── features/            one folder per domain: router / service / repository / schemas
│   │   │   ├── auth/            signup, signin, signout, me
│   │   │   ├── runs/            POST /runs, SSE events, cancel, background worker
│   │   │   ├── conversations/   list, get, rename, soft delete
│   │   │   ├── records/         generic list / update / delete across all record kinds
│   │   │   ├── coverage/        what data is still missing
│   │   │   ├── analysis/        goal progress report
│   │   │   └── profile, cash_flow, assets, liabilities, protection, planning
│   │   ├── calc/                pure maths: money, growth, goals, cash_flow
│   │   └── services/llm.py      the one place a chat model is built
│   ├── alembic/versions/        0001 … 0013
│   ├── tests/calc/              only calc tests exist today
│   └── docs/ROADMAP.md          stale, describes the wiped backend
├── frontend/
│   ├── app/                     page.tsx (planner), signin/, signup/
│   ├── components/chat/         ChatWorkspace, MessageTimeline, Composer, HistoryPanel, …
│   ├── components/dashboard/    cards, all fed by mock data today
│   └── lib/                     api.ts, stream.ts, session.ts, useUploads.ts, mock/
├── docs/                        design.md (UI spec), flow/tool-events.md, folder.md (plan only)
└── sql/                         early hand-written table drafts + NSE/MF CSV seed data
```

### 1.6 Runtime and deployment

- Local development only. No Dockerfile, CI config or cloud deploy files exist.
- Backend runs as **one Uvicorn process**. Several parts depend on that (see 2.3).
- Frontend proxies `/api/*` and `/health` to `BACKEND_ORIGIN` (default `http://127.0.0.1:8000`).
  See `frontend/next.config.ts`. One origin, so no CORS on the backend.
- Settings read by the backend (`backend/app/core/config.py`):
  `OPENAI_API_KEY`, `CHAT_MODEL`, `DATABASE_URL`, `JWT_SECRET`, `TOKEN_TTL_MINUTES`, `COOKIE_SECURE`.
- `backend/.env.example` lists more keys (`ROUTER_MODEL`, `CHECKPOINT_ENCRYPTION_KEY`, …).
  These are leftovers. `Settings` ignores them.

---

## 2. Architecture

### 2.1 Diagram

```mermaid
flowchart TD
    User([User in browser]) --> FE[Next.js ChatWorkspace<br/>lib/stream.ts]
    FE -- "POST /api/runs" --> Proxy[Next rewrite /api/*]
    FE -- "GET /api/runs/:id/events (SSE)" --> Proxy
    Proxy --> API[FastAPI runs/router.py]

    API --> Auth[deps.get_current_user_id<br/>JWT from mosaic_session cookie]
    Auth --> RunSvc[RunService.create_run]
    RunSvc --> Conv[resolve_conversation<br/>create or load, owner check]
    RunSvc --> DB[(Postgres)]
    RunSvc -- "asyncio.create_task" --> Registry[RunRegistry<br/>in-process]
    Registry --> Worker[worker.execute_run]

    Worker --> Profile[ProfileService.get_profile]
    Profile --> DB
    Worker --> Graph[LangGraph planner_graph<br/>thread_id = conversation_id]
    Graph <--> Ckpt[(InMemorySaver<br/>process memory)]
    Graph --> Agent[run_agent node<br/>system prompt + profile + history]
    Agent --> LLM[OpenAI chat model]
    Agent -- tool_calls --> Tools[ToolNode: 22 tools]
    Tools --> DB
    Tools --> Agent

    Worker -- "tool rows, reply text every 1s, final status" --> DB
    Worker -- publish --> Events[RunEvents<br/>in-process pub/sub]
    Events -- SSE --> API
```

### 2.2 Request lifecycle

The frontend turns one user message into two HTTP calls.
Source: `frontend/lib/stream.ts`, `docs/flow/tool-events.md`.

**Step 1 — User sends a message**

- `createRun` posts `{conversation_id, client_request_id, message}` to `POST /api/runs`.
- `client_request_id` is a fresh UUID per message. The POST is retried on network error.
- `conversation_id` is `null` for a new chat.

**Step 2 — Authentication and authorization**

- `get_current_user_id` reads the `mosaic_session` cookie and decodes the JWT (`backend/app/api/deps.py`).
- Missing or invalid token → `401`. Token TTL is 7 days by default.
- There is no per-route permission check. Every query filters by `user_id` instead.
- Example: `RunRepository.get_conversation` requires `user_id` match and `status != deleted`.

**Step 3 — Conversation is identified**

- `RunService.resolve_conversation` in `backend/app/features/runs/service.py`.
- No id → create a `conversations` row, title from the first message (`titles.title_from`).
- Id given → load it for this user, else `404`.
- Idempotency: same `(conversation_id, client_request_id)` returns the existing run.
- One active run per conversation, enforced by partial unique index `uq_agent_runs_one_active`.
  A second message during a reply gets `409`.

**Step 4 — Persist the turn before running**

- `create_run_with_messages` inserts, in one transaction:
  - `agent_runs` row, status `queued`.
  - User `messages` row, `completed`, `content = {"text": ...}`.
  - Empty assistant `messages` row, status `streaming`.
- Sequence numbers come from `conversations.current_sequence`, bumped with one `UPDATE … RETURNING`.
- Commit, then `run_registry.start(...)` launches `execute_run` as an asyncio task.
- API answers `202 {run_id, conversation_id, status}`.

**Step 5 — Context is loaded and assembled**

- `worker.stream_events` loads the profile with `ProfileService.get_profile`.
  Only `BASIC_FIELDS`: name, email, DOB, city, risk appetite, retirement age, life expectancy.
- It builds `PlannerContext(user_id, profile)` — frozen, read-only, per run.
- Graph config: `{"configurable": {"thread_id": str(conversation_id)}}`.
- Graph input is only the new `HumanMessage`. Earlier turns come from the **checkpointer**, not from `messages`.
- `run_agent` in `backend/app/agent/nodes.py` builds the model input each step:
  - `SystemMessage` = `SYSTEM_BASE_INSTRUCTIONS` + `TOOL_USAGE_INSTRUCTIONS` + profile block + today's date.
  - Then every message in `state["messages"]`, with no trimming.
- All other financial data is not in the prompt. The model must call `list_records`.

**Step 6 — Model is called**

- `llm_service.with_tools(ALL_TOOLS).astream(messages)` — OpenAI, streaming.
- All 22 tools are bound on every call.
- Chunks are added together into one `AIMessage` and returned to state.

**Step 7 — Tools are selected and executed**

- Graph: `START → agent → (tools_condition) → tools → agent → … → END`.
- Loop limit is LangGraph's default recursion limit. No custom cap.
- Tools read `runtime.context.user_id`, so a tool can only touch the caller's rows.
- Each tool opens its own short DB session via `SessionLocal()`.
- Tools return plain strings, for example `"Saved loan with id 7: …"` or `"Not saved. Required details missing …"`.
- Tool groups:

| Group | Tools |
|---|---|
| Read / onboarding | `get_missing_data`, `update_data_coverage`, `list_records` |
| Change | `update_record`, `delete_record` (prompt asks user to confirm first) |
| Save | `update_profile`, `add_family_member`, `add_income_source`, `add_expense`, `add_transaction`, `add_bank_account`, `add_fixed_deposit`, `add_retirement_account`, `add_physical_asset`, `add_loan`, `add_credit_card`, `add_insurance_policy`, `add_goal`, `allocate_goal`, `set_assumption`, `set_tax_profile` |
| Calculate | `check_goal_progress` |

- Delete confirmation is a prompt rule only. Nothing in code blocks an unconfirmed delete.
- `list_records` has a 5 second `asyncio.sleep` marked `TODO(orb-demo)`. It must go before production.

**Step 8 — Response is streamed**

- Graph runs with `stream_mode=["messages", "updates"]`.
- `updates` with `AIMessage.tool_calls` → `tool.started` event.
- `updates` with `ToolMessage` → `tool.finished` event, status `ok` or `error`.
- `messages` chunks with text → `assistant.delta` event.
- Events go to `RunEvents.publish`, which copies them into every listener queue.
- `GET /api/runs/{id}/events` streams them as SSE until `run.completed`, `run.failed` or `run.cancelled`.
- A late listener gets the tool steps so far plus an `assistant.snapshot` of text so far.
- If the run already ended, the route returns one final event built from the DB.

**Step 9 — Messages, events and state are persisted**

| What | Where | When |
|---|---|---|
| User message | `messages` | Before the run starts |
| Assistant text | `messages.content.text` | Every 1 second during streaming, and at the end |
| Run status | `agent_runs` | queued → running → completed / failed / cancelled |
| Tool call | `tool_calls` (args JSONB) | When the model asks for it, status `running` |
| Tool result | `tool_calls.output = {"text": …}` or `error_text` | When the tool returns |
| Financial data | domain tables | Inside the tool, own transaction |
| Full LangGraph state | `InMemorySaver` | After every node, **in process memory only** |
| Live text and tool steps | `RunEvents.texts` / `.tools` | Process memory, cleared on final event |

- On cancel: run → `cancel_requested`, task cancelled, run and message end as `cancelled`, open tool rows closed.
- On error: run `failed` with `failure_code="agent_error"`, user sees a generic message.

**Step 10 — Background jobs**

- There is no job queue and no scheduler.
- The only background work is the per-run asyncio task in the same process.
- On startup, `fail_orphaned_runs` marks every active run as `failed` (`worker_restart`).
- No summarisation, embedding, extraction or cleanup job runs after a turn.

### 2.3 Single-process assumptions

These break as soon as there are two Uvicorn workers or two hosts:

- `InMemorySaver` — conversation memory lives in one process.
- `RunRegistry` — cancel only works in the process that runs the task.
- `RunEvents` — SSE listener must hit the same process as the worker.
- `fail_orphaned_runs` — fails runs that other live workers own (a TODO in the code says so).
- `agent_runs.worker_id` and `heartbeat_at` exist but are never written.

---

## 3. Current memory model

The project has three kinds of "memory". They are stored in different places and do not sync.

### 3.1 Long-term structured memory (Postgres, durable)

- This is what the prompt calls "your memory".
- Domain tables in section 1.2, written only through tools.
- Every row has `user_id`, so it is per user and shared across all conversations.
- Read path 1: basic profile is pushed into the system prompt every model call.
- Read path 2: everything else is pulled by `list_records(kind)`.
- `data_coverage` remembers which sections were asked, answered, declined or empty.

Example flow — user says "I have an HDFC home loan":

- Model calls `add_loan` with what the user gave.
- `save_record` in `agent/tools/common.py` finds missing required fields.
- Tool returns `"Not saved. Required details missing for this loan: …"`.
- Model asks the user. Next turn it calls `add_loan` again with everything.
- Row lands in `loans`. Coverage section `loans` becomes provided.

### 3.2 Short-term conversation memory (LangGraph checkpointer, not durable)

- Built in `backend/app/main.py`: `build_planner_graph(InMemorySaver())`.
- Keyed by `thread_id = conversation_id`.
- Holds every `HumanMessage`, `AIMessage` (with tool calls) and `ToolMessage` of the thread.
- This is the **only** history the model sees. The `messages` table is never read back into the graph.

### 3.3 Display history (Postgres, durable)

- `messages` and `tool_calls`, read by `GET /api/conversations/{id}` for the UI.
- Only user and assistant text is returned. Tool rows become `tools[]` on the assistant message.

---

## 4. Gaps relevant to memory management

Ordered by impact.

**4.1 Conversation memory is lost on every restart**

- Restart → `InMemorySaver` is empty.
- UI still shows the full chat from `messages`.
- Model sees only the new message. Preeti forgets the chat but the user does not.

**4.2 History grows without limit**

- `run_agent` sends `[system, *state["messages"]]` every step.
- Tool outputs (full `list_records` dumps) stay in state forever.
- Long chats will hit the context window and cost more on every turn.
- Docstrings in `graph.py` and `nodes.py` mention a "compaction node". It does not exist.

**4.3 Summary columns exist but are unused**

- `conversations.summary` and `conversations.summarized_through_sequence` — never written or read.
- `PlannerState.turn_count` — declared, never set.

**4.4 Cancelled or failed runs can leave a broken thread**

- Cancel during a tool step can leave an `AIMessage` with `tool_calls` and no matching `ToolMessage`.
- OpenAI rejects that history on the next call. The next turn in that chat may fail.
- Not confirmed by a test. Worth checking first.

**4.5 Two histories can disagree**

- `messages` has the partial text of a cancelled reply. The checkpoint may not.
- Tool output in `tool_calls.output` is a string copy, not linked to the checkpoint.
- There is no single source of truth to rebuild context from.

**4.6 Long-term memory has no history or provenance**

- `update_record` and `delete_record` overwrite or remove rows. No audit log, no versions.
- No record of which conversation, run or tool call created a row.
- `conversations.user_id` has no foreign key to `users`.

**4.7 No unstructured or semantic memory**

- Preferences, opinions or facts with no table ("I want to retire in Goa") are not saved anywhere durable.
- No embeddings, no vector store, no retrieval across conversations.

**4.8 Prompt context is fixed**

- Profile is injected every time. Other data needs a tool call every time.
- No selection of relevant data per question. No token budgeting.
- All 22 tool schemas are sent on every call.

**4.9 Privacy and retention**

- Conversation delete is soft: `status = deleted`, `deleted_at` set. Messages, tool rows and checkpoint stay.
- No account delete, export or retention rule.
- Tool arguments and outputs with financial data are stored as plain JSONB.
- `CHECKPOINT_ENCRYPTION_KEY` in `.env.example` hints at a plan. Nothing reads it.

**4.10 Scaling**

- See 2.3. Any durable checkpointer must also work with more than one worker.

---

## 5. Data model for conversations and runs

```mermaid
erDiagram
    users ||--o{ conversations : "user_id (no FK)"
    conversations ||--o{ messages : has
    conversations ||--o{ agent_runs : has
    agent_runs ||--o{ messages : "run_id"
    agent_runs ||--o{ tool_calls : "run_id"
    messages ||--o{ tool_calls : "message_id"
    users ||--o{ loans : "user_id"
    users ||--|| data_coverage : "user_id"
```

| Table | Key columns | Notes |
|---|---|---|
| `conversations` | `id`, `user_id`, `title`, `status`, `current_sequence`, `summary`, `summarized_through_sequence`, `deleted_at` | Summary columns unused |
| `messages` | `conversation_id`, `run_id`, `sequence_number`, `role`, `status`, `content` JSONB | Unique on `(conversation_id, sequence_number)`. Only `{"text"}` used |
| `agent_runs` | `conversation_id`, `client_request_id`, `status`, `failure_code`, timestamps, `worker_id`, `heartbeat_at`, `version` | One active run per conversation |
| `tool_calls` | `conversation_id`, `message_id`, `run_id`, `tool_call_id`, `tool_name`, `arguments`, `status`, `output`, `error_text` | Unique on `(conversation_id, tool_call_id)` |

---

## 6. Frontend notes that touch memory

- `lib/session.ts` keeps the signed-in user in browser memory, from `GET /api/auth/me`.
- `lib/stream.ts` follows a live run again after reload, using `active_run` from the conversation detail.
- The dashboard reads `lib/mock/data.ts`. It is not connected to the user's saved data.
- `lib/api.ts` and `lib/useUploads.ts` call `/api/v1/documents/*` for file import.
  Those routes do not exist in the current backend. Upload is not working end to end.

---

## 7. Stale or misleading files

| File | Why it misleads |
|---|---|
| `backend/docs/ROADMAP.md` | Describes the old, wiped backend (`/api/v1/planner/messages`, 24 tables, 132 tests) |
| `docs/folder.md` | A planned layout (`modules/`, `workers/`, `redis_client.py`) that was never built |
| `backend/.env.example` | Keys `Settings` does not read |
| `sql/*.sql` | Early drafts with UUID keys. Alembic is the real schema |
| Docstrings in `agent/graph.py`, `agent/nodes.py` | Mention a compaction node that does not exist |

---

## 8. Facts to keep when adding memory

- The model must never do maths. Numbers come from tools. Keep this in any summary design.
- The model must call saved data "memory", never "database" or "record", in replies.
- Tools must keep scoping by `runtime.context.user_id`.
- `client_request_id` idempotency and one-active-run-per-conversation must keep working.
- The SSE event names in `features/runs/events.py` are a contract with the frontend.
