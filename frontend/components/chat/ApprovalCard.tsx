'use client';

import { AlertTriangle, ArrowRight, Check, Clock, Info, X } from 'lucide-react';
import { useEffect, useState } from 'react';

import HoldingCorrection from '@/components/chat/HoldingCorrection';
import { CheckSum, EditRecord, Guard, RemoveRecord } from '@/components/icons/FinIcons';
import type {
  ApprovalAction,
  ApprovalDecision,
  ApprovalEdits,
  ApprovalField,
  ApprovalRequest,
  ApprovalState,
} from '@/lib/types';

/** The words and colours for each kind of approval, so a change never reads like a delete. */
const COPY: Record<
  ApprovalAction,
  { approve: string; keep: string; note: string; tone: string; done: string; kept: string; verb: string }
> = {
  remove: {
    approve: 'Yes, remove it',
    keep: 'No, keep it',
    note: 'Nothing is removed until you tap Yes',
    tone: 'var(--negative)',
    done: 'You approved this.',
    kept: 'You chose to keep it.',
    verb: 'removed',
  },
  change: {
    approve: 'Yes, change it',
    keep: 'No, keep it',
    note: 'Nothing changes until you tap Yes',
    tone: 'var(--accent)',
    done: 'You approved this change.',
    kept: 'You kept it as is.',
    verb: 'changed',
  },
  confirm: {
    approve: "Yes, that's right",
    keep: 'No, let me fix it',
    note: 'Nothing is saved until you tap Yes',
    tone: 'var(--accent)',
    done: 'You confirmed this, so it was saved.',
    kept: 'Not saved.',
    verb: 'saved',
  },
  run: {
    approve: 'Allow',
    keep: "Don't allow",
    note: 'Nothing happens until you approve',
    tone: 'var(--accent)',
    done: 'You allowed this.',
    kept: 'You did not allow this.',
    verb: 'done',
  },
};

/**
 * The Approve / Reject card for one risky tool the planner paused on.
 *
 * Nothing changes until the person approves. The card is written for anyone to follow: the
 * question names the real item ("Change your HDFC Flexi Cap Fund?"), small labels say what kind
 * it is, a change shows only the values that really change, a removal shows four key facts and
 * says what removing does not do, and the buttons say exactly what happens.
 *
 * Every piece comes from what the backend read before pausing, so the decision is about the real
 * record and not the model's description of it. Cards saved before these pieces existed only have
 * raw fields, and still show them as a plain list.
 *
 * A `confirm` card shows values the app worked out, such as fund units from an amount. "Correct"
 * saves them as shown; "Not correct" opens a box under the card to fix them before saving.
 *
 * The card greys itself out when `expires_at` passes, because the backend refuses a late click.
 * Once answered it stays in the chat as a one-line record of what was decided.
 */
export default function ApprovalCard({
  request,
  state,
  failure,
  onDecide,
}: {
  request: ApprovalRequest;
  state: ApprovalState;
  failure?: string;
  onDecide: (decision: ApprovalDecision, edits?: ApprovalEdits) => void;
}) {
  const expired = useExpired(request.expires_at);
  const [fixing, setFixing] = useState(false);
  const shown = state === 'pending' && expired ? 'expired' : state;
  const action = request.preview.action ?? 'remove';
  const copy = COPY[action];

  if (shown !== 'pending' && shown !== 'sending') {
    return <Outcome state={shown} action={action} title={request.preview.title} failure={failure} />;
  }

  const sending = shown === 'sending';
  const canFix = action === 'confirm' && request.preview.editable !== undefined;

  if (canFix && fixing) {
    return (
      <>
        <Summary request={request} />
        <HoldingCorrection
          name={nameOf(request)}
          start={request.preview.editable ?? {}}
          sending={sending}
          failure={failure}
          onSave={(edits) => onDecide('approve', edits)}
          onDiscard={() => onDecide('reject')}
        />
      </>
    );
  }

  const preview = request.preview;
  const plain = Boolean(preview.changes || preview.facts || preview.summary || preview.chips);

  return (
    <div className="mt-2 overflow-hidden rounded-xl border border-line bg-panel">
      {plain ? (
        <PlainBody action={action} preview={preview} />
      ) : (
        <>
          <div className="flex items-center gap-2 border-b border-line px-3 py-2.5">
            <Guard size={16} className="text-warning" />
            <span className="text-[12.5px] font-medium text-primary">{preview.title}</span>
          </div>

          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 px-3 py-2.5 text-[12px]">
            {preview.fields.map((field) => (
              <div key={field.name} className="contents">
                <dt className="text-muted">{fieldLabel(field.name)}</dt>
                <FieldValue field={field} />
              </div>
            ))}
          </dl>
        </>
      )}

      {failure && <p className="px-4 pb-2 text-[11.5px] text-negative">{failure}</p>}

      <div className="flex flex-wrap items-center gap-2 border-t border-line px-4 py-3">
        <button
          type="button"
          disabled={sending}
          onClick={() => onDecide('approve')}
          className="flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-[13px] font-semibold transition disabled:cursor-not-allowed disabled:opacity-40"
          style={{ background: copy.tone, color: action === 'remove' ? 'var(--background)' : 'var(--on-accent)' }}
        >
          {action === 'remove' ? <RemoveRecord size={16} /> : <Check size={14} aria-hidden="true" />}
          {copy.approve}
        </button>

        <button
          type="button"
          disabled={sending}
          onClick={() => (canFix ? setFixing(true) : onDecide('reject'))}
          className="flex items-center gap-1.5 rounded-lg border border-line px-3.5 py-2 text-[13px] text-secondary transition hover:text-primary disabled:opacity-40"
        >
          <X size={14} aria-hidden="true" />
          {copy.keep}
        </button>

        <span className="ml-auto text-[11px] text-muted">{copy.note}</span>
      </div>
    </div>
  );
}

/** The look of each kind of card: its icon and the soft colour behind it. */
const BADGE: Record<ApprovalAction, { icon: React.ReactNode; background: string; color: string }> = {
  change: { icon: <EditRecord size={20} />, background: 'var(--accent-soft)', color: 'var(--accent)' },
  remove: { icon: <RemoveRecord size={20} />, background: 'var(--negative-soft)', color: 'var(--negative)' },
  confirm: { icon: <CheckSum size={20} />, background: 'var(--warning-soft)', color: 'var(--warning)' },
  run: { icon: <Guard size={20} />, background: 'var(--warning-soft)', color: 'var(--warning)' },
};

/** The plain-words body: question, labels, then the changes, the facts or the sum, and a short note. */
function PlainBody({ action, preview }: { action: ApprovalAction; preview: ApprovalRequest['preview'] }) {
  const badge = BADGE[action];

  return (
    <>
      <div className="flex gap-3 px-4 pt-4 pb-3">
        <div
          className="fi-host grid h-10 w-10 flex-none place-items-center rounded-xl"
          style={{ background: badge.background, color: badge.color }}
        >
          {badge.icon}
        </div>

        <div className="min-w-0">
          <p className="text-[15.5px] leading-snug font-semibold text-primary">{preview.title}</p>
          {preview.subtitle && <p className="mt-0.5 text-[13px] text-secondary">{preview.subtitle}</p>}

          {preview.chips && preview.chips.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {preview.chips.map((chip) => (
                <span key={chip} className="rounded-full border border-line bg-panel-subtle px-2.5 py-0.5 text-[11.5px] text-secondary">
                  {chip}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      {preview.changes && preview.changes.length > 0 && (
        <div className="px-4 pb-3">
          <p className="mb-2 text-[11px] font-semibold tracking-wide text-muted uppercase">What will change</p>

          <div className="space-y-2">
            {preview.changes.map((change) => (
              <div
                key={change.label}
                className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line bg-panel-subtle px-3 py-2.5"
              >
                <span className="text-[13px] text-primary">{change.label}</span>
                <span className="flex items-center gap-2 tabular-nums">
                  <span className="text-[13px] text-muted line-through">{change.old}</span>
                  <ArrowRight size={13} className="text-muted" aria-hidden="true" />
                  <span className="text-[15px] font-bold" style={{ color: 'var(--accent)' }}>
                    {change.new}
                  </span>
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {preview.facts && preview.facts.length > 0 && (
        <div className="grid grid-cols-2 gap-2 px-4 pb-3">
          {preview.facts.map((fact) => (
            <div key={fact.label} className="rounded-xl border border-line bg-panel-subtle px-3 py-2">
              <p className="text-[11.5px] text-muted">{fact.label}</p>
              <p className="text-[14px] font-semibold text-primary tabular-nums">{fact.value}</p>
            </div>
          ))}
        </div>
      )}

      {preview.summary && (
        <div className="px-4 pb-3">
          <div className="rounded-xl border border-line bg-panel-subtle px-3 py-3 text-[13.5px] text-primary">
            {preview.summary.lead}
            <p className="text-[22px] font-bold tabular-nums" style={{ color: 'var(--accent)' }}>
              {preview.summary.big}
            </p>
            <p className="mt-1 text-[12px] text-muted">{preview.summary.how}</p>
          </div>
        </div>
      )}

      {preview.note && (
        <div className="px-4 pb-3">
          <div
            className="flex items-start gap-2 rounded-xl px-3 py-2.5 text-[12.5px] text-primary"
            style={{
              background:
                preview.note.tone === 'warn'
                  ? 'var(--warning-soft, rgba(243,178,60,0.12))'
                  : 'var(--accent-soft, rgba(63,212,122,0.12))',
            }}
          >
            {preview.note.tone === 'warn' ? (
              <AlertTriangle size={14} className="mt-0.5 flex-none text-warning" aria-hidden="true" />
            ) : (
              <Info size={14} className="mt-0.5 flex-none" style={{ color: 'var(--accent)' }} aria-hidden="true" />
            )}
            {preview.note.text}
          </div>
        </div>
      )}
    </>
  );
}

/** The confirm card folded to its title and fields once the person chose to fix the values. */
function Summary({ request }: { request: ApprovalRequest }) {
  return (
    <div className="mt-2 rounded-xl border border-line bg-panel-subtle px-3 py-2 text-[12px]">
      <span className="text-muted">{request.preview.subtitle ?? request.preview.title} </span>
      <span className="inline-flex items-center gap-1 text-secondary">
        <X size={13} aria-hidden="true" />
        You said this is not right.
      </span>
    </div>
  );
}

/** The instrument's name from the card's fields, or a plain word when the card has none. */
function nameOf(request: ApprovalRequest): string {
  return request.preview.subtitle ?? request.preview.fields.find((field) => field.name === 'name')?.value ?? 'this holding';
}

/** A removed field's value, or a changed field's saved value struck through next to its new one. */
function FieldValue({ field }: { field: ApprovalField }) {
  if (field.new === undefined) {
    return <dd className="min-w-0 truncate text-primary tabular-nums">{field.value}</dd>;
  }

  return (
    <dd className="flex min-w-0 items-center gap-1.5 tabular-nums">
      <span className="truncate text-muted line-through">{field.old}</span>
      <ArrowRight size={12} className="flex-none text-muted" aria-hidden="true" />
      <span className="truncate font-medium text-primary">{field.new}</span>
    </dd>
  );
}

/** The one line an answered, skipped or expired card shrinks to. */
function Outcome({
  state,
  action,
  title,
  failure,
}: {
  state: Exclude<ApprovalState, 'pending' | 'sending'>;
  action: ApprovalAction;
  title: string;
  failure?: string;
}) {
  const copy = COPY[action];

  const lines: Record<typeof state, { icon: React.ReactNode; text: string; tone: string }> = {
    approved: { icon: <Check size={13} aria-hidden="true" />, text: copy.done, tone: 'text-positive' },
    rejected: { icon: <X size={13} aria-hidden="true" />, text: copy.kept, tone: 'text-secondary' },
    skipped: {
      icon: <X size={13} aria-hidden="true" />,
      text: `Not ${copy.verb}, because you sent a new message.`,
      tone: 'text-muted',
    },
    expired: {
      icon: <Clock size={13} aria-hidden="true" />,
      text: `This request expired. Ask again if you still want it ${copy.verb}.`,
      tone: 'text-muted',
    },
    closed: { icon: <X size={13} aria-hidden="true" />, text: failure ?? 'This request was already answered.', tone: 'text-muted' },
  };

  const line = lines[state];

  return (
    <div className="mt-2 rounded-xl border border-line bg-panel-subtle px-3 py-2 text-[12px]">
      <span className="text-muted">{title} </span>
      <span className={`inline-flex items-center gap-1 ${line.tone}`}>
        {line.icon}
        {line.text}
      </span>
    </div>
  );
}

/** True once the time has passed, and re-renders the card at that moment. */
function useExpired(expiresAt: string): boolean {
  const deadline = new Date(expiresAt).getTime();
  const [expired, setExpired] = useState(() => Date.now() >= deadline);

  useEffect(() => {
    const left = deadline - Date.now();

    if (left <= 0) return;

    const timer = setTimeout(() => setExpired(true), left);

    return () => clearTimeout(timer);
  }, [deadline]);

  return expired;
}

/** "outstanding_amount" becomes "Outstanding amount". */
function fieldLabel(name: string): string {
  const words = name.replaceAll('_', ' ');

  return words.charAt(0).toUpperCase() + words.slice(1);
}
