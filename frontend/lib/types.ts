/**
 * The shapes the backend actually returns, mirrored by hand rather than generated.
 *
 * `RunResponse` is what `POST /api/runs` answers with: the run that will write the reply, and the
 * conversation it belongs to. The conversation id is sent back with the next message so the agent
 * continues the same thread.
 */

/** The signed-in person, as `GET /api/auth/me` returns them. */
export interface CurrentUser {
  id: number;
  name: string;
  email: string;
}

export type RunStatus =
  | 'queued'
  | 'running'
  | 'cancel_requested'
  | 'cancelled'
  | 'completed'
  | 'failed';

export interface RunResponse {
  run_id: number;
  conversation_id: number;
  status: RunStatus;
}

/** One row of the history list. The title comes from the chat's first message. */
export interface ConversationSummary {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ConversationList {
  conversations: ConversationSummary[];
}

export type MessageStatus = 'streaming' | 'completed' | 'cancelled' | 'failed';

export interface ConversationMessage {
  id: number;
  run_id: number | null;
  role: 'user' | 'assistant';
  status: MessageStatus;
  text: string;
  created_at: string;
}

/**
 * One past chat, opened. `active_run` is set when a reply is still being written, so the chat can
 * rejoin that run's stream instead of showing half a reply that never finishes.
 */
export interface ConversationDetail {
  id: number;
  title: string;
  messages: ConversationMessage[];
  active_run: { run_id: number; status: RunStatus } | null;
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
