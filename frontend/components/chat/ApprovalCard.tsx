'use client';

import { ArrowRight, Check, Clock, ShieldAlert, Trash2, X } from 'lucide-react';
import { useEffect, useState } from 'react';

import type { ApprovalAction, ApprovalField, ApprovalRequest, ApprovalState } from '@/lib/types';

/** The words and colours for each kind of approval, so a change never reads like a delete. */
const COPY: Record<
  ApprovalAction,
  { approve: string; keep: string; note: string; tone: string; done: string; kept: string; verb: string }
> = {
  remove: {
    approve: 'Remove',
    keep: 'Keep it',
    note: 'Nothing is removed until you approve',
    tone: 'var(--negative)',
    done: 'You approved this.',
    kept: 'You chose to keep it.',
    verb: 'removed',
  },
  change: {
    approve: 'Save change',
    keep: 'Keep as is',
    note: 'Nothing changes until you approve',
    tone: 'var(--accent)',
    done: 'You approved this change.',
    kept: 'You kept it as is.',
    verb: 'changed',
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
 * Nothing changes until the person approves. The card shows the item the backend read before
 * pausing, field by field, so the decision is about the real record and not the model's
 * description of it. A change shows each field's saved value and its new one.
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
  onDecide: (decision: 'approve' | 'reject') => void;
}) {
  const expired = useExpired(request.expires_at);
  const shown = state === 'pending' && expired ? 'expired' : state;
  const action = request.preview.action ?? 'remove';
  const copy = COPY[action];

  if (shown !== 'pending' && shown !== 'sending') {
    return <Outcome state={shown} action={action} title={request.preview.title} failure={failure} />;
  }

  const sending = shown === 'sending';

  return (
    <div className="mt-2 overflow-hidden rounded-xl border border-line bg-panel">
      <div className="flex items-center gap-2 border-b border-line px-3 py-2.5">
        <ShieldAlert size={15} className="flex-none text-warning" aria-hidden="true" />
        <span className="text-[12.5px] font-medium text-primary">{request.preview.title}</span>
      </div>

      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 px-3 py-2.5 text-[12px]">
        {request.preview.fields.map((field) => (
          <div key={field.name} className="contents">
            <dt className="text-muted">{fieldLabel(field.name)}</dt>
            <FieldValue field={field} />
          </div>
        ))}
      </dl>

      {failure && <p className="px-3 pb-1 text-[11.5px] text-negative">{failure}</p>}

      <div className="flex flex-wrap items-center gap-2 border-t border-line px-3 py-2.5">
        <button
          type="button"
          disabled={sending}
          onClick={() => onDecide('approve')}
          className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12.5px] font-medium text-white transition disabled:cursor-not-allowed disabled:opacity-40"
          style={{ background: copy.tone }}
        >
          {action === 'remove' ? <Trash2 size={14} aria-hidden="true" /> : <Check size={14} aria-hidden="true" />}
          {copy.approve}
        </button>

        <button
          type="button"
          disabled={sending}
          onClick={() => onDecide('reject')}
          className="flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-[12.5px] text-secondary transition hover:text-primary disabled:opacity-40"
        >
          <X size={14} aria-hidden="true" />
          {copy.keep}
        </button>

        <span className="ml-auto text-[11px] text-muted">{copy.note}</span>
      </div>
    </div>
  );
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
