'use client';

import { LoaderCircle, SendHorizontal, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { cleanValue, FORMS, inputValue, problemWith, type FieldSpec } from '@/lib/forms';
import type { FormKind, FormValue } from '@/lib/types';

/**
 * The form the planner opened, drawn beside the chat.
 *
 * It starts with the values the agent already knew. Send hands the cleaned values to the chat,
 * which sends them to the agent as the person's next message. Close just closes it: the agent is not
 * told, and the reply that opened it keeps an "Open form" button to bring it back.
 *
 * The panel itself does not decide where it sits. The chat places it on the right half of the screen,
 * or over the whole screen on a phone.
 */

const INPUT =
  'w-full rounded-xl border border-line bg-panel px-3.5 py-2.5 text-[14px] text-primary transition placeholder:text-muted focus:border-accent focus:outline-none';

export default function FormPanel({
  kind,
  initial,
  editing,
  busy,
  onSend,
  onClose,
}: {
  kind: FormKind;
  initial: Record<string, FormValue>;
  /** Set when the form changes a saved item rather than adding one. */
  editing: boolean;
  /** True while a reply is being written, so a second message cannot start. */
  busy: boolean;
  onSend: (values: Record<string, FormValue>) => void;
  onClose: () => void;
}) {
  const spec = FORMS[kind];
  const [values, setValues] = useState<Record<string, FormValue>>(initial);
  const [problem, setProblem] = useState<string | null>(null);
  const first = useRef<HTMLDivElement>(null);

  useEffect(() => {
    first.current?.querySelector<HTMLElement>('input, select')?.focus();
  }, []);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose();
    }

    window.addEventListener('keydown', onKey);

    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  function set(name: string, value: FormValue) {
    setProblem(null);
    setValues((current) => ({ ...current, [name]: value }));
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();

    const found = problemWith(spec, values);

    if (found) {
      setProblem(found);
      return;
    }

    const cleaned: Record<string, FormValue> = {};

    for (const field of spec.fields) {
      const value = cleanValue(field, values[field.name]);

      if (value !== undefined) cleaned[field.name] = value;
    }

    onSend(cleaned);
  }

  return (
    <form onSubmit={submit} noValidate className="flex h-full min-h-0 flex-col" aria-label={`${spec.title} form`}>
      <header className="flex items-start gap-3 px-5 pt-5 pb-3 sm:px-6">
        <div className="min-w-0">
          <p className="text-[11.5px] font-medium tracking-wide text-accent uppercase">{editing ? 'Change details' : 'Add details'}</p>
          <h2 className="mt-0.5 text-[20px] font-semibold tracking-[-0.01em] text-primary">{spec.title}</h2>
          <p className="mt-1 text-[13px] text-secondary">{spec.lead}</p>
        </div>

        <button type="button" onClick={onClose} aria-label="Close form" title="Close" className="icon-pill ml-auto h-8 w-8">
          <X size={15} aria-hidden="true" />
        </button>
      </header>

      <div ref={first} className="quiet-scroll min-h-0 flex-1 overflow-y-auto px-5 pb-4 sm:px-6">
        <div className="grid gap-4 sm:grid-cols-2">
          {spec.fields.map((field) => (
            <Field key={field.name} field={field} value={values[field.name]} onChange={(value) => set(field.name, value)} />
          ))}
        </div>
      </div>

      <footer className="border-t border-[var(--pane-border)] px-5 py-4 sm:px-6">
        {problem && (
          <p role="alert" className="mb-3 text-[12.5px] text-negative">
            {problem}
          </p>
        )}

        <div className="flex items-center gap-3">
          <p className="text-[12px] text-muted">The planner checks these before saving.</p>

          <button
            type="submit"
            disabled={busy}
            className="ml-auto flex h-10 items-center gap-2 rounded-xl px-5 text-[13.5px] font-semibold transition disabled:cursor-not-allowed disabled:opacity-50"
            style={{ background: 'var(--gradient-send)', color: 'var(--on-accent)' }}
          >
            {busy ? <LoaderCircle size={15} className="animate-spin" aria-hidden="true" /> : <SendHorizontal size={15} aria-hidden="true" />}
            Send details
          </button>
        </div>
      </footer>
    </form>
  );
}

function Field({ field, value, onChange }: { field: FieldSpec; value: FormValue | undefined; onChange: (value: FormValue) => void }) {
  const id = `form-${field.name}`;
  const wide = field.type === 'text' && (field.name === 'name' || field.name === 'instrument_name');

  if (field.type === 'boolean') {
    return (
      <label htmlFor={id} className="flex items-center gap-2.5 self-end py-2.5 text-[13.5px] text-primary">
        <input
          id={id}
          type="checkbox"
          checked={value === true || value === 'true'}
          onChange={(event) => onChange(event.target.checked)}
          className="h-4 w-4 accent-[var(--accent)]"
        />
        {field.label}
      </label>
    );
  }

  return (
    <div className={wide ? 'sm:col-span-2' : undefined}>
      <label htmlFor={id} className="mb-1.5 block text-[12px] font-medium text-secondary">
        {field.label}
        {field.required && <span className="text-accent"> *</span>}
      </label>

      {field.type === 'select' ? (
        <select id={id} value={inputValue(value)} onChange={(event) => onChange(event.target.value)} className={INPUT}>
          <option value="">Choose…</option>
          {field.options?.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      ) : (
        <div className="relative">
          {field.type === 'money' && (
            <span className="pointer-events-none absolute top-1/2 left-3.5 -translate-y-1/2 text-[14px] text-muted">₹</span>
          )}

          <input
            id={id}
            type={field.type === 'date' ? 'date' : 'text'}
            inputMode={['money', 'number', 'percent', 'year'].includes(field.type) ? 'decimal' : undefined}
            value={inputValue(value)}
            placeholder={field.placeholder}
            onChange={(event) => onChange(event.target.value)}
            className={`${INPUT} ${field.type === 'money' ? 'pl-7' : ''} ${field.type === 'percent' ? 'pr-8' : ''}`}
          />

          {field.type === 'percent' && (
            <span className="pointer-events-none absolute top-1/2 right-3.5 -translate-y-1/2 text-[14px] text-muted">%</span>
          )}
        </div>
      )}

      {field.hint && <p className="mt-1 text-[11.5px] text-muted">{field.hint}</p>}
    </div>
  );
}
