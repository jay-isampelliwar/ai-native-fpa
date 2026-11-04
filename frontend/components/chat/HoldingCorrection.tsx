'use client';

import { Check, PencilLine, X } from 'lucide-react';
import { useState } from 'react';

import type { ApprovalEdits } from '@/lib/types';

/**
 * The box that opens in the chat when the person says the worked-out units are not correct.
 *
 * It starts with the units and amount the card showed, so the person only changes what is wrong.
 * Saving sends the fixed values with the approval and the backend saves them as typed, with no
 * AI step in between. "Don't save" answers the card as rejected, so nothing is saved.
 */
export default function HoldingCorrection({
  name,
  start,
  sending,
  failure,
  onSave,
  onDiscard,
}: {
  name: string;
  start: ApprovalEdits;
  sending: boolean;
  failure?: string;
  onSave: (edits: ApprovalEdits) => void;
  onDiscard: () => void;
}) {
  const [units, setUnits] = useState(start.units ?? '');
  const [amount, setAmount] = useState(start.amount ?? '');

  const unitsError = numberError(units, true);
  const amountError = numberError(amount, false);
  const ready = !unitsError && !amountError && !sending;

  function save() {
    if (!ready) return;

    onSave({ units: units.trim(), amount: amount.trim() });
  }

  return (
    <div className="mt-2 overflow-hidden rounded-xl border border-line bg-panel">
      <div className="flex items-center gap-2 border-b border-line px-3 py-2.5">
        <PencilLine size={15} className="flex-none text-accent" aria-hidden="true" />
        <span className="text-[12.5px] font-medium text-primary">What are the correct values for {name}?</span>
      </div>

      <form
        className="grid gap-3 px-3 py-3 sm:grid-cols-2"
        onSubmit={(event) => {
          event.preventDefault();
          save();
        }}
      >
        <NumberField label="Units" value={units} error={unitsError} disabled={sending} onChange={setUnits} />
        <NumberField label="Amount invested (₹)" value={amount} error={amountError} disabled={sending} onChange={setAmount} />
        <button type="submit" hidden aria-hidden="true" tabIndex={-1} />
      </form>

      {failure && <p className="px-3 pb-1 text-[11.5px] text-negative">{failure}</p>}

      <div className="flex flex-wrap items-center gap-2 border-t border-line px-3 py-2.5">
        <button
          type="button"
          disabled={!ready}
          onClick={save}
          className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12.5px] font-medium text-white transition disabled:cursor-not-allowed disabled:opacity-40"
          style={{ background: 'var(--accent)' }}
        >
          <Check size={14} aria-hidden="true" />
          Save these values
        </button>

        <button
          type="button"
          disabled={sending}
          onClick={onDiscard}
          className="flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-[12.5px] text-secondary transition hover:text-primary disabled:opacity-40"
        >
          <X size={14} aria-hidden="true" />
          Don&apos;t save
        </button>

        <span className="ml-auto text-[11px] text-muted">Saved exactly as you type them</span>
      </div>
    </div>
  );
}

function NumberField({
  label,
  value,
  error,
  disabled,
  onChange,
}: {
  label: string;
  value: string;
  error?: string;
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1 text-[12px]">
      <span className="text-muted">{label}</span>
      <input
        inputMode="decimal"
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        aria-invalid={Boolean(error)}
        className="rounded-lg border border-line bg-panel-subtle px-2.5 py-1.5 text-[13px] text-primary tabular-nums outline-none focus:border-[var(--accent)] disabled:opacity-60"
      />
      {error && <span className="text-[11px] text-negative">{error}</span>}
    </label>
  );
}

/** Why a typed number cannot be saved, or nothing when it can. Units may be 0, an amount may not. */
function numberError(value: string, zeroAllowed: boolean): string | undefined {
  const trimmed = value.trim();

  if (!trimmed) return 'Enter a number';

  if (!/^\d+(\.\d+)?$/.test(trimmed)) return 'Use only digits and one dot';

  const number = Number(trimmed);

  if (zeroAllowed ? number < 0 : number <= 0) return zeroAllowed ? 'Cannot be below 0' : 'Must be more than 0';

  return undefined;
}
