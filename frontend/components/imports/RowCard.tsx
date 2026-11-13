'use client';

import { AlertTriangle, ArrowRight, Check, Eye, Loader2, Pencil, RotateCcw, Trash2, X } from 'lucide-react';
import { useState } from 'react';

import InstrumentSearch from '@/components/imports/InstrumentSearch';
import { HIDDEN_FIELDS, effectiveData, errorField, humanize, rowTitle, showValue } from '@/lib/imports';
import type { ImportFields, ImportRowView, RowEdit } from '@/lib/types';

/**
 * One row of an upload: what it would save, old against new for an update, its errors, and an
 * edit form for any field. A holding's stock or fund is picked from a search, not typed free.
 */

const ACTION_LABELS: Record<string, { label: string; tone: string }> = {
  create: { label: 'New', tone: 'bg-accent-soft text-accent' },
  update: { label: 'Update', tone: 'bg-warning-soft text-warning' },
  no_change: { label: 'No change', tone: 'bg-panel text-muted' },
};

const STATUS_LABELS: Record<string, { label: string; tone: string }> = {
  written: { label: 'Saved', tone: 'bg-positive-soft text-positive' },
  failed: { label: 'Not saved', tone: 'bg-negative-soft text-negative' },
  rejected: { label: 'Skipped', tone: 'bg-panel text-muted' },
  undone: { label: 'Undone', tone: 'bg-panel text-muted' },
};

const INPUT =
  'w-full rounded-lg border border-line bg-panel px-2.5 py-1.5 text-[13px] text-primary placeholder:text-muted focus:border-accent focus:outline-none';

function badgeFor(row: ImportRowView): { label: string; tone: string } | null {
  if (row.resolved.removed) return { label: 'Removed', tone: 'bg-panel text-muted' };

  if (STATUS_LABELS[row.status]) return STATUS_LABELS[row.status];

  return row.action ? ACTION_LABELS[row.action] : null;
}

export default function RowCard({
  row,
  fields,
  busy,
  onEdit,
  onRemove,
}: {
  row: ImportRowView;
  fields: ImportFields | null;
  busy: boolean;
  onEdit: (row: ImportRowView, edit: RowEdit) => Promise<boolean>;
  /** Take the row out of the import, or bring it back when `removed` is false. */
  onRemove: (row: ImportRowView, removed: boolean) => void;
}) {
  const [editing, setEditing] = useState(false);
  const kinds = fields?.tables[row.target_table] ?? {};
  const data = effectiveData(row);
  const changes = row.resolved.changes ?? {};
  const badge = badgeFor(row);
  const removed = Boolean(row.resolved.removed);
  const editable = !removed && (row.status === 'proposed' || row.status === 'failed');
  const removable = !removed && (editable || (row.status === 'rejected' && Boolean(row.resolved.skipped)));

  const shown = Object.keys(data).filter((name) => !HIDDEN_FIELDS.has(name) && data[name] !== null && data[name] !== undefined);

  return (
    <li className={`rounded-xl border bg-panel px-3 py-2.5 ${row.errors.length && editable ? 'border-[var(--warning)]' : 'border-line'} ${removed ? 'opacity-60' : ''}`}>
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13px] font-medium text-primary">{rowTitle(row)}</p>
          <p className="text-[11.5px] text-muted">
            Row {row.row_number}
            {row.source.sheet ? ` · ${row.source.sheet}` : ''}
            {row.source.row ? `, line ${row.source.row}` : ''}
          </p>
        </div>

        {row.source.read_by_model && (
          <span className="flex flex-none items-center gap-1 rounded-md bg-warning-soft px-2 py-0.5 text-[11px] font-medium text-warning" title="Read by the model. Check each value against the file.">
            <Eye size={11} aria-hidden="true" /> Check
          </span>
        )}

        {badge && <span className={`flex-none rounded-md px-2 py-0.5 text-[11px] font-medium ${badge.tone}`}>{badge.label}</span>}

        {editable && !editing && (
          <button type="button" onClick={() => setEditing(true)} aria-label={`Edit row ${row.row_number}`} title="Edit" className="icon-pill h-7 w-7 flex-none">
            <Pencil size={12} aria-hidden="true" />
          </button>
        )}

        {removable && !editing && (
          <button
            type="button"
            disabled={busy}
            onClick={() => onRemove(row, true)}
            aria-label={`Remove row ${row.row_number} from this import`}
            title="Remove from this import"
            className="icon-pill h-7 w-7 flex-none hover:text-negative disabled:opacity-40"
          >
            <Trash2 size={12} aria-hidden="true" />
          </button>
        )}

        {removed && (
          <button type="button" disabled={busy} onClick={() => onRemove(row, false)} className="chip-button h-7 flex-none gap-1 px-2.5 text-[12px] disabled:opacity-40">
            <RotateCcw size={12} aria-hidden="true" />
            Bring back
          </button>
        )}
      </div>

      {!editing && !removed && (
        <dl className="mt-2 grid grid-cols-[minmax(7rem,11rem)_minmax(0,1fr)] gap-x-4 gap-y-1 text-[12.5px]">
          {shown.map((name) => (
            <div key={name} className="contents">
              <dt className="truncate text-secondary">{humanize(name)}</dt>
              <dd className="min-w-0 truncate text-primary tabular-nums">
                {name in changes ? (
                  <span className="inline-flex items-center gap-1.5">
                    <span className="text-muted line-through">{showValue(changes[name], kinds[name])}</span>
                    <ArrowRight size={11} className="text-muted" aria-hidden="true" />
                    {showValue(data[name], kinds[name])}
                  </span>
                ) : (
                  showValue(data[name], kinds[name])
                )}
              </dd>
            </div>
          ))}
        </dl>
      )}

      {editing && (
        <RowEditor
          row={row}
          fields={fields}
          busy={busy}
          onCancel={() => setEditing(false)}
          onSave={async (edit) => {
            if (await onEdit(row, edit)) setEditing(false);
          }}
        />
      )}

      {editable && row.errors.length > 0 && (
        <ul className="mt-2 space-y-1">
          {row.errors.map((error) => (
            <li key={error} className="flex items-start gap-1.5 text-[12px] leading-[1.45] text-warning">
              <AlertTriangle size={12} className="mt-0.5 flex-none" aria-hidden="true" />
              {error}
            </li>
          ))}
        </ul>
      )}

      {row.warnings.length > 0 && (
        <ul className="mt-1.5 space-y-1">
          {row.warnings.map((warning) => (
            <li key={warning} className="text-[12px] leading-[1.45] text-muted">
              {warning}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

function RowEditor({
  row,
  fields,
  busy,
  onCancel,
  onSave,
}: {
  row: ImportRowView;
  fields: ImportFields | null;
  busy: boolean;
  onCancel: () => void;
  onSave: (edit: RowEdit) => void;
}) {
  const kinds = fields?.tables[row.target_table] ?? {};
  const data = effectiveData(row);
  const wanted = new Set([...Object.keys(data), ...row.errors.map(errorField)]);
  const names = Object.keys(kinds).filter((name) => wanted.has(name) && !HIDDEN_FIELDS.has(name) && name !== 'security_name');
  const [values, setValues] = useState<Record<string, unknown>>(() => Object.fromEntries(names.map((name) => [name, data[name] ?? ''])));
  const [instrument, setInstrument] = useState<string | undefined>(undefined);
  const holding = row.target_table === 'holdings';

  function changed(): Record<string, unknown> {
    return Object.fromEntries(Object.entries(values).filter(([name, value]) => String(value ?? '') !== String(data[name] ?? '')));
  }

  return (
    <form
      className="mt-2.5 space-y-2.5"
      onSubmit={(event) => {
        event.preventDefault();
        onSave({ changes: changed(), ...(instrument ? { instrument } : {}) });
      }}
    >
      {holding && (
        <label className="block">
          <span className="mb-1 block text-[11.5px] font-medium text-secondary">Fund or stock</span>
          <InstrumentSearch
            initial={row.resolved.instrument?.name ?? String(data.security_name ?? '')}
            onPick={(choice) => setInstrument(choice.value)}
          />
        </label>
      )}

      <div className="grid gap-2.5 sm:grid-cols-2">
        {names.map((name) => (
          <Field
            key={name}
            name={name}
            kind={kinds[name]}
            choices={fields?.choices[kinds[name]]}
            value={values[name]}
            onChange={(value) => setValues((current) => ({ ...current, [name]: value }))}
          />
        ))}
      </div>

      <div className="flex items-center gap-2">
        <button
          type="submit"
          disabled={busy}
          className="send-gradient flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12.5px] font-semibold disabled:opacity-40"
        >
          {busy ? <Loader2 size={13} className="animate-spin" aria-hidden="true" /> : <Check size={13} aria-hidden="true" />}
          Save
        </button>
        <button type="button" onClick={onCancel} className="chip-button gap-1.5 px-3 py-1.5 text-[12.5px]">
          <X size={13} aria-hidden="true" />
          Cancel
        </button>
      </div>
    </form>
  );
}

function Field({
  name,
  kind,
  choices,
  value,
  onChange,
}: {
  name: string;
  kind: string | undefined;
  choices: string[] | undefined;
  value: unknown;
  onChange: (value: unknown) => void;
}) {
  const id = `field-${name}`;

  if (kind === 'bool') {
    return (
      <label htmlFor={id} className="flex items-center gap-2 self-end py-1.5 text-[13px] text-primary">
        <input id={id} type="checkbox" checked={value === true} onChange={(event) => onChange(event.target.checked)} className="h-4 w-4 accent-[var(--accent)]" />
        {humanize(name)}
      </label>
    );
  }

  return (
    <label htmlFor={id} className="block">
      <span className="mb-1 block text-[11.5px] font-medium text-secondary">{humanize(name)}</span>

      {choices ? (
        <select id={id} value={String(value ?? '')} onChange={(event) => onChange(event.target.value)} className={INPUT}>
          <option value="">Not set</option>
          {choices.map((choice) => (
            <option key={choice} value={choice}>
              {humanize(choice)}
            </option>
          ))}
        </select>
      ) : (
        <input
          id={id}
          type={kind === 'date' ? 'date' : 'text'}
          inputMode={kind === 'money' || kind === 'units' || kind === 'rate' || kind === 'int' || kind === 'year' ? 'decimal' : undefined}
          value={String(value ?? '')}
          onChange={(event) => onChange(event.target.value)}
          className={INPUT}
        />
      )}
    </label>
  );
}
