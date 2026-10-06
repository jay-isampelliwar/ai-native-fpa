/**
 * The shapes the backend actually returns, mirrored by hand rather than generated.
 *
 * There are two of them, because the backend has two endpoints: registering an id, and one streaming
 * chat turn. Everything else this file held - typed blocks, the workspace panel, imports and their
 * staged rows, alerts, goals, holdings, conversations, approvals - described routes that have been
 * removed, and a type for a field the backend cannot send is how a client ends up rendering an empty
 * section forever.
 *
 * `MessageResponse` is what the stream's closing `done` event carries: only the thread id. The
 * backend holds one fixed thread for now, so there is nothing for the client to send back.
 *
 * `ProgressEvent` is one line of "what is happening" while the answer is being written. It carries no
 * skill name any more; there is one node in the graph, so there is nothing to name.
 */

export interface MessageResponse {
  thread_id: string;
}

export interface ProgressEvent {
  node: string;
  label: string;
}

/**
 * The states one uploaded document moves through, mirrored from the backend's own tuple.
 *
 * `locked` and `needs_mapping` are not failures and must not be drawn as one. A locked PDF is
 * waiting for a password and a `needs_mapping` file is waiting for a column mapping — both are
 * asking the reader for something, which is the opposite of a dead end.
 */
export type ImportStatus =
  | 'uploaded'
  | 'extracting'
  | 'extracted'
  | 'committed'
  | 'failed'
  | 'needs_mapping'
  | 'locked'
  | 'rejected';

/** One accepted upload, answered before the file has been read. */
export interface UploadedDocument {
  id: string;
  filename: string;
  status: ImportStatus;
  duplicate: boolean;
}

export interface UploadResponse {
  documents: UploadedDocument[];
}

/**
 * Where one document has reached, with the row tallies a card needs before fetching any detail.
 *
 * The four counts are of staged rows, not of records written. `duplicate_rows` are the ones held
 * back because they already appear in the person's records, and they are approved separately.
 */
export interface DocumentImport {
  id: string;
  filename: string;
  content_type: string;
  byte_size: number;

  status: ImportStatus;
  document_kind: string;
  detected_format: string | null;
  extractor: string | null;
  error: string | null;

  row_count: number;
  pending_rows: number;
  accepted_rows: number;
  rejected_rows: number;
  duplicate_rows: number;

  statement_totals: Record<string, string> | null;
  computed_totals: Record<string, string> | null;
  reconciled: boolean | null;
  reconciliation_note: string | null;

  import_batch_id: string | null;
  created_at: string;
  extracted_at: string | null;
  committed_at: string | null;
}

/**
 * One extracted record as the review card shows it, before anyone has approved anything.
 *
 * `payload` is shaped for the table the row is destined for, so its keys differ between a
 * transaction and a holding. The card reads it defensively rather than assuming one shape.
 *
 * `confidence` is how sure the extractor was. A deterministic parser reports 1, an inferred
 * reading reports less, and the card sorts the doubtful ones to the top.
 */
export interface StagedRow {
  id: string;
  row_index: number;
  target_table: string;
  payload: Record<string, string | null>;

  confidence: string;
  status: 'pending' | 'accepted' | 'rejected' | 'duplicate';
  issue: string | null;
  edited: boolean;

  source_sheet: string | null;
  source_row_number: number | null;
  source_cells: string[];
}

export interface StagedRows {
  import_id: string;
  rows: StagedRow[];
}

/** What one approval wrote, including anything it could not write and why. */
export interface CommitResult {
  status: 'committed' | 'already_committed' | 'nothing_accepted' | 'not_ready' | 'not_found';
  rows_written: number;
  rows_skipped: number;
  import_batch_id: string | null;
  detail: string | null;
}
