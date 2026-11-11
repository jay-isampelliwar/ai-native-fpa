# Document Import

## Goal

Put the right values from any financial file into the right tables for the user, with no wrong records.

This is a single-user hobby project. The design stays small on purpose.

## Core rules

- Code reads and cleans every value. The model may read a layout or a page, but never writes records.
- When anything is unsure, the user decides. The code never picks on its own.
- Nothing is saved until the user presses Import.
- Writes go through the existing domain services, and every write is read back and checked.
- The model never sees rows above a header, and sees samples only with digits hidden.
- A full page goes to the model only after the user says yes.
- The user never sees ids, document numbers or links. Files are named by their file name.

## Flow

```text
Upload -> read -> classify or plan -> parse -> check -> review -> import -> read back -> note to chat
```

1. The user attaches files in chat. Each one uploads on its own, as soon as it is picked.
2. The same file again returns the earlier upload. A failed or unread upload is read again.
3. The file is saved under `backend/var/uploads/{user_id}/`.
4. The file is read into sheets for code, and pages for the model.
5. Sheets are matched to a known family, or read with a column plan.
6. Every value is cleaned, and every row is checked.
7. The user reviews the rows in a panel beside the chat, then presses Import.
8. The chat gets a short note, "Imported plan.xlsx". The agent reads the saved counts with a tool.

The message to the agent carries only the document id. The tool returns counts and at most five
questions or errors, so the chat stays small whatever the file size.

## Accepted files

| File | How it is read |
|---|---|
| `.xlsx`, `.xls`, `.csv` | Code reads every sheet |
| `.pdf` with tables | Code reads each table as a sheet |
| `.pdf` page with text but no table | The model reads the text, after the user says yes |
| Scanned `.pdf` page, `.png`, `.jpg`, `.webp` | The model reads the picture, after the user says yes |

- The limits are 10 MB per file and 20 pages per PDF.
- The bytes must match the file ending. Video and other files are refused.
- A locked PDF asks for its password in the file chip. The password is used once and never saved.

## Classify or plan

- **Known family:** the planner workbook is matched by its sheet headers and read by fixed rules.
- **Saved plan:** a sheet whose header shape was seen before is read with its saved column plan.
- **New shape:** the model sees only the headings and digit-masked samples, and proposes a plan.
  - If the plan passes the checks, the file is read with it at once. The review shows the plan, with "Change columns".
  - If it fails, the user picks the columns before anything is read.
- A plan is confirmed and saved when the user imports, or changes the columns.
- The model can never map fields the code fills itself, such as a holding's type.

## Checks on every row

- Needed fields, value limits, and real dates.
- Stocks and funds:
  - Exact ISIN or exact symbol needs no question.
  - Any match by name is a question with the five closest choices.
- The same holding twice, with the same folio or no folio: a question on each line.
- A saved holding with no folio while the file has one: a question.
- Units × price more than 1% from the value: a question.
- Matching saved records by type and name: create, update or no change. Two candidates: a question.
- Rows the model read are marked "Check".
- A file with no date gets one date for all rows, from the date bar.

## Totals check

- Total lines, such as "Total" or "Grand Total", are kept out of the rows and used only for the check.
- Labelled totals above or below the rows are read by code: opening balance, closing balance,
  invested value and present value.
- Checks:
  - Each column's sum against its total line.
  - Holdings: units × average price against invested value, and value against present value.
  - Bank: opening + credits − debits = closing.
  - Running balance, line by line, in either order. The first line that breaks is named.
- A difference within ₹1 passes.
- A mismatch blocks the import until the user fixes the rows or picks "Import anyway".
  If the mismatch changes afterwards, it asks again.

## Review panel

- What each sheet gave, and why a sheet was skipped.
- Questions one at a time, "1 of N".
- Rows by table, marked New, Update, No change, Saved, Not saved or Removed. Updates show old against new.
- Edit any field. Fund and stock names suggest matches as you type.
- Remove a row from the import, or bring it back. Saved records are never touched by this.
- Import the ready rows, and undo the whole import afterwards.

## Import and undo

- Each row is written on its own. A failed row is marked with its reason, and the rest stay saved.
- Before an update, the saved record must still match what the preview showed.
- Old values are kept, so undo can put them back.
- Undo removes what the import added and restores what it changed, newest row first.
- Undo stops and changes nothing if any record was changed after the import.

## Tables

| Table | Holds |
|---|---|
| `documents` | File, hash, status, family, summary: sheet notes, plans, totals, waiting steps |
| `import_rows` | One record per row: parsed values, edits, old values, source cells, errors, warnings, questions, matches |
| `layout_mappings` | Column plans by header shape, shared, confirmed by the user |

Document states: `uploaded`, `needs_mapping`, `needs_password`, `needs_consent`, `parsed`, `imported`, `rejected` (undone), `failed`.

Migrations `0022` to `0025`.

## Chat tools

| Tool | Does |
|---|---|
| `get_import_preview` | Reads counts, questions, errors and totals. Never rows. |
| `answer_import_question` | Saves the user's own reply to one question |
| `approve_import` | Imports the ready rows, behind the approval card |
| `undo_import` | Undoes the import, behind the approval card |

- One open question is asked in chat. More than one is answered in the review panel.
- The agent never asks for a PDF password in chat, because chat is saved.

## Code

- Backend: `backend/app/features/documents/`
- Chat tools: `backend/app/agent/tools/imports.py`
- Frontend: `frontend/components/imports/`, `frontend/components/chat/FileChips.tsx`, `frontend/lib/useUploads.ts`
- Tests: `backend/tests/documents/`
