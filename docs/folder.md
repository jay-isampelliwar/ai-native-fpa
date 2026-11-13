# Folder map

Where things live, and the rule each folder follows.

## Backend

```
backend/
├── app/
│   ├── main.py                 FastAPI app: mounts the routes, starts no background task
│   ├── api/
│   │   ├── router.py           gathers every feature's routes under /api
│   │   └── deps.py             who is calling, read from the session cookie
│   ├── core/
│   │   ├── config.py           every setting, limit and timeout
│   │   └── redis.py            shared Redis client and stream helpers
│   ├── db/
│   │   ├── session.py          async engine, session factory, declarative base
│   │   ├── enums.py            enum values stored in the tables
│   │   └── models/             one file per group of tables
│   ├── agent/
│   │   ├── graph.py            wires the nodes of the planner graph
│   │   ├── nodes.py            load memories, call the model, wrap up at a limit
│   │   ├── intents.py          keyword rules, then a small model, then a fallback
│   │   ├── repair.py           fixes a history a stopped turn left broken
│   │   ├── approval.py         the approval gate and the card previews
│   │   ├── budget.py           per-turn model, tool and token limits, and cost
│   │   ├── cancellation.py     the saved-cancel check before model and tool calls
│   │   ├── blocks.py           typed UI cards built from exact tool data
│   │   ├── cards.py, forms.py  plain-words pieces for cards, and the input forms
│   │   ├── prompt.py           the system prompt
│   │   ├── state.py, context.py, checkpointer.py
│   │   └── tools/
│   │       ├── __init__.py     ALL_TOOLS, the list the graph gets
│   │       ├── policies.py     risk level and approval rule for every tool
│   │       ├── wrapper.py      the step every tool call runs through
│   │       ├── limits.py       time limits and retry rules
│   │       ├── operations.py   run_write: idempotency guard, write check, one commit
│   │       ├── results.py      the one shape every tool returns
│   │       ├── selection.py    which tools each intent gets
│   │       ├── common.py       steps every save tool shares
│   │       └── records.py, profile.py, cash_flow.py, assets.py, investments.py,
│   │           liabilities.py, protection.py, planning.py, analysis.py, overview.py,
│   │           market.py, indices.py, web.py, forms.py, imports.py, labels.py
│   ├── features/               one folder per feature
│   │   ├── auth/               sign up, sign in, sign out, me
│   │   ├── runs/               router, service, repository, schemas, plus:
│   │   │                       jobs.py (queue), consumer.py (agent worker process),
│   │   │                       worker.py (one run), publisher.py (events),
│   │   │                       stream.py (SSE replay and live), events.py, registry.py
│   │   ├── approvals/          decide a card; auto-reject, cancel and expire
│   │   ├── operations/         saved results of write tool calls
│   │   ├── conversations/      list, open, rename, soft delete
│   │   ├── records/            generic list, update and delete for any owned table
│   │   ├── coverage/           which sections of the user's data are still missing
│   │   ├── profile/, cash_flow/, assets/, liabilities/, protection/, planning/
│   │   ├── investments/        holdings, SIPs, and read-only market queries
│   │   ├── analysis/           goal progress report
│   │   ├── overview/           net worth, asset split, cash flow, health score
│   │   ├── indices/            index quotes from Yahoo, cached in Redis
│   │   ├── web_search/         Tavily search, Redis cache with a lock, page previews
│   │   ├── voice/              speech to text
│   │   ├── documents/          upload, read, parse, check, review, write, undo
│   │   │   └── families/       known file layouts, read by fixed rules
│   │   ├── outbox/             outbox repository and the publisher process
│   │   └── memory/             extractor, prompt, rules, repository, worker process
│   ├── calc/                   pure money maths: no database, no model
│   ├── observability/          Langfuse client, masking, manual spans
│   └── services/               llm.py (the one model factory), verify.py (the write check)
├── alembic/versions/           0001 … 0025
├── scripts/market_data/        download, build and load stock and fund data
├── tests/                      agent/, approvals/, tools/, documents/, runs/, memory/,
│                               outbox/, observability/, calc/, core/, voice/, integration/
├── deploy/                     Caddyfile, setup-vm.sh, README.md
├── Dockerfile
├── docker-compose.yml          production stack
└── pyproject.toml, uv.lock
```

### Rules the backend follows

- A feature folder has `router.py`, `service.py`, `repository.py` and `schemas.py`. It adds more files only when it needs them.
- A router reads the request and calls a service. It holds no business rule.
- A service holds the rules. It calls `flush()`, never `commit()`.
- A repository holds the SQL. It makes no decision.
- A tool is thin: it checks input, calls a service through `run_write`, and returns a typed result.
- A background loop is its own process and its own Compose service. The API starts none.

Example, saving a loan:

- `add_loan` in [agent/tools/liabilities.py](../backend/app/agent/tools/liabilities.py) gets the model's arguments.
- `run_write` in [agent/tools/operations.py](../backend/app/agent/tools/operations.py) checks the call was not done before.
- The service in [features/liabilities/service.py](../backend/app/features/liabilities/service.py) applies the rules and flushes.
- The repository in [features/liabilities/repository.py](../backend/app/features/liabilities/repository.py) runs the insert.
- The row is read back and compared, then one commit saves the loan and its `tool_operations` row.

## Frontend

```
frontend/
├── app/
│   ├── page.tsx                the planner
│   ├── signin/, signup/
│   ├── layout.tsx, globals.css
├── components/
│   ├── PlannerShell.tsx        page frame
│   ├── chat/                   ChatWorkspace, MessageTimeline, Reply, ChatComposer,
│   │                           ApprovalCard, FileChips, ImportReview, HistoryPanel, VoiceBars
│   ├── blocks/                 BlockView picks one card per UI block type
│   ├── imports/                ImportPanel, RowCard, QuestionStepper, MappingStep
│   ├── forms/                  FormPanel
│   ├── auth/, ui/, icons/
│   └── dashboard/              cards on mock data, hidden for now
├── lib/
│   ├── api.ts                  typed API client
│   ├── stream.ts               SSE reader with reconnect and replay
│   ├── types.ts                event and block types shared with the backend
│   ├── cards.ts                splits a reply at its card markers
│   ├── session.ts, forms.ts, imports.ts, format.ts, theme.tsx
│   └── useUploads.ts, useVoiceInput.ts, useCountUp.ts
├── next.config.ts              rewrites /api/* to the backend, so one origin
└── DESIGN.md                   design system
```

## Docs

```
docs/
├── PROJECT_CONTEXT.md                  the deep reference
├── document-import.md                  design of the document import
├── folder.md                           this file
├── MEMORY_IMPLEMENTATION_HANDOFF.md    the original memory plan
├── design.md                           the brief the first UI was built from
├── chat-components.html                static preview of the chat cards
└── flow/                               flow diagrams, each with its Mermaid source
```
