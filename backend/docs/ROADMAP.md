# AI Native Financial Planner — state and what is left

Written 05 September 2026, updated the same day when the backend was completed. This is the
pick-up-later document: what exists, what was decided, and what is still open.

---

## Where the build is now

**The backend is complete. Phases 1 through 5 of the implementation guide are built and verified.**

| | |
|---|---|
| Python modules | 89 (excluding `__init__.py`) |
| Tests | 132 passing, 2 skipped (live-model evals) |
| HTTP endpoints | 30 |
| Frontend | 19 files, Next 16.3.4 + Tailwind 4 |
| Database | PostgreSQL `fpa` on `localhost:5433`, 24 tables |
| Migration | Alembic at revision `0003` |

Only the frontend remains.

### What works end to end

1. A request enters `POST /api/v1/planner/messages`.
2. The manual top-level LangGraph authenticates, routes to a skill, checks scopes,
   executes, validates, audits, and replies.
3. Four skills are registered in three different shapes:
   - `cashflow_summary` — deterministic, no model call
   - `expense_investigation` — ReAct agent, tools bound to the authenticated user
   - `goal_planning` — manual subgraph, four nodes, no model call
   - `sip_modification` — manual subgraph, the only skill that can reach a write
4. Records entered through `/api/v1/records/*` immediately change what the planner says.
5. Every answer carries `evidence_ids`, `calculator_versions` and typed UI `blocks`; every run,
   including refusals, writes an `audit_records` row.
6. `POST /api/v1/planner/messages/stream` streams the same answer as SSE, one event per node.
7. Uploading a CSV statement stages rows for reconciliation; only accepted rows commit, under one
   `import_batch_id`.
8. `GET /api/v1/alerts` evaluates seven rules against the current position and returns findings
   with evidence, ordered so what needs deciding comes first.

### Verified behaviours worth not breaking

- A caller missing one required scope is stopped **before the skill executes** — `result`
  is never set.
- An unregistered skill name is refused before permissions are even checked.
- Tools close over `user_id`; it appears in no tool schema the model fills in.
- Archiving removes a record from calculations but leaves the row readable.
- Ownership failures return 404, never 403.
- Checkpoints are AES-GCM encrypted; a tampered one fails to load rather than resuming.
- There is **no in-memory checkpointer fallback** — if PostgreSQL is down, the app does
  not start.
- A proposed SIP change does not touch the database until approved; the stored approval keeps the
  exact before and after the user was shown.
- `route_by_risk` pauses only when the definition requires approval **and** a durable proposal
  exists — a refusal from a write-capable skill never asks a user to approve nothing.
- A block citing evidence the skill did not read fails validation.
- Extraction stages rows; the record tables are untouched until a person accepts them.
- A salary credit in a bank statement is skipped, never imported as negative spending.
- The same file uploaded twice returns the first import; a transaction already on record is flagged
  as a duplicate rather than silently doubled.

### Running it

```bash
cd backend
uv run --python 3.13 pytest tests -q
uv run --python 3.13 uvicorn app.main:app --reload
```

System `python3` is 3.9. Always go through `uv run --python 3.13`.

---

## Open decisions

| Decision | Status |
|---|---|
| **Holdings valuation** — cost basis vs. a `price_snapshots` table vs. live feed | Open. Currently cost basis, flagged as `valued_at_cost` in every response. |
| **Document extraction approach** — deterministic parsers, LLM vision, or hybrid | Open. Deliberately not assumed. |

Everything below assumes these are still unanswered.

---

## Small things outstanding

- `route_request` has never run against a real model — every test stubs it. One live
  check with a real `OPENAI_API_KEY` is worth doing before trusting routing quality.
- `pending_approvals` table exists and nothing writes to it yet (that is Phase 5).
- `.env` currently has a placeholder `OPENAI_API_KEY`.

---

## Phase 3 — Document import — BUILT

**Exit condition met:** imports reconcile before committing records.

Documents in scope, all four: bank statements (PDF/CSV), CAS from CAMS/KFintech, broker
statements and contract notes, salary slips.

The rule that must not bend: extraction never writes straight into the record tables. Rows
are staged, a person reconciles them, and only then are they committed with an
`import_batch_id` so a bad import can be reversed as a unit.

```
upload → detect format → extract → staged rows + confidence
       → user reconciles → approve → commit (tagged import_batch_id)
```

Roughly 20–25 backend files:

- documents router + schemas, storage adapter
- `document_imports` and `staged_rows` tables, migration `0002`
- format dispatcher plus one parser per document type
- reconciliation service and endpoints
- commit path and the approval gate
- parser fixtures per format, reconcile-flow tests

The file count moves with the extraction decision: deterministic parsers mean more files
but simpler ones; LLM-vision-for-everything is fewer files and a much heavier eval suite.

---

## Phase 4 — Proactive planner — BUILT

**Exit condition met:** alerts cite fresh verified data with evidence ids and calculator versions.

Alerts that fire without being asked — cash shortfall ahead, goal drift, FD maturity
approaching, SIP debit failing. Each one has to cite the records behind it, which means
they run through skills rather than through a cron job with its own SQL.

Roughly 10–12 files: a scheduler, alert definitions, a notification table and delivery
adapter, plus skills for each alert kind.

---

## Phase 5 — Controlled actions — BUILT, pending compliance review

**Exit condition partly met:** the write path, approval binding and audit trail are complete. The
SEBI review the implementation guide requires before shipping recommendation or execution
capability has **not** been done and is not a coding task.

This is where `controlled_write` stops being a stub and `pending_approvals` gets used.
The graph shape is already correct and enforced — the only edge into `controlled_write`
comes from `request_approval` — so this phase fills in the tools rather than rewiring.

Includes: approval token binding and expiry, idempotent write tools, before/after state
captured as what the user was shown, and the SEBI review the implementation guide flags
before any recommendation or execution capability ships.

Roughly 12–15 files.

---

## v1 frontend — new scope, agreed 05 September 2026

Not started. Decided:

- **Dynamic UI means backend-returned typed blocks.** Skills return a `blocks` array
  (`kpi`, `table`, `chart`, `approval_card`, `text`); the frontend renders them from a
  fixed component registry. The model never emits markup, so every rendered number still
  traces to an `evidence_id`.
- **Stack:** Next.js + TypeScript + Tailwind.
- **Features:** chat, document upload, reconciliation screens, record entry forms.

| Area | Files | Notes |
|---|---|---|
| Backend — UI blocks | ~8 | `blocks.py`, `SkillResult.blocks`, 3 skills emitting blocks, planner schemas |
| Backend — streaming | ~2 | SSE so the chat renders as the graph runs |
| Frontend — scaffold | ~6 | Next config, Tailwind, API client, generated types |
| Frontend — chat | ~5 | page, message list, composer, streaming hook, evidence drawer |
| Frontend — block registry | ~7 | `BlockRenderer` plus one component per block type |
| Frontend — upload & reconcile | ~6 | dropzone, progress, staged-rows table, inline edit, commit |
| Frontend — record forms | ~5 | income, expense, EMI, SIP, goal |

Backend additions ≈ 10, frontend ≈ 29.

Phase 3 and the frontend overlap heavily — upload, extract and reconcile need both halves
— so they are better built together than back to back.

---

## Total remaining

Roughly **70–80 files** across Phases 3–5 and the frontend, with the extraction decision
being the largest single variable.

## Suggested order

1. Decide extraction approach and holdings valuation.
2. UI blocks in the backend (small, unblocks all frontend work).
3. Frontend scaffold + chat against the three existing skills.
4. Phase 3 upload → extract → reconcile, frontend and backend together.
5. Phase 5 controlled writes.
6. Phase 4 proactive alerts last — it is the only phase nothing else depends on.

---

## What was built on 05 September 2026 (backend completion)

### UI blocks
`app/ui/blocks.py` defines the closed vocabulary — `text`, `kpi`, `table`, `chart`, `callout`,
`approval_card`. Evidence is attached **per block**, not per result, so a user can tap one figure
and see the rows behind that figure, and the validator can reject a block citing evidence the skill
never read. `display` (backend-formatted) is separate from `value` (raw `Decimal`) so currency
formatting lives in one place and charts still scale on real numbers.

### Streaming
`POST /api/v1/planner/messages/stream` emits one `progress` event per graph node, then a `done`
event carrying the identical body the non-streaming endpoint returns. A client that ignores every
intermediate event is still correct.

### Controlled writes
`app/tools/controlled_write/writes.py` holds the only code that changes a record on a user's
behalf. Five preconditions, all checked: authenticated user, authorization decision, approved
pending action, idempotency key, audit context. Plus a freshness check — if the row changed after
the proposal was shown, the write is refused rather than discarding the user's newer edit.

`app/approvals/store.py` records what the user was shown (`before_state` / `after_state`), binds the
decision to the person and the moment, and expires proposals on read rather than by a sweeper.

### Document import
- `app/storage/files.py` — storage behind a protocol; keys are generated, never derived from the
  user-supplied filename
- `app/extraction/base.py` — the extractor contract: bytes in, candidate rows with confidence out
- `app/extraction/bank_csv.py` — deterministic CSV parser, header-alias matching, day-first dates,
  credits skipped
- `app/extraction/dispatcher.py` — first extractor that claims the document wins; an unknown format
  is a stated refusal, never a guess
- `app/services/jobs.py` — the background runner, since extraction outlives a request and is not a
  graph run
- `app/services/import_service.py` — staging, duplicate detection at two levels, and a commit that
  is all-or-nothing under one batch id

### Alerts
`app/alerts/rules.py` — seven pure rules over one snapshot. `app/alerts/service.py` fetches once so
no two rules can disagree about the same month. Computed on request, never stored: a stored alert
goes stale and telling someone their goal is drifting after they fixed it costs more trust than
silence.

---

## Still open

| Item | Status |
|---|---|
| **Extraction approach** | **Decided 05 Sep 2026 and built** — template families with an AI-assisted mapping path for unknown layouts. See the section below. |
| **Holdings valuation** | Imported statements now carry the `current_value` and `last_price` the *statement stated*, dated by `as_of`. Nothing refreshes them — a live figure still needs a price feed. `goals_repository` continues to value at cost. |
| **SEBI compliance review** | Required before shipping advice or execution. Not a coding task. |
| **Live routing check** | `route_request` has still never run against a real model — every test stubs it. |

## Frontend — built 05 September 2026

Farline's theme, layout and component idiom, adapted to this backend's API. Stock Next 16.3.4 + pnpm;
the backend is reached through a `next.config` rewrite so there is one origin and no CORS.

| Route | Component | What it does |
|---|---|---|
| `/` | `ChatPanel` | SSE-streamed conversation, typed blocks, approvals answered inline |
| `/portfolio` | `Portfolio` | Holdings totals, asset-type split, positions, goal funding |
| `/import` | `Import` | Upload → poll → reconcile → commit, plus the mapping path |
| `/alerts` | `Alerts` | What the planner noticed, ordered by severity |

`components/blocks.tsx` is the closed rendering vocabulary — `text`, `kpi`, `table`, `chart`,
`callout`, `approval_card` — with an exhaustive switch, so adding a block type to the backend without
adding it here is a TypeScript error rather than a missing element.

Copied verbatim from Farline: `app/globals.css`, `lib/chart.ts`, `public/favicon.png`, `public/og.png`,
and the `layout.tsx` metadata (name, tagline, OG image). Dropped: `PlanReport`, `PlanWorkbench`,
`PlanWorkspace`, `ForecastCanvas`, `ScenarioLab` — they render a `PlanSummary` this backend does not
produce.

Two things learned the hard way and worth not re-learning:

- **A render prop cannot cross the server/client boundary.** `<Shell>{(id) => ...}</Shell>` 500s,
  because a function is not serialisable into the RSC payload. The user id reaches pages through
  context instead.
- **`GROUP BY` on a repeated `coalesce`** emits two separate bind parameters, and PostgreSQL then sees
  two different expressions and rejects the grouping. Label the expression and group by the label.

### Backend additions for the frontend

`GET /api/v1/assets/holdings` — the portfolio read, which did not exist. `app/repositories/holdings_repository.py`
plus `tests/test_holdings_read.py`.

## What remains to build

Nothing structural. Previously estimated as ~29 files:

| Area | Files |
|---|---|
| Scaffold | ~6 — Next config, Tailwind, API client, types generated from the OpenAPI schema |
| Chat | ~5 — page, message list, composer, SSE hook, evidence drawer |
| Block registry | ~7 — `BlockRenderer` plus one component per block type |
| Upload & reconcile | ~6 — dropzone, progress polling, staged-rows table, inline edit, commit |
| Record forms | ~5 — income, expense, EMI, SIP, goal |

Every backend endpoint the frontend needs already exists and is tested.


---

## Extraction pipeline — decided and built, 05 September 2026

**A parser per template family, not per file.** Unknown layouts cost one confirmation, not one per month.

```
Upload → hash/duplicate check → fingerprint layout
      ├── known template  → deterministic parser → staging
      └── unknown         → AI proposes mapping → validate → user confirms
                          → mapping saved as template → deterministic parser → staging
      → reconcile totals → user accepts rows → commit → PostgreSQL
```

### Common holdings model

`owner → account → instrument → ISIN → asset_type → quantity → average_cost → invested_value →
current_value → source → as_of_date`, plus `identifier_type` and `import_batch_id`.

`identifier_type` exists because **two of the three real formats carry no ISIN at all**. A holding
keyed on a scheme name is weaker evidence than one keyed on an ISIN, and the row says which it is
rather than treating them as equivalent.

### The three built-in families

| Template | Layout | What it taught |
|---|---|---|
| `consolidated_holdings.v1` | header row 1, sheet `Holdings Detail` | ends with a **formula total row** that must be skipped |
| `broker_holdings.v1` | header row **23**, column **B**, two sheets | supplies **no value columns** — invested and current are computed from qty × price |
| `mutual_fund_statement.v1` | header row 21, data from row 23 | **name / mobile / PAN sit above the table**; percentages stored as text |

### Files

`app/extraction/` — `workbook.py` (header detection + layout fingerprint), `values.py` (₹, %, date
coercion), `holdings.py` (canonical model), `templates.py` (template-driven parser),
`builtin_templates.py`, `mapping.py` (AI proposal + validation), `holdings_extractor.py`.
Plus `app/repositories/templates_repository.py` and migration `0003`.

### Rules enforced in code

- Extraction **never** writes to a record table; rows stage, a person accepts, then commit.
- A row whose first cell reads as a total is skipped, always.
- Statement totals are read and compared against the sum of extracted rows; drift over 0.5% marks the
  import unreconciled with a stated reason.
- The model sees **only** sheet names, column headings and three **digit-masked** samples per column —
  never the data, never rows above the header. `INE466L01038` becomes `INE###L########`.
- A proposed mapping is validated (columns exist, no duplicates, instrument name present) before a
  person is asked to confirm it.
- Every staged row keeps its sheet, row number and original cells.
- A table's header row is never read as a totals label — this caused a 4% phantom drift on a file that
  in fact reconciled to the rupee.

### Verified against the real files

| File | Rows | Reconciled |
|---|---|---|
| Consolidated | 47 (total row skipped) | ✓ 0.0000% drift |
| Broker | 80 (78 equity + 2 MF) | ✓ 0.0000% drift |
| MF statement | 18 | ✓ 0.0000% drift |

**145 holdings imported end to end through the HTTP API, 79 identified by ISIN.**

### Not yet built

PDF statements and CAS from CAMS/KFintech. Each is a new extractor registered in `EXTRACTORS` or a new
entry in `BUILTIN_TEMPLATES` — no other file changes.

**Password-protected files are explicitly out of scope** (decided 05 September 2026). A protected
statement should be refused with a clear message asking for an unlocked export rather than prompting
for a password we would then have to hold.
