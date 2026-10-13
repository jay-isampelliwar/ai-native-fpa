'use client';

import { motion } from 'framer-motion';
import { Check, Copy, Download, Paperclip, PenLine, RefreshCw, ThumbsDown, ThumbsUp } from 'lucide-react';
import { useState } from 'react';

import { clockTime } from '@/lib/format';
import type { ToolStep } from '@/lib/types';
import ImportReview from '@/components/chat/ImportReview';
import Reply from '@/components/chat/Reply';

/**
 * The conversation so far.
 *
 * The two roles get genuinely different surfaces rather than the same bubble in two
 * colours: the reader's own words sit in a tinted card on the right, the planner's
 * answer as plain text across the column, with no box and no mark. That difference
 * is what lets someone find their own question again while scrolling. A failed
 * answer is the one exception: it keeps a red box so the error stands out.
 *
 * Timestamps are muted and small. They are needed to place a turn in a session and
 * never needed at a glance, so they sit under the message rather than in it.
 *
 * The turns sit in one centred column, at most 1024px wide, the same width as the composer. On a
 * wide screen a line of text that runs the full width is hard to read, and the
 * empty space on both sides keeps the eye on the conversation.
 *
 * Each finished answer gets a row of round buttons, as in the reference. Copy and
 * Regenerate work. Like, Dislike, Edit and Download are drawn but do nothing yet —
 * the backend has no feedback table and no export route for them to call.
 *
 * Tools are not listed in the timeline. While a reply is written, the thinking pill under the
 * chat shows the running tool's orb and label instead.
 */

export interface Turn {
  id: string;
  role: 'user' | 'planner';
  text: string;
  at: Date;
  /** Set when the turn failed, so it can be styled as a problem rather than an answer. */
  failed?: boolean;
  /** Set when the person stopped the reply, so the partial text is shown as cut short. */
  stopped?: boolean;
  /** Filenames sent with a user turn, so the question keeps a record of what went with it. */
  attached?: string[];
  /** Imports this answer is about. The review cards for them are drawn under it. */
  importIds?: string[];
  /** Tools the planner called for this answer, in the order they started. Read by the thinking pill. */
  tools?: ToolStep[];
}

export default function MessageTimeline({
  turns,
  streamingId,
  userId,
  busy,
  onRegenerate,
}: {
  turns: Turn[];
  streamingId?: string;
  userId: number | null;
  busy: boolean;
  onRegenerate: (answerId: string) => void;
}) {
  return (
    <div className="mx-auto w-full max-w-5xl space-y-5 px-4 pt-1 sm:px-6">
      {turns.map((turn) =>
        turn.role === 'user' ? (
          <UserTurn key={turn.id} turn={turn} />
        ) : (
          turn.text && (
            <PlannerTurn
              key={turn.id}
              turn={turn}
              streaming={turn.id === streamingId}
              userId={userId}
              busy={busy}
              onRegenerate={() => onRegenerate(turn.id)}
            />
          )
        ),
      )}
    </div>
  );
}

function UserTurn({ turn }: { turn: Turn }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
      className="flex justify-end"
    >
      <div className="flex max-w-[88%] flex-col items-end">
        <p
          className="rounded-2xl rounded-br-md border border-[var(--pane-border)] px-3.5 py-2.5 text-[13.5px] leading-[1.55] whitespace-pre-wrap text-primary"
          style={{ background: 'var(--gradient-user)' }}
        >
          {turn.text}
        </p>

        {turn.attached && turn.attached.length > 0 && (
          <p className="mt-1 pr-1 text-[11px] text-muted">
            <Paperclip size={10} className="mr-1 inline-block align-[-1px]" aria-hidden="true" />
            {turn.attached.join(', ')}
          </p>
        )}
        <time className="mt-1 pr-1 text-[10.5px] text-muted">{clockTime(turn.at)}</time>
      </div>
    </motion.div>
  );
}

function PlannerTurn({
  turn,
  streaming,
  userId,
  busy,
  onRegenerate,
}: {
  turn: Turn;
  streaming: boolean;
  userId: number | null;
  busy: boolean;
  onRegenerate: () => void;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
    >
      <div className="min-w-0">
        {turn.failed ? (
          <div
            className="rounded-2xl border px-3.5 py-3"
            style={{ borderColor: 'var(--negative)', background: 'var(--negative-soft)' }}
          >
            <Reply text={turn.text} streaming={streaming} />
          </div>
        ) : (
          <Reply text={turn.text} streaming={streaming} />
        )}

        {/* One card per attached file, drawn under the answer that describes them. They are the
            only way anything read from a document is saved, so they sit with the reply that asked
            for the decision rather than anywhere else on the screen. */}
        {!streaming &&
          typeof userId === 'number' &&
          turn.importIds?.map((importId) => (
            <ImportReview key={importId} userId={userId} importId={importId} />
          ))}

        {!streaming && (
          <ReplyActions text={turn.text} busy={busy} onRegenerate={onRegenerate} />
        )}

        <time className="mt-1.5 pl-1 block text-[10.5px] text-muted">
          {clockTime(turn.at)}
          {turn.stopped && ' · Response stopped'}
        </time>
      </div>
    </motion.div>
  );
}

/** The round buttons under a finished answer. */
function ReplyActions({
  text,
  busy,
  onRegenerate,
}: {
  text: string;
  busy: boolean;
  onRegenerate: () => void;
}) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard access can be refused by the browser. Nothing useful to show.
    }
  }

  return (
    <div className="mt-2 flex flex-wrap items-center gap-1.5">
      <ActionButton label={copied ? 'Copied' : 'Copy'} onClick={copy}>
        {copied ? <Check size={13} aria-hidden="true" /> : <Copy size={13} aria-hidden="true" />}
      </ActionButton>
      <ActionButton label="Good response">
        <ThumbsUp size={13} aria-hidden="true" />
      </ActionButton>
      <ActionButton label="Bad response">
        <ThumbsDown size={13} aria-hidden="true" />
      </ActionButton>
      <ActionButton label="Edit">
        <PenLine size={13} aria-hidden="true" />
      </ActionButton>
      <ActionButton label="Download">
        <Download size={13} aria-hidden="true" />
      </ActionButton>
      <ActionButton label="Regenerate" onClick={onRegenerate} disabled={busy}>
        <RefreshCw size={13} aria-hidden="true" />
      </ActionButton>
    </div>
  );
}

function ActionButton({
  label,
  onClick,
  disabled = false,
  children,
}: {
  label: string;
  onClick?: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      disabled={disabled}
      className="icon-pill h-7 w-7 disabled:cursor-not-allowed disabled:opacity-40"
    >
      {children}
    </button>
  );
}
