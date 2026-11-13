'use client';

import { AlertTriangle, CalendarDays, CheckCircle2, ChevronDown, Columns3, Eye, Loader2, Lock, RotateCcw, Scale, Upload, X } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import MappingStep from '@/components/imports/MappingStep';
import QuestionStepper, { openQuestions } from '@/components/imports/QuestionStepper';
import RowCard from '@/components/imports/RowCard';
import { documents } from '@/lib/api';
import { errorField, humanize, loadFields, tableLabel } from '@/lib/imports';
import type { DocumentView, ImportFields, ImportQuestion, ImportRowView, RowEdit, SheetChoice } from '@/lib/types';

/**
 * The review of one upload, beside the chat: what each sheet gave, the open questions one at a
 * time, every row by table with errors to fix in place, and the Approve and Undo buttons.
 *
 * Every change goes to the backend, which checks the whole document again and answers with it, so
 * this panel never decides anything itself. It only shows what the backend says and sends what
 * the person picks.
 */

const NOTE_TONES: Record<string, string> = {
  imported: 'text-secondary',
  empty: 'text-muted',
  not_imported: 'text-muted',
  needs_mapping: 'text-warning',
  warning: 'text-warning',
};

export default function ImportPanel({
  documentId,
  onClose,
  onChanged,
  onImported,
}: {
  documentId: number;
  onClose: () => void;
  onChanged?: (document: DocumentView) => void;
  /** Tell the chat an import was saved, so the planner can say what changed. */
  onImported?: (document: DocumentView) => void;
}) {
  const [document, setDocument] = useState<DocumentView | null>(null);
  const [fields, setFields] = useState<ImportFields | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [sheetsOpen, setSheetsOpen] = useState(false);

  const show = useCallback(
    (next: DocumentView) => {
      setDocument(next);
      onChanged?.(next);
    },
    [onChanged],
  );

  useEffect(() => {
    let live = true;

    documents
      .get(documentId)
      .then((found) => live && setDocument(found))
      .catch((error: unknown) => live && setProblem(error instanceof Error ? error.message : 'This file could not be loaded'));

    loadFields()
      .then((found) => live && setFields(found))
      .catch(() => undefined);

    return () => {
      live = false;
    };
  }, [documentId]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose();
    }

    window.addEventListener('keydown', onKey);

    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  /** Run one call, keeping its answer, or its reason when it was refused. */
  async function act<T>(call: () => Promise<T>): Promise<T | null> {
    setBusy(true);
    setProblem(null);
    setNotice(null);

    try {
      return await call();
    } catch (error) {
      setProblem(error instanceof Error ? error.message : 'That did not work. Try again.');

      return null;
    } finally {
      setBusy(false);
    }
  }

  async function answer(row: ImportRowView, question: ImportQuestion, value: string) {
    const next = await act(() => documents.answer(documentId, [{ row_id: row.id, question_id: question.id, answer: value }]));

    if (next) show(next);
  }

  async function edit(row: ImportRowView, change: RowEdit): Promise<boolean> {
    const next = await act(() => documents.editRow(documentId, row.id, change));

    if (next) show(next);

    return next !== null;
  }

  async function remove(row: ImportRowView, removed: boolean) {
    const next = await act(() => (removed ? documents.removeRow(documentId, row.id) : documents.restoreRow(documentId, row.id)));

    if (next) show(next);
  }

  async function approve() {
    const outcome = await act(() => documents.approve(documentId));

    if (!outcome) return;

    show(outcome.document);

    if (outcome.written > 0) onImported?.(outcome.document);

    setNotice(
      `Saved ${outcome.written} row${outcome.written === 1 ? '' : 's'}` +
        (outcome.no_change ? `, ${outcome.no_change} had no change` : '') +
        (outcome.failed ? `. ${outcome.failed} could not be saved; see the rows marked Not saved.` : '.'),
    );
  }

  async function undo() {
    const next = await act(() => documents.undo(documentId));

    if (next) {
      show(next);
      setNotice('The import was undone. Your records are as they were before it.');
    }
  }

  const rows = document?.rows ?? [];
  const questions = openQuestions(rows);
  const ready = document?.checks.ready ?? 0;
  const written = rows.some((row) => row.status === 'written' && row.action !== 'no_change');
  const tables = [...new Set(rows.map((row) => row.target_table))];
  const waiting = rows.filter((row) => !row.resolved.removed && (row.status === 'proposed' || row.status === 'failed')).length;
  const undated = rows.filter(
    (row) => (row.status === 'proposed' || row.status === 'failed') && row.errors.some((error) => errorField(error) === 'as_of_date'),
  ).length;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex items-start gap-3 px-5 pt-5 pb-3 sm:px-6">
        <div className="min-w-0">
          <p className="text-[11.5px] font-medium tracking-wide text-accent uppercase">Review import</p>
          <h2 className="mt-0.5 truncate text-[20px] font-semibold tracking-[-0.01em] text-primary">
            {document?.original_filename ?? 'Loading…'}
          </h2>
          {document && <Summary document={document} questions={questions.length} />}
        </div>

        <button type="button" onClick={onClose} aria-label="Close review" title="Close" className="icon-pill ml-auto h-8 w-8 flex-none">
          <X size={15} aria-hidden="true" />
        </button>
      </header>

      <div className="quiet-scroll min-h-0 flex-1 space-y-4 overflow-y-auto px-5 pb-4 sm:px-6">
        {!document && !problem && (
          <p className="flex items-center gap-2 text-[13px] text-muted">
            <Loader2 size={14} className="animate-spin" aria-hidden="true" /> Loading the file…
          </p>
        )}

        {document?.status === 'failed' && (
          <p className="rounded-xl border border-line bg-negative-soft px-3 py-2.5 text-[13px] text-negative">
            {document.error_message ?? 'This file could not be read.'}
          </p>
        )}

        {document?.status === 'needs_password' && (
          <PasswordStep
            message={document.error_message}
            busy={busy}
            onSend={async (password) => {
              const next = await act(() => documents.unlock(documentId, password));

              if (next) show(next);
            }}
          />
        )}

        {document?.status === 'needs_consent' && document.pending_pages && (
          <ConsentStep
            pages={document.pending_pages}
            locked={document.locked}
            busy={busy}
            onAllow={async (password) => {
              const next = await act(() => documents.allowModel(documentId, password));

              if (next) show(next);
            }}
          />
        )}

        {document?.status === 'parsed' && document.plans.length > 0 && !rows.some((row) => row.status === 'written') && (
          <PlanNote
            document={document}
            fields={fields}
            busy={busy}
            problem={problem}
            onConfirm={async (sheets) => {
              const next = await act(() => documents.confirmMapping(documentId, sheets));

              if (next) show(next);
            }}
          />
        )}

        {document?.status === 'needs_mapping' && (
          <MappingStep
            pending={document.pending_mappings}
            fields={fields}
            busy={busy}
            problem={problem}
            onConfirm={async (sheets) => {
              const next = await act(() => documents.confirmMapping(documentId, sheets));

              if (next) show(next);
            }}
          />
        )}

        {document && document.sheets.length > 0 && (
          <section aria-label="Sheets">
            <button
              type="button"
              onClick={() => setSheetsOpen((was) => !was)}
              className="flex w-full items-center gap-1.5 text-left text-[12px] font-medium tracking-wide text-secondary uppercase"
            >
              What each sheet gave ({document.sheets.length})
              <ChevronDown size={14} className={`ml-auto transition ${sheetsOpen ? 'rotate-180' : ''}`} aria-hidden="true" />
            </button>

            {sheetsOpen && (
              <ul className="mt-2 space-y-1.5">
                {document.sheets.map((note) => (
                  <li key={`${note.sheet}:${note.message}`} className="text-[12.5px] leading-[1.45]">
                    <span className="text-primary">{note.sheet || 'Whole file'}</span>
                    <span className={` · ${NOTE_TONES[note.outcome] ?? 'text-muted'}`}> · {note.message}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        {document && (document.status === 'parsed' || document.status === 'imported') && document.totals.length > 0 && (
          <TotalsCard
            document={document}
            busy={busy}
            onAccept={async () => {
              const next = await act(() => documents.acceptTotals(documentId));

              if (next) show(next);
            }}
          />
        )}

        {document?.status === 'parsed' && undated > 0 && (
          <DateBar
            count={undated}
            busy={busy}
            onSet={async (asOf) => {
              const next = await act(() => documents.setAsOfDate(documentId, asOf));

              if (next) show(next);
            }}
          />
        )}

        {document?.status === 'parsed' && <QuestionStepper questions={questions} busy={busy} onAnswer={(row, question, value) => void answer(row, question, value)} />}

        {tables.map((table) => {
          const group = rows.filter((row) => row.target_table === table);

          return (
            <section key={table} aria-label={tableLabel(table)}>
              <p className="mb-1.5 text-[12px] font-medium tracking-wide text-muted uppercase">
                {tableLabel(table)} · {group.length}
              </p>
              <ul className="space-y-2">
                {group.map((row) => (
                  <RowCard key={row.id} row={row} fields={fields} busy={busy} onEdit={edit} onRemove={(item, removed) => void remove(item, removed)} />
                ))}
              </ul>
            </section>
          );
        })}
      </div>

      <footer className="border-t border-[var(--pane-border)] px-5 py-4 sm:px-6">
        {problem && document?.status !== 'needs_mapping' && (
          <p role="alert" className="mb-3 text-[12.5px] text-negative">
            {problem}
          </p>
        )}

        {notice && (
          <p role="status" className="mb-3 flex items-start gap-1.5 text-[12.5px] text-positive">
            <CheckCircle2 size={13} className="mt-0.5 flex-none" aria-hidden="true" />
            {notice}
          </p>
        )}

        <div className="flex flex-wrap items-center gap-2">
          {document?.status === 'parsed' && ready === 0 && (
            <p className="text-[12.5px] text-secondary">
              {waiting} row{waiting === 1 ? '' : 's'} still need{waiting === 1 ? 's' : ''} fixing or an answer before it can be imported.
            </p>
          )}

          {document?.status === 'parsed' && ready > 0 && (
            <button
              type="button"
              disabled={busy || ready === 0 || document.totals_blocked}
              title={document.totals_blocked ? 'The totals do not match yet' : undefined}
              onClick={() => void approve()}
              className="send-gradient flex h-10 items-center gap-2 rounded-xl px-5 text-[13.5px] font-semibold disabled:cursor-not-allowed disabled:opacity-40"
            >
              {busy ? <Loader2 size={15} className="animate-spin" aria-hidden="true" /> : <Upload size={15} aria-hidden="true" />}
              Import {ready} ready row{ready === 1 ? '' : 's'}
            </button>
          )}

          {written && (
            <button type="button" disabled={busy} onClick={() => void undo()} className="chip-button h-10 gap-2 px-4 text-[13px]">
              <RotateCcw size={14} aria-hidden="true" />
              Undo import
            </button>
          )}

          <p className="ml-auto text-[12px] text-muted">Nothing is saved until you import.</p>
        </div>
      </footer>
    </div>
  );
}

function Summary({ document, questions }: { document: DocumentView; questions: number }) {
  const checks = document.checks;
  const parts: string[] = [];

  if (document.status === 'imported') parts.push('Imported');
  if (document.status === 'rejected') parts.push('Import undone');
  if (document.status === 'parsed') parts.push(`${checks.ready ?? 0} ready`);
  if (questions) parts.push(`${questions} to answer`);
  if (checks.with_errors) parts.push(`${checks.with_errors} to fix`);
  if (checks.no_change) parts.push(`${checks.no_change} no change`);

  return <p className="mt-1 text-[13px] text-secondary">{parts.join(' · ') || ' '}</p>;
}

/** Today as YYYY-MM-DD in the person's own time zone, for the date box. */
function today(): string {
  const now = new Date();

  return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

/**
 * One date for every row the file left undated, such as a broker export with no "as of" column.
 * Today is filled in, but nothing is set until the person presses the button.
 */
function DateBar({ count, busy, onSet }: { count: number; busy: boolean; onSet: (asOf: string) => void }) {
  const [asOf, setAsOf] = useState(today);

  return (
    <section aria-label="As-of date" className="tile tone-warn px-4 py-3">
      <p className="flex items-center gap-2 text-[13.5px] font-medium text-primary">
        <CalendarDays size={15} className="flex-none text-warning" aria-hidden="true" />
        {count} row{count === 1 ? ' has' : 's have'} no as-of date
      </p>
      <p className="mt-1 text-[12.5px] text-secondary">This file does not say what date its values are from. Pick the date once for all of them.</p>

      <div className="mt-2.5 flex flex-wrap items-center gap-2">
        <input
          type="date"
          value={asOf}
          max={today()}
          onChange={(event) => setAsOf(event.target.value)}
          aria-label="As-of date"
          className="rounded-lg border border-line bg-panel px-2.5 py-1.5 text-[13px] text-primary focus:border-accent focus:outline-none"
        />
        <button
          type="button"
          disabled={busy || !asOf}
          onClick={() => onSet(asOf)}
          className="send-gradient flex h-8 items-center gap-1.5 rounded-lg px-3 text-[12.5px] font-semibold disabled:opacity-40"
        >
          {busy && <Loader2 size={13} className="animate-spin" aria-hidden="true" />}
          Set for all {count}
        </button>
      </div>
    </section>
  );
}

/** The password box for a locked PDF. The password is sent once and never kept. */
function PasswordStep({ message, busy, onSend }: { message: string | null; busy: boolean; onSend: (password: string) => void }) {
  const [password, setPassword] = useState('');

  return (
    <section aria-label="Password" className="tile tone-warn px-4 py-3">
      <p className="flex items-center gap-2 text-[13.5px] font-medium text-primary">
        <Lock size={15} className="flex-none text-warning" aria-hidden="true" />
        This PDF is locked
      </p>
      <p className="mt-1 text-[12.5px] text-secondary">{message ?? 'Give its password to read it.'} The password is used once and never saved.</p>

      <form
        className="mt-2.5 flex items-center gap-2"
        onSubmit={(event) => {
          event.preventDefault();

          if (password) onSend(password);
        }}
      >
        <input
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          autoComplete="off"
          placeholder="PDF password"
          aria-label="PDF password"
          className="min-w-0 flex-1 rounded-lg border border-line bg-panel px-2.5 py-1.5 text-[13px] text-primary placeholder:text-muted focus:border-accent focus:outline-none"
        />
        <button type="submit" disabled={busy || !password} className="send-gradient flex h-8 items-center gap-1.5 rounded-lg px-3 text-[12.5px] font-semibold disabled:opacity-40">
          {busy && <Loader2 size={13} className="animate-spin" aria-hidden="true" />}
          Open
        </button>
      </form>
    </section>
  );
}

/**
 * The OK to let the model read pages code cannot: scanned pages, photos, and text with no table.
 * The whole page goes to the model, so the person is told plainly what that means before saying yes.
 */
function ConsentStep({
  pages,
  locked,
  busy,
  onAllow,
}: {
  pages: { count: number; pictures: number };
  locked: boolean;
  busy: boolean;
  onAllow: (password?: string) => void;
}) {
  const [password, setPassword] = useState('');
  const kind = pages.pictures === pages.count ? (pages.count === 1 ? 'a picture' : 'pictures') : 'pages with no table';

  return (
    <section aria-label="Let the model read it" className="tile tone-warn px-4 py-3">
      <p className="flex items-center gap-2 text-[13.5px] font-medium text-primary">
        <Eye size={15} className="flex-none text-warning" aria-hidden="true" />
        {pages.count} page{pages.count === 1 ? '' : 's'} can only be read by the model
      </p>
      <p className="mt-1 text-[12.5px] leading-[1.5] text-secondary">
        This file has {kind}, so code cannot read them. If you say yes, the whole page is sent to the model, including any name, PAN or
        account numbers on it. Every value it reads is marked so you can check it before importing.
      </p>

      <div className="mt-2.5 flex flex-wrap items-center gap-2">
        {locked && (
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="off"
            placeholder="PDF password again"
            aria-label="PDF password"
            className="min-w-0 flex-1 rounded-lg border border-line bg-panel px-2.5 py-1.5 text-[13px] text-primary placeholder:text-muted focus:border-accent focus:outline-none"
          />
        )}
        <button
          type="button"
          disabled={busy || (locked && !password)}
          onClick={() => onAllow(locked ? password : undefined)}
          className="send-gradient flex h-8 items-center gap-1.5 rounded-lg px-3 text-[12.5px] font-semibold disabled:opacity-40"
        >
          {busy && <Loader2 size={13} className="animate-spin" aria-hidden="true" />}
          Yes, let the model read it
        </button>
      </div>
    </section>
  );
}

/** The column plan each sheet was read with, and the way to change it while nothing is imported. */
function PlanNote({
  document,
  fields,
  busy,
  problem,
  onConfirm,
}: {
  document: DocumentView;
  fields: ImportFields | null;
  busy: boolean;
  problem: string | null;
  onConfirm: (sheets: SheetChoice[]) => void;
}) {
  const [changing, setChanging] = useState(false);

  if (changing) {
    return <MappingStep pending={document.plans} fields={fields} busy={busy} problem={problem} onConfirm={onConfirm} />;
  }

  return (
    <section aria-label="Column plan" className="rounded-xl border border-line bg-panel px-3 py-2.5">
      <div className="flex items-center gap-2">
        <Columns3 size={14} className="flex-none text-muted" aria-hidden="true" />
        <p className="text-[12.5px] text-secondary">Read with the planner&apos;s column plan</p>
        <button type="button" onClick={() => setChanging(true)} className="chip-button ml-auto h-7 px-2.5 text-[12px]">
          Change columns
        </button>
      </div>

      <ul className="mt-2 space-y-1">
        {document.plans.map((plan) => (
          <li key={plan.fingerprint} className="text-[12px] leading-[1.5] text-muted">
            <span className="text-primary">{plan.sheet}</span> to {plan.target_table ? tableLabel(plan.target_table) : 'skipped'}:{' '}
            {Object.entries(plan.columns)
              .map(([header, field]) => `${header} → ${humanize(field)}`)
              .join(', ')}
          </li>
        ))}
      </ul>
    </section>
  );
}

/** A rupee amount kept as text, shown with Indian grouping. */
function rupeesText(value: string): string {
  const amount = Number(value);

  return Number.isFinite(amount) ? `₹${amount.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : value;
}

/**
 * The rows checked against the totals the file prints. A mismatch blocks the import until the
 * person fixes the rows or picks Import anyway; "I will check the file" only folds this away.
 */
function TotalsCard({ document, busy, onAccept }: { document: DocumentView; busy: boolean; onAccept: () => void }) {
  const [folded, setFolded] = useState(false);
  const failed = document.totals.filter((item) => !item.ok);

  if (failed.length === 0) {
    return (
      <p className="flex items-center gap-2 rounded-xl border border-line bg-panel px-3 py-2.5 text-[12.5px] text-secondary">
        <Scale size={14} className="flex-none text-positive" aria-hidden="true" />
        The rows add up to the totals in the file ({document.totals.length} check{document.totals.length === 1 ? '' : 's'}).
      </p>
    );
  }

  if (!document.totals_blocked) {
    return (
      <p className="flex items-center gap-2 rounded-xl border border-line bg-panel px-3 py-2.5 text-[12.5px] text-secondary">
        <AlertTriangle size={14} className="flex-none text-warning" aria-hidden="true" />
        The totals do not match, and you chose to import anyway.
      </p>
    );
  }

  return (
    <section aria-label="Totals" className="tile tone-warn px-4 py-3">
      <p className="flex items-center gap-2 text-[13.5px] font-medium text-primary">
        <AlertTriangle size={15} className="flex-none text-warning" aria-hidden="true" />
        The rows do not add up to the totals in the file
      </p>

      {!folded && (
        <>
          <ul className="mt-2 space-y-2">
            {failed.map((item) => (
              <li key={`${item.sheet}:${item.label}`} className="rounded-lg border border-line bg-panel px-3 py-2 text-[12.5px]">
                <p className="text-primary">{item.label}</p>
                <p className="mt-0.5 text-muted">
                  {item.sheet} · file says {rupeesText(item.expected)} · rows give {rupeesText(item.found)} · off by {rupeesText(item.difference.replace('-', ''))}
                </p>
              </li>
            ))}
          </ul>

          <p className="mt-2 text-[12.5px] text-secondary">Fix the rows below, or import anyway if you are sure the rows are right.</p>

          <div className="mt-2.5 flex flex-wrap items-center gap-2">
            <button type="button" disabled={busy} onClick={onAccept} className="send-gradient flex h-8 items-center gap-1.5 rounded-lg px-3 text-[12.5px] font-semibold disabled:opacity-40">
              {busy && <Loader2 size={13} className="animate-spin" aria-hidden="true" />}
              Import anyway
            </button>
            <button type="button" onClick={() => setFolded(true)} className="chip-button h-8 px-3 text-[12.5px]">
              I will check the file
            </button>
          </div>
        </>
      )}
    </section>
  );
}
