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
  | 'awaiting_approval'
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

/**
 * One tool the planner called during a reply, and how far it has got. `stopped` comes only from
 * a saved chat, for a tool that was still running when the reply was stopped. `rejected` is a
 * tool the person said no to on an approval card.
 */
export interface ToolStep {
  id: string;
  name: string;
  /** The friendly line to show, such as "Reading your records". */
  label: string;
  status: 'running' | 'ok' | 'error' | 'stopped' | 'rejected';
}

/**
 * A risky tool call the run paused on, as the `approval.required` event carries it.
 *
 * `preview` is the exact item the backend read before pausing, so the card shows what will really
 * change rather than what the model thinks it is. After `expires_at` the backend refuses a click.
 *
 * `action` says what approving does. A `remove` field has a `value`; a `change` field has its saved
 * `old` value and the `new` one. `run` is a tool with no preview of its own, showing its arguments.
 * `confirm` shows values the app worked out, such as fund units from an amount, and `editable`
 * holds the ones the person may fix before saving.
 * Older approvals were saved before `action` existed and are always removals.
 */
export interface ApprovalRequest {
  approval_id: number;
  run_id: number;
  name: string;
  label: string;
  preview: {
    action?: ApprovalAction;
    title: string;
    fields: ApprovalField[];
    editable?: ApprovalEdits;
    subtitle?: string | null;
    chips?: string[];
    changes?: ApprovalChange[];
    facts?: ApprovalFact[];
    summary?: { lead: string; big: string; how: string };
    note?: { tone: 'calm' | 'warn'; text: string };
  };
  expires_at: string;
}

export type ApprovalAction = 'remove' | 'change' | 'run' | 'confirm';

/** Values the person fixed on a confirm card, sent with the approval. */
export interface ApprovalEdits {
  units?: string;
  amount?: string;
}

export type ApprovalDecision = 'approve' | 'reject';

/** One field a change card will change, in plain words, such as "Money you put in" ₹5,000 → ₹6,000. */
export interface ApprovalChange {
  label: string;
  old: string;
  new: string;
}

/** One key fact a remove card shows about the item, such as "Units" 551.241. */
export interface ApprovalFact {
  label: string;
  value: string;
}

export interface ApprovalField {
  name: string;
  value?: string;
  old?: string;
  new?: string;
}

/**
 * Where one approval card is. `skipped` is a card the person moved past by sending a new message,
 * which the backend treats as a reject. `closed` is one the backend had already answered.
 */
export type ApprovalState = 'pending' | 'sending' | 'approved' | 'rejected' | 'skipped' | 'expired' | 'closed';

export interface ConversationMessage {
  id: number;
  run_id: number | null;
  role: 'user' | 'assistant';
  status: MessageStatus;
  text: string;
  created_at: string;
  /** Tools the planner called for this answer. Always empty for the person's own messages. */
  tools: ToolStep[];
  /** Cards and forms the tools gave this answer, keyed by tool call id. */
  blocks?: UiBlockEntry[];
  /** The filled form this user message was sent from, shown as a chip instead of its text. */
  form?: FormSubmission | null;
}

/**
 * Typed UI blocks a tool sends with `ui.block`. The backend builds every value from exact data, so
 * the frontend only draws them. A reply's text places a card with a `{{card:<id>}}` line.
 */
export type UiBlock =
  | TableBlock
  | BreakdownBlock
  | GoalProgressBlock
  | FactsBlock
  | StackBlock
  | SourcesBlock
  | QuoteBlock
  | HoldingsBlock
  | FormBlock;

export interface UiBlockEntry {
  id: string;
  block: UiBlock;
}

export interface TableBlock {
  type: 'table';
  title?: string | null;
  subtitle?: string | null;
  columns: { key: string; label: string; align: 'left' | 'right' }[];
  rows: Record<string, string>[];
}

export interface BreakdownItem {
  label: string;
  /** Bar length, 0 to 100. */
  pct: number;
  value: string;
}

export interface BreakdownBlock {
  type: 'breakdown';
  title?: string | null;
  subtitle?: string | null;
  groups: { title: string; items: BreakdownItem[] }[];
}

export interface GoalProgressBlock {
  type: 'goal_progress';
  title: string;
  summary: { label: string; value: string }[];
  goals: {
    name: string;
    target_year: number;
    on_track: boolean;
    target_today: string;
    target_future: string;
    monthly_need: string;
    monthly_assigned: string;
    shortfall: string;
    covered_pct: number;
  }[];
}

export interface FactsBlock {
  type: 'facts';
  title?: string | null;
  facts: { label: string; value: string }[];
}

export interface StackBlock {
  type: 'stack';
  title: string;
  chips?: string[];
  blocks: UiBlock[];
}

/** A `sources` block: the web pages a search found, each opened in a new tab. */
export interface SourcesBlock {
  type: 'sources';
  title: string;
  items: { title: string; url: string; site: string; published?: string | null; image?: string | null }[];
}

/** A labelled number for a card's top row, coloured by `direction` when it is a change. */
export interface SummaryStat {
  label: string;
  value: string;
  note?: string | null;
  direction?: 'up' | 'down' | null;
}

/** A `holdings` block: total value and gain on top, then each holding by size with its share of the money. */
export interface HoldingsBlock {
  type: 'holdings';
  title: string;
  as_of?: string | null;
  subtitle?: string | null;
  summary: SummaryStat[];
  items: {
    name: string;
    value: string;
    /** Share of the total value, 0 to 100. */
    share: number;
    /** Today's move, only when a fresh NAV or price for today is known. */
    today?: { text: string; direction: 'up' | 'down' } | null;
  }[];
}

/** A `quote` block: one or more index levels. One index also carries four stats; several carry none. */
export interface QuoteBlock {
  type: 'quote';
  as_of: string;
  closed: boolean;
  items: {
    name: string;
    value: string;
    number: number;
    change: string;
    change_pct: string;
    direction: 'up' | 'down';
    stats?: { label: string; value: string }[];
  }[];
}

export type FormKind ='goal' | 'income' | 'expense' | 'holding' | 'loan' | 'insurance';

export type FormValue = string | number | boolean;

export interface FormBlock {
  type: 'form';
  form: FormKind;
  values: Record<string, FormValue>;
  record_id: number | null;
}

/** A filled form as it is sent to start a run, and as it comes back on the saved user message. */
export interface FormSubmission {
  kind: FormKind;
  values: Record<string, FormValue>;
  record_id: number | null;
  block_id: string | null;
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
