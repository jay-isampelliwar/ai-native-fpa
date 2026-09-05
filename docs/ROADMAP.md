# AI Native Financial Planner — state and what is left

Written 05 September 2026. This is the pick-up-later document: what exists, what was
decided, what is still open, and what each remaining phase actually involves.

---

## Where the build is now

**Phases 1 and 2 of the implementation guide are complete and verified.**

| | |
|---|---|
| Python modules | 55 (excluding `__init__.py`) |
| Tests | 82 passing, 2 skipped (live-model evals) |
| HTTP endpoints | 18 |
| Database | PostgreSQL `fpa` on `localhost:5433`, 20 tables |
| Migration | Alembic at revision `0001` |

### What works end to end

1. A request enters `POST /api/v1/planner/messages`.
2. The manual top-level LangGraph authenticates, routes to a skill, checks scopes,
   executes, validates, audits, and replies.
3. Three skills are registered, deliberately in three different shapes:
   - `cashflow_summary` — deterministic, no model call
   - `expense_investigation` — ReAct agent, tools bound to the authenticated user
   - `goal_planning` — manual subgraph, four nodes, no model call
4. Records entered through `/api/v1/records/*` immediately change what the planner says.
5. Every answer carries `evidence_ids` and `calculator_versions`; every run, including
   refusals, writes an `audit_records` row.

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

## Phase 3 — Document import

**Exit condition:** imports reconcile before committing records.

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

## Phase 4 — Proactive planner

**Exit condition:** notifications cite fresh verified data.

Alerts that fire without being asked — cash shortfall ahead, goal drift, FD maturity
approaching, SIP debit failing. Each one has to cite the records behind it, which means
they run through skills rather than through a cron job with its own SQL.

Roughly 10–12 files: a scheduler, alert definitions, a notification table and delivery
adapter, plus skills for each alert kind.

---

## Phase 5 — Controlled actions

**Exit condition:** compliance review complete, full audit trail.

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
