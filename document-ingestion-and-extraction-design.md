# Document Import Plan

## Goal

Put the right values from a file into the right tables for the user, with no wrong records.

This is a single-user hobby project. The design stays small on purpose.

## Core rule

- Code parses the file. The model never writes records.
- Every row is checked before it is written.
- The user sees a preview and approves it.
- Writes go through the existing services, such as the investments service.
- Each write is read back and checked.

## Flow

```text
Upload -> classify -> parse -> check -> preview -> approve -> write -> read back
```

1. The user uploads a file. The API hashes it with SHA-256.
2. The same file again returns the earlier document. It is not parsed twice.
3. The file is saved under `backend/var/uploads`.
4. Code reads the header row and finds the format family.
5. That family's parser turns each record into one `import_rows` row.
6. Checks run: ISIN match, numbers, dates, duplicates, statement totals.
7. The preview shows each row as create, update or no change.
8. The user approves, edits or rejects rows.
9. Approved rows are written through the domain service, then read back.

Excel and CSV parse in under a second, so the API parses them directly. A worker is added only when PDFs or OCR arrive.

## Classification

- Each family lists the headers it expects.
- The header row is compared with each family.
- One match: that parser runs, and `documents.family` is set.
- No match: the upload stops with "Format not known", plus the headers it found.
- Two matches: the upload stops with "Matches two formats".
- Later, an unknown file's headings and digit-masked samples go to the model. The model suggests a family or mapping, and the user confirms it.

Known families:

- `consolidated_holdings`
- `broker_holdings`
- `mutual_fund_statement`

## Tables

Migration `0022_document_import`.

### `documents`

One uploaded file.

| Column | Meaning |
|---|---|
| `user_id` | Owner |
| `original_filename`, `mime_type`, `file_size_bytes` | What was uploaded |
| `sha256` | Unique per user, so the same file is stored once |
| `storage_path` | Where the file sits under `var/uploads` |
| `family` | The format family it matched |
| `status` | `uploaded`, `parsed`, `imported`, `rejected`, `failed` |
| `error_message` | Why it failed |

### `import_rows`

One full record from a document, such as one holding.

| Column | Meaning |
|---|---|
| `document_id` | The file it came from |
| `row_number` | Order in the file, unique per document |
| `target_table` | Where it goes, such as `holdings` |
| `action` | `create`, `update` or `no_change` |
| `status` | `proposed`, `approved`, `rejected`, `written`, `failed`, `undone` |
| `parsed_data` | Values as parsed. Never changed after parsing. |
| `edited_data` | The user's changes, kept apart from `parsed_data` |
| `previous_data` | Old values of the record, saved before an update |
| `target_record_id` | The record updated or created |
| `source` | Sheet, row and cells the values came from |
| `errors` | Problems that block the write |
| `warnings` | Problems the user should look at |
| `written_at` | When the write happened |

## Rules

- Money and units are stored as strings in JSON and as `NUMERIC` in tables, never as float.
- Match a security by ISIN first. With no ISIN, the row needs review. No guessing.
- The sum of rows must match the statement total.
- The model sees only headings and digit-masked samples.
- Rows above the header are never sent to the model. One real format has PAN there.
- Undo puts back `previous_data`. If the record changed after the import, undo stops and warns.

## Phases

| # | Phase | Done when |
|---|---|---|
| 1 | Two tables, one migration | Migration runs up and down |
| 2 | Upload and parse holdings files | Real files give correct rows |
| 3 | Checks: ISIN, totals, duplicates | A bad row shows an error |
| 4 | Preview, approve, write, read back | Approve fills `holdings` correctly |
| 5 | Upload and review card in the frontend | Works from the browser |
| 6 | Later: other tables, PDFs, unknown formats | Added when needed |

## Testing

- One real test file per family, with every number checked.
- Unit tests for the number and date cleaning.
- The target is zero wrong records written.
