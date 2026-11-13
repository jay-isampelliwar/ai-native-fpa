# Flow diagrams

Each diagram below is drawn by GitHub from its `.mmd` source file in this folder.
The source is the truth: change the `.mmd` file, then copy it here.

| # | Diagram | Shows | Source |
|---|---|---|---|
| 1 | [System architecture](#1-system-architecture) | Every process, store and outside service, and what moves between them. | [system-architecture.mmd](system-architecture.mmd) |
| 2 | [Agent graph](#2-agent-graph) | The LangGraph nodes one chat turn passes through. | [agent-graph.mmd](agent-graph.mmd) |
| 3 | [Run lifecycle](#3-run-lifecycle) | The states of one run, from the user's message to its end. | [run-lifecycle.mmd](run-lifecycle.mmd) |
| 4 | [Send a message](#4-send-a-message) | One chat turn across the API, Redis, the agent worker and Postgres. | [send-message-sequence.mmd](send-message-sequence.mmd) |
| 5 | [Cancel a run](#5-cancel-a-run) | How Stop reaches a run that lives in another process. | [cancel-run-sequence.mmd](cancel-run-sequence.mmd) |
| 6 | [Idempotent retry](#6-idempotent-retry) | Why a retried request never creates a second run. | [idempotent-retry-sequence.mmd](idempotent-retry-sequence.mmd) |
| 7 | [Approval before a risky tool call](#7-approval-before-a-risky-tool-call) | Pause, show a card, and resume on any worker. | [approval-sequence.mmd](approval-sequence.mmd) |
| 8 | [Memory pipeline](#8-memory-pipeline) | Outbox, Redis stream and the memory worker after a run completes. | [memory-pipeline.mmd](memory-pipeline.mmd) |
| 9 | [Document import](#9-document-import) | From an uploaded file to checked rows the user approves. | [document-import-flow.mmd](document-import-flow.mmd) |

To export every diagram as a PNG with the same name:

```bash
for f in docs/flow/*.mmd; do
  npx -y @mermaid-js/mermaid-cli -i "$f" -o "${f%.mmd}.png" -t dark -b "#1a1a1a" -s 2
done
```

## 1. System architecture

Every process, store and outside service, and what moves between them.

```mermaid
flowchart TD
    User([User in browser]) --> FE[Next.js app<br/>chat, cards, forms, import review]
    FE -- "/api/* through a Next.js rewrite" --> API[FastAPI API<br/>HTTP and SSE only]

    API -- "run, messages, approvals" --> PG[(PostgreSQL<br/>source of truth)]
    API -- "XADD run job" --> RunStream[(Redis stream<br/>runs)]
    RunStream -- "XREADGROUP" --> AgentWorker[Agent worker<br/>claims the run, keeps a heartbeat]
    AgentWorker --> Graph[LangGraph planner graph<br/>thread_id = conversation_id]
    Graph <--> Ckpt[(Postgres checkpointer)]
    Graph --> LLM[OpenAI chat model]
    Graph --> Tools[42 tools<br/>policy, approval, timeout, retry]
    Tools -- "one commit: write + idempotency row" --> PG
    Tools --> Ext[Tavily web search<br/>Yahoo index quotes]
    Tools <--> Cache[(Redis cache)]

    AgentWorker -- "save numbered event" --> PG
    AgentWorker -- "PUBLISH live event" --> PubSub[(Redis pub/sub)]
    PubSub -- "live events" --> API
    PG -- "replay missed events" --> API
    API -- "PUBLISH cancel" --> PubSub
    PubSub -- "cancel signal" --> AgentWorker

    AgentWorker -- "run completed + outbox row, same commit" --> PG
    Outbox[Outbox publisher] -- "claim pending rows" --> PG
    Outbox -- "XADD" --> MemStream[(Redis stream<br/>memory)]
    MemStream -- "XREADGROUP" --> MemWorker[Memory worker]
    MemWorker --> MemLLM[Small model<br/>structured output]
    MemWorker -- "memories + history, then XACK" --> PG

    AgentWorker -. "masked traces" .-> Langfuse[Langfuse]
```

## 2. Agent graph

The LangGraph nodes one chat turn passes through.

```mermaid
flowchart TD
    Start([New user message]) --> Repair[repair_history<br/>answer tool calls a stopped turn left open]
    Repair --> Intent[classify_intents<br/>keyword rules first, small model when unsure]
    Intent --> Memory[load_memories<br/>up to 50 active memories]
    Memory --> Agent[agent<br/>model call with only the tools the intents need]
    Agent -- "no tool calls" --> End([Turn ends])
    Agent -- "tool calls" --> Gate{approval_gate<br/>is any call risky?}
    Gate -- "safe calls" --> Tools[tools<br/>policy check, timeout, retry, write check]
    Gate -- "risky call" --> Pause[[interrupt<br/>wait for the user's card]]
    Pause -- "approved" --> Tools
    Pause -- "rejected" --> Agent
    Tools -- "results" --> Agent
    Tools -- "turn closed without a reply" --> End
```

## 3. Run lifecycle

The states of one run, from the user's message to its end.

```mermaid
flowchart TD
    A[User submits a message] --> B[Frontend generates client_request_id]
    B --> C[POST /api/runs]
    C --> D{Same client_request_id<br/>seen before?}
    D -- "Yes" --> D1[Return the existing run]
    D -- "No" --> E[One transaction:<br/>agent_runs row + user message + empty assistant message]
    E --> F[Run status: queued]
    F --> G[API adds a start job to the Redis run stream]
    G --> H[Agent worker claims the run in Postgres]
    H --> I[Run status: running<br/>heartbeat every 10 s]
    I --> J[LangGraph runs with conversation_id as thread_id]
    J --> K[Each event saved in run_events,<br/>then published on Redis]
    K --> L[Frontend reads the events as SSE]
    J --> M{How does the turn end?}
    M -- "Reply finished" --> N[Run status: completed<br/>outbox row in the same commit]
    M -- "Risky tool call" --> O[Run status: awaiting_approval<br/>approval card shown]
    O -- "User decides" --> P[Resume job on the Redis run stream]
    P --> H
    M -- "Cancel requested" --> Q[Run status: cancelled<br/>partial reply kept]
    M -- "Error or 90 s timeout" --> R[Run status: failed]
```

## 4. Send a message

One chat turn across the API, Redis, the agent worker and Postgres.

```mermaid
sequenceDiagram
    actor User
    participant FE as Frontend
    participant API as FastAPI API
    participant PG as PostgreSQL
    participant R as Redis
    participant W as Agent worker
    participant G as LangGraph

    User->>FE: Sends "What is my net worth?"
    FE->>FE: Generate client_request_id
    FE->>API: POST /api/runs
    API->>PG: Save run (queued), user message, empty assistant message
    API->>R: XADD start job to the run stream
    API-->>FE: 202 with run_id and conversation_id
    FE->>API: GET /api/runs/{run_id}/events (SSE)
    API->>R: SUBSCRIBE to the run's event channel
    R->>W: XREADGROUP delivers the job
    W->>PG: Claim the run (running, worker_id, heartbeat)
    W->>R: XACK the job
    W->>G: Start the graph with thread_id = conversation_id
    loop Each step of the turn
        G-->>W: Reply text or tool step
        W->>PG: Save the numbered event in run_events
        W->>R: PUBLISH the event
        R-->>API: Live event
        API-->>FE: SSE assistant.delta, tool.started, tool.finished, ui.block
    end
    G-->>W: Graph finished
    W->>PG: One commit: run completed, usage and cost, outbox row
    W->>R: PUBLISH run.completed
    API-->>FE: SSE run.completed
    FE-->>User: Show the final reply with its cards
```

## 5. Cancel a run

How Stop reaches a run that lives in another process.

```mermaid
sequenceDiagram
    participant FE as Frontend
    participant API as FastAPI API
    participant PG as PostgreSQL
    participant R as Redis
    participant W as Agent worker
    participant T as Run task

    FE->>API: POST /api/runs/{run_id}/cancel
    API->>PG: Status running to cancel_requested
    API->>R: PUBLISH on the run's cancel channel
    API-->>FE: 202 with status cancel_requested
    R-->>W: Cancel message
    W->>T: task.cancel()
    Note over PG,T: If the signal is missed, the task reads the saved status<br/>before every model call and tool call, and stops itself.
    T->>PG: Run cancelled, assistant message cancelled, open tool rows closed
    T->>PG: Save the run.cancelled event
    T->>R: PUBLISH run.cancelled
    R-->>API: Live event
    API-->>FE: SSE run.cancelled
    FE->>FE: Stop the loader and keep the partial reply
```

## 6. Idempotent retry

Why a retried request never creates a second run.

Image: [idempotent-retry-sequence.png](idempotent-retry-sequence.png)

```mermaid
sequenceDiagram
    participant FE as Frontend
    participant API as FastAPI API
    participant PG as PostgreSQL

    FE->>API: POST /api/runs with client_request_id req-001
    API->>PG: Create run-001
    API--xFE: Response lost on the network
    FE->>API: Retry POST /api/runs with the same req-001
    API->>PG: Find the run by (conversation_id, client_request_id)
    PG-->>API: run-001 already exists
    API-->>FE: Return run-001, no second run
    Note over API,PG: When two retries race, a unique index lets one insert win<br/>and the other request reads the winner.
```

## 7. Approval before a risky tool call

Pause, show a card, and resume on any worker.

```mermaid
sequenceDiagram
    actor User
    participant FE as Frontend
    participant API as FastAPI API
    participant PG as PostgreSQL
    participant R as Redis
    participant W as Agent worker
    participant G as LangGraph

    User->>FE: "Delete my rent expense"
    Note over FE,W: The run starts as in the send message flow
    G->>G: Model asks for delete_record
    G->>G: approval_gate: policy says destructive, build a preview
    G-->>W: interrupt() with the preview, state kept by the checkpointer
    W->>PG: One commit: run awaiting_approval, tool_approvals row (15 min expiry),<br/>approval.required event, run released
    W->>R: PUBLISH approval.required
    API-->>FE: SSE approval.required, then the stream ends
    FE-->>User: Card "Remove this expense?"
    User->>FE: Clicks "Yes, remove it"
    FE->>API: POST /api/runs/{run_id}/approvals/{approval_id}
    API->>PG: Lock the row, check owner, pending and expiry, save the decision
    API->>R: XADD resume job to the run stream
    R->>W: Any agent worker takes the job
    W->>G: Command(resume = answer)
    G->>G: Gate checks the same call id and the exact same arguments
    G->>PG: One commit: delete, read-back check, idempotency row
    G-->>W: Reply text
    W-->>FE: Events through Redis and SSE, then run.completed
```

## 8. Memory pipeline

Outbox, Redis stream and the memory worker after a run completes.

```mermaid
sequenceDiagram
    participant W as Agent worker
    participant PG as PostgreSQL
    participant O as Outbox publisher
    participant R as Redis memory stream
    participant M as Memory worker
    participant L as Small model

    W->>PG: One commit: run completed + outbox_events row
    loop Every second
        O->>PG: Lock due pending rows (FOR UPDATE SKIP LOCKED)
        O->>R: XADD the event
        O->>PG: Mark published (backoff on error, dead_letter after 5 tries)
    end
    R->>M: XREADGROUP under the worker's own consumer name
    M->>PG: Skip if this outbox event was already handled
    M->>PG: Load the run's messages and the user's active memories
    M->>L: Propose memories as structured output
    M->>M: Apply the rules: user's own words, confidence, no data a table owns
    M->>PG: Save memory_items + memory_events, then commit
    M->>R: XACK only after the commit
    Note over R,M: No ack on failure. After more than 5 deliveries<br/>the entry is copied to a dead stream.
```

## 9. Document import

From an uploaded file to checked rows the user approves.

```mermaid
flowchart TD
    U[User attaches a file in chat] --> Up[POST /api/documents<br/>size, type and hash checked]
    Up --> Dup{Same file<br/>uploaded before?}
    Dup -- "Yes" --> Old[Return the earlier upload]
    Dup -- "No" --> Read[Read into sheets for code<br/>and pages for the model]
    Read --> Kind{What is in the file?}
    Kind -- "Known family" --> Fixed[Parse with fixed rules]
    Kind -- "Header shape seen before" --> Saved[Parse with the saved column plan]
    Kind -- "New shape" --> Plan[Model sees headings and digit-masked samples,<br/>then proposes a column plan]
    Kind -- "Scan, photo or text page" --> Consent[Ask the user before the model reads the page]
    Fixed --> Check
    Saved --> Check
    Plan --> Check
    Consent --> Check
    Check[Code cleans every value and checks every row:<br/>needed fields, matches, duplicates, printed totals]
    Check --> Review[Review panel beside the chat:<br/>questions, edits, old against new]
    Review --> Import[User presses Import,<br/>or approves the card in chat]
    Import --> Write[Each row written through the domain services<br/>and read back]
    Write --> Done[Short note to the chat, undo stays possible]
```
