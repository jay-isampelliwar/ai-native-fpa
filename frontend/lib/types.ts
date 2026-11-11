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
  | HeroBlock
  | KpisBlock
  | BarsBlock
  | RingBlock
  | GaugeBlock
  | ReceiptBlock
  | ChangesBlock
  | ChecklistBlock
  | CompareBlock
  | TimelineBlock
  | EmptyBlock
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

/** Which way a number moved, for colour: up is profit (teal), down is loss (rose). */
export type Direction = 'up' | 'down';

/** A small change beside a number, such as "+₹52,400 (2.9%)". */
export interface Change {
  text: string;
  direction: Direction;
}

/** A `hero` block: one big number that answers the question, such as net worth, with a few facts under it. */
export interface HeroBlock {
  type: 'hero';
  title: string;
  as_of?: string | null;
  value: string;
  change?: Change | null;
  /** A short word after the change, such as "this month". */
  change_note?: string | null;
  facts?: { label: string; value: string }[];
  tone?: 'up' | 'down' | 'accent' | 'warn' | null;
}

/** A `kpis` block: two to four small tiles, each a number with its change and a short trend line. */
export interface KpisBlock {
  type: 'kpis';
  title?: string | null;
  as_of?: string | null;
  items: {
    label: string;
    value: string;
    change?: Change | null;
    /** Recent values, oldest first, for the trend line. Empty or missing draws no line. */
    trend?: number[];
  }[];
}

/** A `bars` block: grouped bars by month, one or two series, in rupees. */
export interface BarsBlock {
  type: 'bars';
  title: string;
  subtitle?: string | null;
  labels: string[];
  series: { name: string; values: number[] }[];
}

/** A `ring` block: how a total is split, as a ring with a legend. */
export interface RingBlock {
  type: 'ring';
  title: string;
  subtitle?: string | null;
  total: string;
  items: { label: string; value: string; pct: number }[];
}

/** A `gauge` block: a score out of 100 on a half ring, with the checks behind it. */
export interface GaugeBlock {
  type: 'gauge';
  title: string;
  as_of?: string | null;
  score: number;
  /** One word for the score, such as "Fair". */
  verdict: string;
  checks: { label: string; value: string; tone: 'up' | 'down' | 'warn' }[];
}

/** A `receipt` block: what was just saved or removed, with its key facts. */
export interface ReceiptBlock {
  type: 'receipt';
  action: 'saved' | 'removed';
  /** The kind of item in words, such as "Loan". */
  kind: string;
  name: string;
  record_id?: number | null;
  facts: { label: string; value: string }[];
}

/** A `changes` block: the fields an update changed, old beside new. */
export interface ChangesBlock {
  type: 'changes';
  title: string;
  fields: { label: string; old: string; new: string }[];
  note?: string | null;
}

/** A `checklist` block: which sections the planner knows about, and which are still missing or declined. */
export interface ChecklistBlock {
  type: 'checklist';
  title: string;
  subtitle?: string | null;
  items: { label: string; status: 'done' | 'missing' | 'declined' }[];
}

/** A `compare` block: two to four things side by side, one row per measure. */
export interface CompareBlock {
  type: 'compare';
  title?: string | null;
  columns: string[];
  rows: {
    label: string;
    values: string[];
    /** Index of the best value in this row, to mark it, or null when none is better. */
    best?: number | null;
  }[];
  note?: string | null;
}

/** A `timeline` block: dated money events, soonest first. */
export interface TimelineBlock {
  type: 'timeline';
  title: string;
  items: { when: string; label: string; value?: string | null; state: 'past' | 'soon' | 'far' }[];
}

/** An `empty` block: nothing saved of this kind yet, with the form that adds one when there is one. */
export interface EmptyBlock {
  type: 'empty';
  title: string;
  text?: string | null;
  form?: FormKind | null;
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
 * Where one upload is: waiting for a confirmed column mapping, parsed and waiting for review,
 * imported, undone (`rejected`) or failed with a reason.
 */
export type DocumentStatus =
  | 'uploaded'
  | 'needs_mapping'
  | 'needs_password'
  | 'needs_consent'
  | 'parsed'
  | 'imported'
  | 'rejected'
  | 'failed';

export type ImportRowAction = 'create' | 'update' | 'no_change';

export type ImportRowStatus = 'proposed' | 'approved' | 'rejected' | 'written' | 'failed' | 'undone';

/** What happened to one sheet of an upload: read, empty, skipped, hidden, or waiting for a mapping. */
export interface SheetNote {
  sheet: string;
  outcome: 'imported' | 'empty' | 'not_imported' | 'needs_mapping' | 'warning';
  message: string;
  rows: number;
}

export interface QuestionOption {
  value: string;
  label: string;
}

/** One doubt the code would not settle alone. The answer is one of the option values, or null. */
export interface ImportQuestion {
  id: string;
  kind: 'pick_instrument' | 'keep_duplicate' | 'pick_record' | 'value_mismatch';
  text: string;
  options: QuestionOption[];
  answer: string | null;
}

/** The stock or fund a holding row was matched to. */
export interface MatchedInstrument {
  kind: 'stock' | 'fund';
  id: number;
  isin: string;
  name: string;
}

/** One full record read from a file, with where it came from and what approving it would do. */
export interface ImportRowView {
  id: number;
  row_number: number;
  target_table: string;
  action: ImportRowAction | null;
  status: ImportRowStatus;
  parsed_data: Record<string, unknown>;
  edited_data: Record<string, unknown> | null;
  source: { sheet?: string; row?: number; cells?: Record<string, string>; read_by_model?: boolean };
  errors: string[];
  warnings: string[];
  questions: ImportQuestion[];
  resolved: {
    instrument?: MatchedInstrument;
    existing?: Record<string, unknown>;
    changes?: Record<string, unknown>;
    skipped?: boolean;
    /** True when the person took this row out of the import. */
    removed?: boolean;
  };
}

/** The model's proposed mapping for one sheet of an unknown file, waiting for the user. */
export interface PendingMapping {
  sheet: string;
  fingerprint: string;
  headers: string[];
  target_table: string | null;
  columns: Record<string, string>;
  reason: string | null;
  errors: string[];
}

export interface ImportChecks {
  ready: number;
  with_errors: number;
  open_questions: number;
  skipped: number;
  no_change: number;
}

export interface DocumentView {
  id: number;
  original_filename: string;
  family: string | null;
  status: DocumentStatus;
  error_message: string | null;
  duplicate: boolean;
  sheets: SheetNote[];
  checks: Partial<ImportChecks>;
  pending_mappings: PendingMapping[];
  /** The column plans the file was read with; each can be changed while nothing is imported. */
  plans: (PendingMapping & { confirmed_at?: string | null })[];
  /** Pages only the model can read, waiting for the person's OK. */
  pending_pages: { count: number; pictures: number } | null;
  /** True for a PDF that needed a password, which must be given again for each new read. */
  locked: boolean;
  rows: ImportRowView[];
  created_at: string;
}

export interface SheetChoice {
  sheet: string;
  target_table: string | null;
  columns: Record<string, string>;
}

export interface QuestionAnswer {
  row_id: number;
  question_id: string;
  answer: string;
}

export interface RowEdit {
  changes?: Record<string, unknown>;
  /** A pick from the search, such as fund:123. */
  instrument?: string;
}

export interface InstrumentChoice {
  value: string;
  label: string;
  kind: 'stock' | 'fund';
  isin: string;
  name: string;
}

export interface ApprovalOutcome {
  written: number;
  no_change: number;
  failed: number;
  document: DocumentView;
}

/** Each table a file can fill with each field's kind, such as money or date, and the values each choice kind allows. */
export interface ImportFields {
  tables: Record<string, Record<string, string>>;
  choices: Record<string, string[]>;
}
