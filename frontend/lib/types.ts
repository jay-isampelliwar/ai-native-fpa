/**
 * The shapes the backend actually returns, mirrored by hand rather than generated.
 *
 * These types are the contract between two codebases and they are deliberately narrow: a block the
 * backend can send has a type here, and one it cannot does not. The discriminated union on `type` is
 * what lets the block registry be exhaustive - adding a block to the backend without adding it here
 * becomes a TypeScript error at the switch rather than a silently unrendered element.
 *
 * Money arrives as a string, never a number. The backend stores NUMERIC and serialises Decimal as a
 * string precisely so precision survives the wire; parsing it into a JavaScript number here would
 * undo that at the last step. `display` is the backend's formatting and is what should be shown;
 * `value` exists for charts that need to scale an axis.
 *
 * `evidence_ids` appears on every block, not just on the response. That is what lets a reader tap one
 * figure and see the rows behind that figure rather than the rows behind the whole answer.
 *
 * `PromptBlock` is the one block with nothing to trace: it asks for records instead of reporting
 * them, so its `evidence_ids` is always empty. Its `examples` come from the backend's list of asks,
 * which is why the renderer can offer them as something to send.
 *
 * There is no `MessageResponse` beyond a thread id and the text, and no conversation or approval
 * shape at all. The blocks, evidence ids, calculator versions, skill name and approval card that
 * used to ride along with a chat reply described endpoints this branch removed, and a type for a
 * field the backend cannot send is how a client ends up rendering an empty section forever.
 */

export type BlockType =
  | "text"
  | "kpi"
  | "table"
  | "chart"
  | "callout"
  | "prompt";

export interface BlockBase {
  evidence_ids: string[];
}

export interface TextBlock extends BlockBase {
  type: "text";
  text: string;
}

export interface KpiBlock extends BlockBase {
  type: "kpi";
  label: string;
  display: string;
  value: string | null;
  caption: string | null;
  tone: "neutral" | "positive" | "negative";
}

export interface TableColumn {
  key: string;
  label: string;
  align: "left" | "right";
}

export interface TableBlock extends BlockBase {
  type: "table";
  title: string | null;
  columns: TableColumn[];
  rows: Record<string, string>[];
}

export interface ChartPoint {
  label: string;
  value: string;
  display: string | null;
  tone: "neutral" | "positive" | "negative";
}

/** One computed figure drawn across a chart — the target a projection is measured against. */
export interface ChartMarker {
  label: string;
  value: string;
  display: string | null;
}

export interface ChartBlock extends BlockBase {
  type: "chart";
  chart: "bar" | "line" | "donut" | "progress";
  title: string | null;
  points: ChartPoint[];
  marker: ChartMarker | null;
  caption: string | null;
  value_prefix: string;
}

export interface CalloutBlock extends BlockBase {
  type: "callout";
  level: "note" | "warning";
  text: string;
}

export interface PromptItem {
  label: string;
  question: string;
  examples: string[];
}

export interface PromptBlock extends BlockBase {
  type: "prompt";
  title: string;
  items: PromptItem[];
  caption: string | null;
}

export type Block =
  | TextBlock
  | KpiBlock
  | TableBlock
  | ChartBlock
  | CalloutBlock
  | PromptBlock;

export interface MessageResponse {
  conversation_id: string;
  response: string;
}

export interface WorkspaceReadiness {
  held: Record<string, number>;
  missing: string[];
  labels: Record<string, string>;
  can_compute_cashflow: boolean;
  has_any_records: boolean;
}

export interface WorkspaceSection {
  key: string;
  title: string;
  subtitle: string | null;
  blocks: Block[];
}

export interface Workspace {
  user_id: number;
  readiness: WorkspaceReadiness;
  sections: WorkspaceSection[];
}

export interface ProgressEvent {
  node: string;
  label: string;
}

export interface ImportRead {
  id: string;
  filename: string;
  status:
    | "uploaded"
    | "extracting"
    | "needs_mapping"
    | "extracted"
    | "committed"
    | "failed";
  document_kind: string;
  detected_format: string | null;
  extractor: string | null;
  template_id: string | null;
  row_count: number;
  error: string | null;
  import_batch_id: string | null;
  created_at: string;
  extracted_at: string | null;
  committed_at: string | null;
  duplicate_of_existing_upload: boolean;
  can_remap: boolean;
  statement_totals: Record<string, string> | null;
  computed_totals: Record<string, string> | null;
  reconciled: boolean | null;
  reconciliation_note: string | null;
}

export interface StagedRow {
  id: string;
  row_index: number;
  target_table: string;
  payload: Record<string, unknown>;
  confidence: string;
  status: "pending" | "accepted" | "rejected" | "duplicate";
  issue: string | null;
  edited: boolean;
}

export interface StagedRowsPage {
  import_id: string;
  status: string;
  total: number;
  pending: number;
  accepted: number;
  rejected: number;
  duplicates: number;
  rows: StagedRow[];
}

export interface MappingColumn {
  index: number;
  header: string;
  samples: string[];
}

export interface MappingSheet {
  sheet: string;
  header_row: number;
  asset_type: string;
  columns: MappingColumn[];
  mapping: Record<string, string>;
}

export interface MappingProposal {
  import_id: string;
  fingerprint: string;
  provider: string;
  sheets: MappingSheet[];
  problems: string[];
  usable: boolean;
}

export interface CommitResponse {
  status: string;
  import_batch_id: string | null;
  rows_written: number;
  detail: string | null;
}

export interface Alert {
  kind: string;
  severity: "action" | "attention" | "info";
  title: string;
  detail: string;
  evidence_ids: string[];
  calculator_versions: string[];
}

export interface AlertsResponse {
  user_id: number;
  total: number;
  action_required: number;
  alerts: Alert[];
}

export interface GoalRead {
  id: string;
  label: string;
  kind: string;
  target_amount: string;
  target_date: string;
  priority: number;
  inflation_percent: string;
  funded_corpus: string;
  monthly_contribution: string;
  valued_at_cost: boolean;
  evidence_ids: string[];
}

export interface RecordCreated {
  id: string;
  kind: string;
}

export interface Holding {
  id: string;
  instrument_name: string;
  isin: string | null;
  identifier_type: string;
  asset_type: string | null;
  account_label: string | null;
  source: string | null;
  folio_id: string | null;
  units: string;
  average_cost: string;
  last_price: string | null;
  invested_value: string | null;
  current_value: string | null;
  as_of: string;
  import_batch_id: string | null;
}

export interface HoldingsSummary {
  count: number;
  invested_value: string;
  current_value: string;
  unrealised: string;
  identified_by_isin: number;
  valued_at: string | null;
  by_asset_type: Record<string, string>;
  holdings: Holding[];
}
