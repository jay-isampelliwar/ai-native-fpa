'use client';

import { AlertTriangle, Check, ChevronDown, Copy, X } from 'lucide-react';
import { useEffect, useState } from 'react';

import { documents, imports } from '@/lib/api';
import type { CommitResult, DocumentImport, StagedRow } from '@/lib/types';

/**
 * The approval card: what was read out of one document, and the only way any of it is saved.
 *
 * There is one card per file rather than one per message. A statement that parsed cleanly should
 * not be held back because a second file in the same upload did not, and each commit is one
 * transaction on the server, so per-file is also what the backend can actually promise.
 *
 * Rows are shown and not edited. The decision this card asks for is whether the document was read
 * correctly, which a person answers by looking — and an editable grid inside a chat turn invites
 * fixing figures one at a time instead of noticing that a whole column is wrong.
 *
 * Doubtful rows sort to the top. Confidence is the extractor saying where it had to infer, and the
 * whole point of sorting by it is that a reader's attention is finite: twenty transactions read
 * from a clean CSV do not need checking, and the one with an unreadable date does.
 *
 * Duplicates are held back and approved separately. Two identical charges on one day are sometimes
 * genuinely two charges, and only the person knows which — so they are neither dropped silently nor
 * swept in with everything else.
 *
 * Nothing here polls. The card is drawn for a document that has already finished being read; the
 * chips above the composer are what watch a file that has not.
 */

/** Below this the extractor had to infer something, and the row is worth a person's eye. */
const CERTAIN_ENOUGH = 0.9;

const KIND_LABELS: Record<string, string> = {
  expense_transactions: 'Transactions',
  records: 'Income and expenses',
  holdings: 'Holdings',
  goals: 'Goals',
};

const LABEL_KEYS = ['merchant', 'label', 'scheme_name', 'name', 'description'];
const AMOUNT_KEYS = ['amount', 'target_amount', 'current_value', 'invested_value'];
const DATE_KEYS = ['occurred_on', 'target_date', 'as_of'];

function pick(payload: Record<string, string | null>, keys: string[]): string | null {
  for (const key of keys) {
    const value = payload[key];
    if (value) return String(value);
  }

  return null;
}

/** Doubtful first, then the order the document stated. */
function forReview(rows: StagedRow[]): StagedRow[] {
  return [...rows].sort((left, right) => {
    const gap = Number(left.confidence) - Number(right.confidence);
    return gap !== 0 ? gap : left.row_index - right.row_index;
  });
}

export default function ImportReview({
  userId,
  importId,
  onCommitted,
}: {
  userId: number;
  importId: string;
  onCommitted?: () => void;
}) {
  const [record, setRecord] = useState<DocumentImport | null>(null);
  const [rows, setRows] = useState<StagedRow[]>([]);
  const [result, setResult] = useState<CommitResult | null>(null);
  const [duplicateResult, setDuplicateResult] = useState<CommitResult | null>(null);
  const [refused, setRefused] = useState(false);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => {
    let live = true;

    async function load() {
      try {
        const [document, staged] = await Promise.all([
          documents.read(userId, importId),
          imports.rows(userId, importId),
        ]);

        if (!live) return;

        setRecord(document);
        setRows(staged.rows);
      } catch {
        // The reply above still stands on its own; a card that cannot load simply does not draw.
      }
    }

    void load();

    return () => {
      live = false;
    };
  }, [importId, userId]);

  if (!record || record.status === 'failed' || record.status === 'locked') return null;

  const pending = rows.filter((row) => row.status === 'pending');
  const duplicates = rows.filter((row) => row.status === 'duplicate');

  const settled = result !== null || refused || record.status === 'committed';

  async function run(work: () => Promise<void>) {
    setBusy(true);
    setFailure(null);

    try {
      await work();
    } catch (error) {
      setFailure(error instanceof Error ? error.message : 'that could not be completed');
    }

    setBusy(false);
  }

  if (settled) {
    return (
      <div className="mt-2 rounded-xl border border-line bg-panel-subtle px-3 py-2 text-[12px]">
        {refused ? (
          <span className="text-muted">Refused {record.filename}. Nothing was saved.</span>
        ) : (
          <span className="text-positive">
            Saved {(result?.rows_written ?? 0) + (duplicateResult?.rows_written ?? 0)} rows from{' '}
            {record.filename}.
            {(result?.rows_skipped ?? 0) > 0 &&
              ` ${result?.rows_skipped} could not be saved and stay listed with the reason.`}
          </span>
        )}

        {!refused && duplicates.length > 0 && duplicateResult === null && (
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              void run(async () => {
                setDuplicateResult(await imports.approveDuplicates(userId, importId));
                onCommitted?.();
              })
            }
            className="ml-1 underline underline-offset-2 disabled:opacity-40"
            style={{ color: 'var(--accent)' }}
          >
            Also save the {duplicates.length} you already had?
          </button>
        )}

        {failure && <p className="mt-1 text-negative">{failure}</p>}
      </div>
    );
  }

  return (
    <div className="mt-2 overflow-hidden rounded-xl border border-line bg-panel">
      <Header record={record} newRows={pending.length} />

      <RowGroups rows={pending} />

      {duplicates.length > 0 && (
        <div className="border-t border-line px-3 py-2">
          <button
            type="button"
            onClick={() => setOpen((was) => !was)}
            className="flex w-full items-center gap-1.5 text-left text-[12px] text-secondary"
          >
            <Copy size={13} className="flex-none text-warning" aria-hidden="true" />
            <span className="flex-1">
              {duplicates.length} row{duplicates.length === 1 ? '' : 's'} you already have, held back
            </span>
            <ChevronDown
              size={14}
              className={`flex-none transition ${open ? 'rotate-180' : ''}`}
              aria-hidden="true"
            />
          </button>

          {open && (
            <ul className="mt-1.5 space-y-1">
              {duplicates.map((row) => (
                <Row key={row.id} row={row} />
              ))}
            </ul>
          )}
        </div>
      )}

      {failure && <p className="px-3 pb-1 text-[11.5px] text-negative">{failure}</p>}

      <div className="flex items-center gap-2 border-t border-line px-3 py-2.5">
        <button
          type="button"
          disabled={busy || pending.length === 0}
          onClick={() =>
            void run(async () => {
              setResult(await imports.approve(userId, importId));
              onCommitted?.();
            })
          }
          className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12.5px] font-medium transition disabled:cursor-not-allowed disabled:opacity-40"
          style={{ background: 'var(--accent)', color: 'var(--on-accent)' }}
        >
          <Check size={14} strokeWidth={2.6} aria-hidden="true" />
          Approve {pending.length} row{pending.length === 1 ? '' : 's'}
        </button>

        <button
          type="button"
          disabled={busy}
          onClick={() =>
            void run(async () => {
              await documents.reject(userId, importId);
              setRefused(true);
            })
          }
          className="flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-[12.5px] text-secondary transition hover:text-primary disabled:opacity-40"
        >
          <X size={14} aria-hidden="true" />
          Reject
        </button>

        <span className="ml-auto text-[11px] text-muted">Nothing is saved until you approve</span>
      </div>
    </div>
  );
}

function Header({ record, newRows }: { record: DocumentImport; newRows: number }) {
  return (
    <div className="border-b border-line px-3 py-2.5">
      <div className="flex items-baseline gap-2">
        <span className="min-w-0 flex-1 truncate text-[12.5px] font-medium text-primary">
          {record.filename}
        </span>
        <span className="flex-none text-[11.5px] text-muted">
          {newRows} new row{newRows === 1 ? '' : 's'}
        </span>
      </div>

      {record.reconciled === false && record.reconciliation_note && (
        <p className="mt-1.5 flex items-start gap-1.5 text-[11.5px] leading-[1.45] text-warning">
          <AlertTriangle size={12} className="mt-0.5 flex-none" aria-hidden="true" />
          {record.reconciliation_note}
        </p>
      )}
    </div>
  );
}

function RowGroups({ rows }: { rows: StagedRow[] }) {
  const kinds = [...new Set(rows.map((row) => row.target_table))];

  if (rows.length === 0) {
    return <p className="px-3 py-3 text-[12px] text-muted">Nothing new was found in this file.</p>;
  }

  return (
    <div className="max-h-72 overflow-y-auto quiet-scroll">
      {kinds.map((kind) => {
        const group = forReview(rows.filter((row) => row.target_table === kind));

        return (
          <div key={kind} className="px-3 py-2">
            <p className="mb-1 text-[11px] font-medium tracking-wide text-muted uppercase">
              {KIND_LABELS[kind] ?? kind} · {group.length}
            </p>

            <ul className="space-y-1">
              {group.map((row) => (
                <Row key={row.id} row={row} />
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}

function Row({ row }: { row: StagedRow }) {
  const doubtful = Number(row.confidence) < CERTAIN_ENOUGH || row.issue !== null;

  const source =
    row.source_sheet && row.source_row_number
      ? `${row.source_sheet}, row ${row.source_row_number}`
      : row.source_cells.join(' · ');

  return (
    <li
      title={source || undefined}
      className="flex items-baseline gap-2 rounded-lg px-1.5 py-1 text-[12px]"
      style={doubtful ? { background: 'var(--warning-soft)' } : undefined}
    >
      <span className="w-20 flex-none tabular-nums text-muted">
        {pick(row.payload, DATE_KEYS) ?? '—'}
      </span>

      <span className="min-w-0 flex-1 truncate text-primary">
        {pick(row.payload, LABEL_KEYS) ?? 'Unnamed'}
      </span>

      <span className="flex-none tabular-nums text-primary">
        {pick(row.payload, AMOUNT_KEYS) ?? '—'}
      </span>

      {doubtful && (
        <AlertTriangle size={12} className="flex-none text-warning" aria-label={row.issue ?? 'Check this row'} />
      )}
    </li>
  );
}
