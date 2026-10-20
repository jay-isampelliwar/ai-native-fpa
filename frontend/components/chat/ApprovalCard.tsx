'use client';

import { Check, Clock, ShieldAlert, Trash2, X } from 'lucide-react';
import { useEffect, useState } from 'react';

import type { ApprovalRequest, ApprovalState } from '@/lib/types';

/**
 * The Approve / Reject card for one risky tool the planner paused on.
 *
 * Nothing changes until the person presses Remove. The card shows the item the backend read
 * before pausing, field by field, so the decision is about the real record and not the model's
 * description of it.
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

  if (shown !== 'pending' && shown !== 'sending') {
    return <Outcome state={shown} title={request.preview.title} failure={failure} />;
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
            <dd className="min-w-0 truncate text-primary tabular-nums">{field.value}</dd>
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
          style={{ background: 'var(--negative)' }}
        >
          <Trash2 size={14} aria-hidden="true" />
          Remove
        </button>

        <button
          type="button"
          disabled={sending}
          onClick={() => onDecide('reject')}
          className="flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-[12.5px] text-secondary transition hover:text-primary disabled:opacity-40"
        >
          <X size={14} aria-hidden="true" />
          Keep it
        </button>

        <span className="ml-auto text-[11px] text-muted">Nothing is removed until you approve</span>
      </div>
    </div>
  );
}

/** The one line an answered, skipped or expired card shrinks to. */
function Outcome({
  state,
  title,
  failure,
}: {
  state: Exclude<ApprovalState, 'pending' | 'sending'>;
  title: string;
  failure?: string;
}) {
  const lines: Record<typeof state, { icon: React.ReactNode; text: string; tone: string }> = {
    approved: { icon: <Check size={13} aria-hidden="true" />, text: 'You approved this.', tone: 'text-positive' },
    rejected: { icon: <X size={13} aria-hidden="true" />, text: 'You chose to keep it.', tone: 'text-secondary' },
    skipped: {
      icon: <X size={13} aria-hidden="true" />,
      text: 'Not removed, because you sent a new message.',
      tone: 'text-muted',
    },
    expired: {
      icon: <Clock size={13} aria-hidden="true" />,
      text: 'This request expired. Ask again if you still want it removed.',
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
