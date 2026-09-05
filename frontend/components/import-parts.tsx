'use client';

import { useState } from 'react';

import { Card } from '@/components/blocks';
import { documents } from '@/lib/api';
import { rupees, toNumber } from '@/lib/format';
import type { ImportRead, MappingSheet, StagedRow, StagedRowsPage } from '@/lib/types';

/**
 * The pieces one import is drawn from, owned by nothing and rendered wherever the import is.
 *
 * These were the body of a dedicated screen. They live apart from it now because the import happens
 * in the conversation, and a card that only compiles inside a page route cannot appear in a turn.
 * Nothing here fetches on mount or holds a status — the caller drives the flow and passes down what
 * it has, so the same summary renders identically whether it is polling or finished.
 *
 * `Mapping` is the exception and calls the backend itself. Proposing a mapping is a request a person
 * makes by pressing a button, not state the import arrives with, and threading two more callbacks up
 * to the caller would buy nothing but indirection.
 *
 * Widths are set for a 760px conversation column rather than a page. The staged table scrolls
 * sideways inside its own box: a row that wraps onto three lines is unreadable, and a chat that
 * scrolls sideways as a whole is worse.
 */

export const CANONICAL_FIELDS = [
  'instrument_name',
  'isin',
  'symbol',
  'quantity',
  'average_cost',
  'last_price',
  'invested_value',
  'current_value',
  'folio_id',
  'source',
  'asset_type',
] as const;

export function ImportSummary({ record }: { record: ImportRead }) {
  const stated = record.statement_totals ?? {};
  const computed = record.computed_totals ?? {};

  return (
    <Card
      title={record.filename}
      subtitle={
        record.template_id
          ? `Read as ${record.template_id}`
          : record.status === 'needs_mapping'
            ? 'This layout has not been seen before'
            : undefined
      }
      right={<StatusChip status={record.status} />}
    >
      {record.error && record.status === 'failed' && (
        <p className="text-[12.5px] leading-5 text-[#8f4227]">{record.error}</p>
      )}

      {record.status === 'extracted' && (
        <div className="space-y-3">
          <p className="text-[12.5px] leading-5 text-[#4d6560]">
            {record.row_count} row{record.row_count === 1 ? '' : 's'} read.
          </p>

          {record.reconciled !== null && (
            <div
              className={`rounded-xl border px-3.5 py-3 ${
                record.reconciled
                  ? 'border-[#00947a]/30 bg-[#00947a]/8'
                  : 'border-[#bf8410]/30 bg-[#bf8410]/8'
              }`}
            >
              <p
                className={`text-[12.5px] font-medium leading-5 ${
                  record.reconciled ? 'text-[#0f5f50]' : 'text-[#8a5a12]'
                }`}
              >
                {record.reconciled ? 'Reconciled' : 'Does not reconcile'}
              </p>

              {record.reconciliation_note && (
                <p className="mt-0.5 text-[11.5px] leading-4 text-[#5d7470]">
                  {record.reconciliation_note}
                </p>
              )}

              {Object.keys(stated).length > 0 && (
                <dl className="mt-2.5 space-y-1">
                  {Object.entries(stated).map(([field, value]) => (
                    <div key={field} className="flex items-baseline justify-between gap-3">
                      <dt className="text-[11.5px] capitalize text-[#5d7470]">
                        {field.replace(/_/g, ' ')}
                      </dt>
                      <dd className="text-[11.5px] tabular-nums text-[#4d6560]">
                        statement {rupees(toNumber(value))} · read{' '}
                        {rupees(toNumber(computed[field]))}
                      </dd>
                    </div>
                  ))}
                </dl>
              )}
            </div>
          )}
        </div>
      )}

      {record.status === 'committed' && (
        <p className="text-[12.5px] leading-5 text-[#0f5f50]">
          Committed as {record.import_batch_id}. Every record from this file carries that batch id.
        </p>
      )}
    </Card>
  );
}

export function StatusChip({ status }: { status: ImportRead['status'] }) {
  const tone =
    status === 'failed'
      ? 'border-[#b83f28]/28 bg-[#b83f28]/8 text-[#8f4227]'
      : status === 'committed'
        ? 'border-[#00947a]/30 bg-[#00947a]/10 text-[#0f5f50]'
        : status === 'needs_mapping'
          ? 'border-[#bf8410]/28 bg-[#bf8410]/8 text-[#8a5a12]'
          : 'border-[#18312f]/12 bg-[#f5f2e8]/70 text-[#5d7470]';

  return (
    <span className={`shrink-0 rounded-full border px-2.5 py-1 text-[10.5px] font-medium ${tone}`}>
      {status.replace(/_/g, ' ')}
    </span>
  );
}

/**
 * The staging table, least confident first.
 *
 * Confidence ordering is the whole point of the column: a row extraction was unsure about is where a
 * person's attention is worth spending, and a table sorted by anything else buries it among ninety
 * rows that are fine.
 */
export function Reconcile({
  rows,
  busy,
  onDecideAll,
  onDecideRow,
  onCommit,
}: {
  rows: StagedRowsPage;
  busy: boolean;
  onDecideAll: (status: 'accepted' | 'rejected') => Promise<void>;
  onDecideRow: (row: StagedRow, status: 'accepted' | 'rejected') => Promise<void>;
  onCommit: () => Promise<void>;
}) {
  return (
    <Card
      title="What was read"
      subtitle={`${rows.accepted} accepted · ${rows.pending} pending · ${rows.rejected} rejected · ${rows.duplicates} already on record`}
      note="Only accepted rows are written, and they are written together under one batch id or not at all."
      right={
        <div className="flex shrink-0 gap-2">
          <button
            type="button"
            onClick={() => void onDecideAll('accepted')}
            className="rounded-full border border-[#18312f]/15 bg-white px-3 py-1.5 text-[11.5px] font-medium text-[#4d6560] transition hover:border-[#00947a] hover:text-[#18312f]"
          >
            Accept all
          </button>

          <button
            type="button"
            onClick={() => void onCommit()}
            disabled={busy || rows.accepted === 0}
            className="rounded-full bg-[#183f3a] px-3.5 py-1.5 text-[11.5px] font-semibold text-white transition hover:bg-[#0d322e] disabled:cursor-not-allowed disabled:opacity-40"
          >
            Commit {rows.accepted > 0 ? rows.accepted : ''}
          </button>
        </div>
      }
    >
      <div className="no-scrollbar -mx-5 max-h-[26rem] overflow-auto px-5">
        <table className="w-full min-w-[38rem] border-collapse">
          <thead className="sticky top-0 bg-white/95 backdrop-blur">
            <tr className="border-b border-[#18312f]/9">
              {['Row', 'Confidence', 'Status', ''].map((heading, index) => (
                <th
                  key={heading || index}
                  scope="col"
                  className={`pb-2 text-[10.5px] uppercase leading-4 tracking-[0.07em] text-[#8ba09c] ${
                    index === 0 ? 'text-left' : 'text-right'
                  }`}
                >
                  {heading}
                </th>
              ))}
            </tr>
          </thead>

          <tbody>
            {rows.rows.map((row) => {
              const confidence = toNumber(row.confidence);
              const doubtful = confidence < 0.9;

              return (
                <tr key={row.id} className="border-b border-[#18312f]/6 last:border-0 align-top">
                  <td className="max-w-[22rem] py-2.5 text-left">
                    <span className="block truncate text-[12.5px] text-[#18312f]">
                      {describe(row)}
                    </span>

                    {row.issue && (
                      <span className="mt-0.5 block text-[11px] leading-4 text-[#8a5a12]">
                        {row.issue}
                      </span>
                    )}
                  </td>

                  <td className="py-2.5 text-right text-[11.5px] tabular-nums">
                    <span className={doubtful ? 'text-[#8a5a12]' : 'text-[#8ba09c]'}>
                      {(confidence * 100).toFixed(0)}%
                    </span>
                  </td>

                  <td className="py-2.5 text-right text-[11.5px] capitalize text-[#5d7470]">
                    {row.status}
                  </td>

                  <td className="py-2.5 text-right">
                    <div className="flex justify-end gap-1.5">
                      <button
                        type="button"
                        onClick={() => void onDecideRow(row, 'accepted')}
                        className="rounded-full border border-[#00947a]/35 px-2 py-0.5 text-[10.5px] text-[#0f5f50] transition hover:bg-[#00947a]/10"
                      >
                        Keep
                      </button>

                      <button
                        type="button"
                        onClick={() => void onDecideRow(row, 'rejected')}
                        className="rounded-full border border-[#18312f]/15 px-2 py-0.5 text-[10.5px] text-[#5d7470] transition hover:bg-white"
                      >
                        Drop
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export function describe(row: StagedRow): string {
  const payload = row.payload as Record<string, string | null>;

  if (row.target_table === 'holdings') {
    const units = payload.quantity ?? '—';
    const value = payload.current_value ?? payload.invested_value;

    return `${payload.instrument_name ?? 'Unnamed'} · ${units} units${value ? ` · ${value}` : ''}`;
  }

  return `${payload.occurred_on ?? '—'} · ${payload.merchant ?? ''} · ${payload.amount ?? ''}`;
}

/**
 * The mapping step for a layout nothing recognises.
 *
 * The proposal comes from a model reading column headings and masked samples — never the data, and
 * never the rows above the header, which in one real format hold a name, a mobile number and a PAN.
 * It is validated before it is shown, so a person is judging a plausible mapping rather than catching
 * a broken one, and their confirmation is what turns it into a template.
 */
export function Mapping({
  userId,
  importId,
  onConfirmed,
}: {
  userId: number;
  importId: string;
  onConfirmed: (record: ImportRead) => Promise<void>;
}) {
  const [sheets, setSheets] = useState<MappingSheet[] | null>(null);
  const [provider, setProvider] = useState('');
  const [problems, setProblems] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  async function propose() {
    setBusy(true);
    setFailed(null);

    try {
      const proposal = await documents.proposeMapping(userId, importId);

      setSheets(proposal.sheets);
      setProvider(proposal.provider === 'unknown' ? '' : proposal.provider);
      setProblems(proposal.problems);
    } catch {
      setFailed('A mapping could not be suggested. You can still set the columns yourself.');
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    if (!sheets || !provider.trim()) return;

    setBusy(true);

    try {
      const updated = await documents.confirmMapping(
        userId,
        importId,
        provider.trim(),
        `${provider.trim()} holdings`,
        sheets,
      );

      await onConfirmed(updated);
    } finally {
      setBusy(false);
    }
  }

  function setField(sheetName: string, field: string, header: string) {
    setSheets((current) =>
      (current ?? []).map((sheet) => {
        if (sheet.sheet !== sheetName) return sheet;

        const mapping = { ...sheet.mapping };

        if (header) mapping[field] = header;
        else delete mapping[field];

        return { ...sheet, mapping };
      }),
    );
  }

  return (
    <Card
      title="This layout needs mapping once"
      subtitle="Tell me what each column means and every later file of this shape imports without asking."
      note="The suggestion is made from column headings and masked samples only — never from your figures."
    >
      {!sheets && (
        <button
          type="button"
          onClick={() => void propose()}
          disabled={busy}
          className="rounded-full bg-[#e7a14d] px-4 py-2 text-[12.5px] font-semibold text-[#18312f] transition hover:bg-[#dda044] disabled:opacity-50"
        >
          {busy ? 'Reading the headings…' : 'Suggest a mapping'}
        </button>
      )}

      {failed && <p className="mt-2 text-[12px] leading-5 text-[#8f4227]">{failed}</p>}

      {problems.length > 0 && (
        <ul className="mb-3 space-y-1">
          {problems.map((problem) => (
            <li key={problem} className="text-[11.5px] leading-4 text-[#8a5a12]">
              {problem}
            </li>
          ))}
        </ul>
      )}

      {sheets && (
        <div className="space-y-4">
          {sheets.map((sheet) => (
            <div key={sheet.sheet}>
              <p className="text-[12px] font-semibold uppercase tracking-[0.07em] text-[#8ba09c]">
                {sheet.sheet}
              </p>

              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                {CANONICAL_FIELDS.map((field) => (
                  <label key={field} className="flex items-center gap-2">
                    <span className="w-[7.5rem] shrink-0 text-[11.5px] capitalize text-[#5d7470]">
                      {field.replace(/_/g, ' ')}
                    </span>

                    <select
                      value={sheet.mapping[field] ?? ''}
                      onChange={(event) => setField(sheet.sheet, field, event.target.value)}
                      className="min-w-0 flex-1 rounded-lg border border-[#18312f]/12 bg-white px-2 py-1 text-[11.5px] text-[#18312f] outline-none focus:border-[#00947a]"
                    >
                      <option value="">—</option>
                      {sheet.columns.map((column) => (
                        <option key={column.index} value={column.header}>
                          {column.header}
                        </option>
                      ))}
                    </select>
                  </label>
                ))}
              </div>
            </div>
          ))}

          <div className="flex flex-wrap items-center gap-2 border-t border-[#18312f]/8 pt-3">
            <input
              value={provider}
              onChange={(event) => setProvider(event.target.value)}
              placeholder="Who is this from? e.g. zerodha"
              className="min-w-[12rem] flex-1 rounded-lg border border-[#18312f]/12 bg-white px-3 py-1.5 text-[12.5px] text-[#18312f] outline-none placeholder:text-[#a8b8b4] focus:border-[#00947a]"
            />

            <button
              type="button"
              onClick={() => void confirm()}
              disabled={busy || !provider.trim()}
              className="rounded-full bg-[#183f3a] px-4 py-2 text-[12.5px] font-semibold text-white transition hover:bg-[#0d322e] disabled:opacity-40"
            >
              {busy ? 'Saving…' : 'Confirm and read the file'}
            </button>
          </div>
        </div>
      )}
    </Card>
  );
}
