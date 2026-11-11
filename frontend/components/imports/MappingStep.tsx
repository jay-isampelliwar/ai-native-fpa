'use client';

import { AlertTriangle, Check, Loader2 } from 'lucide-react';
import { useState } from 'react';

import { HIDDEN_FIELDS, humanize, tableLabel } from '@/lib/imports';
import type { ImportFields, PendingMapping, SheetChoice } from '@/lib/types';

/**
 * Confirming how an unknown file's columns map, sheet by sheet.
 *
 * The model's proposal is filled in, but nothing is read until the person confirms it. They can
 * change the table, set any column to "Not used", or skip the sheet. The same shape next time is
 * read with this mapping and no model.
 */

const SKIP = '';

const SELECT =
  'w-full rounded-lg border border-line bg-panel px-2.5 py-1.5 text-[13px] text-primary focus:border-accent focus:outline-none';

export default function MappingStep({
  pending,
  fields,
  busy,
  problem,
  onConfirm,
}: {
  pending: PendingMapping[];
  fields: ImportFields | null;
  busy: boolean;
  problem: string | null;
  onConfirm: (sheets: SheetChoice[]) => void;
}) {
  const [choices, setChoices] = useState<SheetChoice[]>(() =>
    pending.map((sheet) => ({
      sheet: sheet.sheet,
      target_table: sheet.target_table,
      columns: Object.fromEntries(Object.entries(sheet.columns).filter(([, field]) => !HIDDEN_FIELDS.has(field))),
    })),
  );

  const tables = Object.keys(fields?.tables ?? {});

  function update(index: number, change: (current: SheetChoice) => SheetChoice) {
    setChoices((current) => current.map((item, at) => (at === index ? change(item) : item)));
  }

  return (
    <section aria-label="Confirm columns" className="space-y-3">
      <div className="tile tone-warn px-4 py-3">
        <p className="text-[13.5px] font-medium text-primary">This file&apos;s format is not known yet</p>
        <p className="mt-1 text-[12.5px] leading-[1.5] text-secondary">
          The planner suggested where each column goes. Check it and confirm. Files of the same shape are read the same way next time.
        </p>
      </div>

      {pending.map((sheet, index) => {
        const choice = choices[index];
        const fieldNames = Object.keys(fields?.tables[choice.target_table ?? ''] ?? {}).filter((name) => !HIDDEN_FIELDS.has(name));

        return (
          <div key={sheet.fingerprint} className="rounded-xl border border-line bg-panel px-3 py-3">
            <p className="text-[13px] font-medium text-primary">Sheet: {sheet.sheet}</p>
            {sheet.reason && <p className="mt-0.5 text-[12px] text-muted">{sheet.reason}</p>}

            <label className="mt-2.5 block">
              <span className="mb-1 block text-[11.5px] font-medium text-secondary">These rows are</span>
              <select
                value={choice.target_table ?? SKIP}
                onChange={(event) =>
                  update(index, (current) => ({
                    ...current,
                    target_table: event.target.value || null,
                    columns: event.target.value === current.target_table ? current.columns : {},
                  }))
                }
                className={SELECT}
              >
                <option value={SKIP}>Skip this sheet</option>
                {tables.map((table) => (
                  <option key={table} value={table}>
                    {tableLabel(table)}
                  </option>
                ))}
              </select>
            </label>

            {choice.target_table && (
              <div className="mt-3 space-y-2">
                {sheet.headers.map((header) => (
                  <label key={header} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] items-center gap-2">
                    <span className="truncate text-[12.5px] text-primary" title={header}>
                      {header}
                    </span>
                    <select
                      value={choice.columns[header] ?? SKIP}
                      onChange={(event) =>
                        update(index, (current) => {
                          const columns = { ...current.columns };

                          if (event.target.value) columns[header] = event.target.value;
                          else delete columns[header];

                          return { ...current, columns };
                        })
                      }
                      className={SELECT}
                    >
                      <option value={SKIP}>Not used</option>
                      {fieldNames.map((name) => (
                        <option key={name} value={name}>
                          {humanize(name)}
                        </option>
                      ))}
                    </select>
                  </label>
                ))}
              </div>
            )}

            {sheet.errors.filter((error) => !error.includes('filled in by the planner')).length > 0 && (
              <ul className="mt-2 space-y-1">
                {sheet.errors.filter((error) => !error.includes('filled in by the planner')).map((error) => (
                  <li key={error} className="flex items-start gap-1.5 text-[12px] text-warning">
                    <AlertTriangle size={12} className="mt-0.5 flex-none" aria-hidden="true" />
                    {error}
                  </li>
                ))}
              </ul>
            )}
          </div>
        );
      })}

      {problem && <p role="alert" className="text-[12.5px] text-negative">{problem}</p>}

      <button
        type="button"
        disabled={busy}
        onClick={() => onConfirm(choices)}
        className="send-gradient flex h-9 items-center gap-1.5 rounded-lg px-4 text-[13px] font-semibold disabled:opacity-40"
      >
        {busy ? <Loader2 size={14} className="animate-spin" aria-hidden="true" /> : <Check size={14} aria-hidden="true" />}
        Confirm and read the file
      </button>
    </section>
  );
}
