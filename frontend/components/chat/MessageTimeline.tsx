'use client';

import { motion } from 'framer-motion';
import { Check, CircleCheck, ClipboardList, Copy, Download, Paperclip, PenLine, RefreshCw, ThumbsDown, ThumbsUp } from 'lucide-react';
import { useState } from 'react';

import { splitCards, withoutCards } from '@/lib/cards';
import { clockTime } from '@/lib/format';
import { FORMS } from '@/lib/forms';
import type {
  ApprovalDecision,
  ApprovalEdits,
  ApprovalRequest,
  ApprovalState,
  FormSubmission,
  ToolStep,
  UiBlockEntry,
} from '@/lib/types';
import BlockView from '@/components/blocks/BlockView';
import ApprovalCard from '@/components/chat/ApprovalCard';
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
 *
 * A reply that paused for approval is split where it paused: the lines written before the pause,
 * then the card, then whatever the planner wrote after the person decided. So the planner first
 * says what it needs checked, and the card sits under those lines.
 *
 * Cards sit inside the reply where its text says `{{card:<id>}}`. A reply that opened a form gets an
 * "Open form" button under it, which turns into "Details shared" once that form is sent. A user turn
 * that was a filled form shows as a small "Details shared" chip, never as the long text the agent read.
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
  /** The approval card this reply paused on, and where it has got. */
  approval?: { request: ApprovalRequest; state: ApprovalState; failure?: string; at: number };
  /** Cards and forms the tools gave this reply, keyed by tool call id. */
  blocks?: UiBlockEntry[];
  /** The filled form a user turn was sent from. */
  form?: FormSubmission | null;
}

export default function MessageTimeline({
  turns,
  streamingId,
  userId,
  busy,
  openFormId,
  onRegenerate,
  onDecide,
  onOpenForm,
}: {
  turns: Turn[];
  streamingId?: string;
  userId: number | null;
  busy: boolean;
  /** The form block now open beside the chat, if any. */
  openFormId?: string | null;
  onRegenerate: (answerId: string) => void;
  onDecide: (answerId: string, decision: ApprovalDecision, edits?: ApprovalEdits) => void;
  onOpenForm: (answerId: string, blockId: string) => void;
}) {
  const sentForms = new Set(turns.map((turn) => turn.form?.block_id).filter((id): id is string => Boolean(id)));

  return (
    <div className="mx-auto w-full max-w-[816px] space-y-8 px-4 pt-4 sm:px-6">
      {turns.map((turn) =>
        turn.role === 'user' ? (
          <UserTurn key={turn.id} turn={turn} />
        ) : (
          (turn.text || turn.approval || turn.blocks?.length) && (
            <PlannerTurn
              key={turn.id}
              turn={turn}
              streaming={turn.id === streamingId}
              userId={userId}
              busy={busy}
              sentForms={sentForms}
              openFormId={openFormId}
              onRegenerate={() => onRegenerate(turn.id)}
              onDecide={(decision, edits) => onDecide(turn.id, decision, edits)}
              onOpenForm={(blockId) => onOpenForm(turn.id, blockId)}
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
      <div className="flex max-w-[78%] flex-col items-end">
        {turn.form ? (
          <p
            className="inline-flex items-center gap-2 rounded-3xl px-5 py-2.5 text-[15px] font-medium text-primary"
            style={{ background: 'var(--gradient-user)' }}
          >
            <CircleCheck size={14} className="text-accent" aria-hidden="true" />
            Details shared · {FORMS[turn.form.kind]?.title ?? 'Form'}
          </p>
        ) : (
          <p
            className="rounded-3xl px-5 py-2.5 text-[16px] leading-[1.6] whitespace-pre-wrap text-primary"
            style={{ background: 'var(--gradient-user)' }}
          >
            {turn.text}
          </p>
        )}

        {turn.attached && turn.attached.length > 0 && (
          <p className="mt-1 pr-1 text-[12.5px] text-muted">
            <Paperclip size={10} className="mr-1 inline-block align-[-1px]" aria-hidden="true" />
            {turn.attached.join(', ')}
          </p>
        )}
        <time className="mt-1 pr-1 text-[12px] text-muted">{clockTime(turn.at)}</time>
      </div>
    </motion.div>
  );
}

function PlannerTurn({
  turn,
  streaming,
  userId,
  busy,
  sentForms,
  openFormId,
  onRegenerate,
  onDecide,
  onOpenForm,
}: {
  turn: Turn;
  streaming: boolean;
  userId: number | null;
  busy: boolean;
  sentForms: Set<string>;
  openFormId?: string | null;
  onRegenerate: () => void;
  onDecide: (decision: ApprovalDecision, edits?: ApprovalEdits) => void;
  onOpenForm: (blockId: string) => void;
}) {
  const forms = (turn.blocks ?? []).filter((entry) => entry.block.type === 'form');

  // Where the reply paused for its card: the text up to there goes above the card, the rest below.
  const cut = turn.approval ? Math.min(turn.approval.at, turn.text.length) : 0;
  const before = turn.text.slice(0, cut);
  const after = turn.text.slice(cut);

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
    >
      <div className="min-w-0">
        {turn.approval && (
          <>
            <ReplyWithCards text={before} blocks={turn.blocks} streaming={false} />

            <div className="my-3">
              <ApprovalCard
                request={turn.approval.request}
                state={turn.approval.state}
                failure={turn.approval.failure}
                onDecide={onDecide}
              />
            </div>
          </>
        )}

        {turn.failed ? (
          <div
            className="rounded-2xl border px-3.5 py-3"
            style={{ borderColor: 'var(--negative)', background: 'var(--negative-soft)' }}
          >
            <Reply text={after} streaming={streaming} />
          </div>
        ) : (
          <ReplyWithCards text={after} blocks={turn.blocks} streaming={streaming} />
        )}

        {forms.map((entry) =>
          entry.block.type === 'form' ? (
            <FormButton
              key={entry.id}
              title={FORMS[entry.block.form]?.title ?? 'Form'}
              sent={sentForms.has(entry.id)}
              open={openFormId === entry.id}
              disabled={busy}
              onOpen={() => onOpenForm(entry.id)}
            />
          ) : null,
        )}

        {/* One card per attached file, drawn under the answer that describes them. They are the
            only way anything read from a document is saved, so they sit with the reply that asked
            for the decision rather than anywhere else on the screen. */}
        {!streaming &&
          typeof userId === 'number' &&
          turn.importIds?.map((importId) => (
            <ImportReview key={importId} userId={userId} importId={importId} />
          ))}

        {!streaming && turn.text && (
          <ReplyActions text={withoutCards(turn.text)} busy={busy} onRegenerate={onRegenerate} />
        )}

        <time className="mt-1.5 pl-1 block text-[12px] text-muted">
          {clockTime(turn.at)}
          {turn.stopped && ' · Response stopped'}
        </time>
      </div>
    </motion.div>
  );
}

/**
 * The reply's markdown with its cards drawn in place. Only the last text part gets the streaming
 * caret, and a card line whose card has not arrived yet draws nothing.
 */
function ReplyWithCards({ text, blocks, streaming }: { text: string; blocks?: UiBlockEntry[]; streaming: boolean }) {
  const segments = splitCards(text);
  const byId = new Map((blocks ?? []).map((entry) => [entry.id, entry.block]));
  const lastText = segments.findLastIndex((segment) => segment.kind === 'text');

  if (segments.length === 0) return streaming ? <Reply text="" streaming /> : null;

  return (
    <>
      {segments.map((segment, index) => {
        if (segment.kind === 'text') {
          return <Reply key={index} text={segment.text} streaming={streaming && index === lastText} />;
        }

        const block = byId.get(segment.id);

        return block ? <BlockView key={index} block={block} /> : null;
      })}
    </>
  );
}

/** The button under a reply that opened a form: open it again, or a quiet note once it was sent. */
function FormButton({
  title,
  sent,
  open,
  disabled,
  onOpen,
}: {
  title: string;
  sent: boolean;
  open: boolean;
  disabled: boolean;
  onOpen: () => void;
}) {
  if (sent) {
    return (
      <p className="mt-2 inline-flex items-center gap-1.5 text-[14px] text-muted">
        <CircleCheck size={13} className="text-accent" aria-hidden="true" />
        {title} details shared
      </p>
    );
  }

  return (
    <button
      type="button"
      onClick={onOpen}
      disabled={disabled || open}
      className="mt-2 inline-flex items-center gap-2 rounded-full border border-[var(--pane-border)] bg-panel-subtle px-3.5 py-1.5 text-[14px] font-medium text-primary transition hover:border-[var(--border-strong)] disabled:cursor-default disabled:opacity-60"
    >
      <ClipboardList size={14} className="text-accent" aria-hidden="true" />
      {open ? `${title} form is open` : `Open ${title.toLowerCase()} form`}
    </button>
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
