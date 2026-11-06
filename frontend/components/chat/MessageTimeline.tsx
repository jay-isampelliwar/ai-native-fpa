'use client';

import { AnimatePresence, motion } from 'framer-motion';
import {
  Ban,
  Check,
  ChevronRight,
  CircleCheck,
  CircleX,
  ClipboardList,
  Copy,
  Download,
  Paperclip,
  PenLine,
  RefreshCw,
  Square,
  ThumbsDown,
  ThumbsUp,
} from 'lucide-react';
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
 * While a reply is written, the thinking pill under the chat shows the running tool's orb and label.
 * Once it is done, a quiet "Worked for 6s · 3 steps" line sits above the answer and opens to the
 * list of steps, so what the planner did stays on record without crowding the reply.
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
  /** How long the planner was at work on this answer, in ms, not counting a wait on an approval card. */
  workedMs?: number;
  /** The approval card this reply paused on, and where it has got. */
  approval?: { request: ApprovalRequest; state: ApprovalState; failure?: string; at: number };
  /** Cards and forms the tools gave this reply, keyed by tool call id. */
  blocks?: UiBlockEntry[];
  /** The filled form a user turn was sent from. */
  form?: FormSubmission | null;
}

/** The one ease every chat entrance uses: fast out, soft landing. */
const EASE = [0.22, 1, 0.36, 1] as const;

/** A block that fades up into place when it appears, such as an approval card or an error box. */
const ENTER = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.24, ease: EASE },
};

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
    <div className="mx-auto w-full max-w-[816px] space-y-9 px-4 pt-6 sm:px-6">
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
      transition={{ duration: 0.24, ease: EASE }}
      className="flex justify-end"
    >
      <div className="flex max-w-[80%] flex-col items-end">
        {turn.form ? (
          <p
            className="user-bubble inline-flex items-center gap-2 rounded-xl px-3.5 py-2 text-[14.5px] font-medium"
          >
            <CircleCheck size={14} className="text-accent" aria-hidden="true" />
            Details shared · {FORMS[turn.form.kind]?.title ?? 'Form'}
          </p>
        ) : (
          <p
            className="user-bubble rounded-xl px-4 py-2.5 text-[15.5px] leading-[1.6] whitespace-pre-wrap"
          >
            {turn.text}
          </p>
        )}

        {turn.attached && turn.attached.length > 0 && (
          <p className="mt-1.5 pr-1 text-[12.5px] text-muted">
            <Paperclip size={10} className="mr-1 inline-block align-[-1px]" aria-hidden="true" />
            {turn.attached.join(', ')}
          </p>
        )}
        <time className="tabular mt-1 pr-1 text-[12px] text-muted">{clockTime(turn.at)}</time>
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
      transition={{ duration: 0.24, ease: EASE }}
    >
      <div className="min-w-0">
        {!streaming && turn.tools && turn.tools.length > 0 && (
          <WorkSummary steps={turn.tools} workedMs={turn.workedMs} />
        )}

        {turn.approval && (
          <>
            <ReplyWithCards text={before} blocks={turn.blocks} streaming={false} />

            <motion.div {...ENTER} className="my-3">
              <ApprovalCard
                request={turn.approval.request}
                state={turn.approval.state}
                failure={turn.approval.failure}
                onDecide={onDecide}
              />
            </motion.div>
          </>
        )}

        {turn.failed ? (
          <motion.div
            {...ENTER}
            className="rounded-xl border px-4 py-3"
            style={{ borderColor: 'var(--negative)', background: 'var(--negative-soft)' }}
          >
            <Reply text={after} streaming={streaming} />
          </motion.div>
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

        <time className="tabular mt-1 block text-[12px] text-muted">
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
      className="chip-button mt-3 h-8 gap-2 px-3 text-[13.5px] font-medium text-primary disabled:cursor-default disabled:opacity-60"
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
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3, delay: 0.1, ease: EASE }}
      className="mt-3 -ml-1.5 flex flex-wrap items-center gap-0.5"
    >
      <ActionButton label={copied ? 'Copied' : 'Copy'} onClick={copy}>
        <AnimatePresence mode="wait" initial={false}>
          <motion.span
            key={copied ? 'done' : 'copy'}
            initial={{ opacity: 0, scale: 0.6 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.6 }}
            transition={{ duration: 0.14 }}
            className={copied ? 'text-positive' : undefined}
          >
            {copied ? <Check size={13} aria-hidden="true" /> : <Copy size={13} aria-hidden="true" />}
          </motion.span>
        </AnimatePresence>
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
    </motion.div>
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
      className="icon-ghost h-7 w-7 disabled:cursor-not-allowed disabled:opacity-40"
    >
      {children}
    </button>
  );
}

/** `6s`, `1m 12s`. Under a second still reads as `1s`, so the line never says "0s". */
function duration(ms: number): string {
  const seconds = Math.max(1, Math.round(ms / 1000));

  return seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

const STEP_ICON: Record<ToolStep['status'], React.ReactNode> = {
  ok: <Check size={12} className="text-positive" aria-hidden="true" />,
  running: <Check size={12} className="text-muted" aria-hidden="true" />,
  error: <CircleX size={12} className="text-negative" aria-hidden="true" />,
  stopped: <Square size={10} className="text-muted" aria-hidden="true" />,
  rejected: <Ban size={12} className="text-muted" aria-hidden="true" />,
};

/**
 * The record of what the planner did for one answer: closed, a single muted line; open, the steps
 * in order with how each ended. The time is only known for a reply watched live in this tab, so a
 * reply loaded from history says how many steps it took and leaves the time out.
 */
function WorkSummary({ steps, workedMs }: { steps: ToolStep[]; workedMs?: number }) {
  const [open, setOpen] = useState(false);

  const count = `${steps.length} ${steps.length === 1 ? 'step' : 'steps'}`;
  const title = workedMs ? `Worked for ${duration(workedMs)} · ${count}` : `Used ${count}`;

  return (
    <div className="mb-3">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="group -ml-1.5 inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[13px] text-muted transition-colors hover:bg-[var(--hover-surface)] hover:text-secondary"
      >
        {title}
        <motion.span animate={{ rotate: open ? 90 : 0 }} transition={{ duration: 0.18, ease: EASE }} className="grid">
          <ChevronRight size={13} aria-hidden="true" />
        </motion.span>
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22, ease: EASE }}
            className="overflow-hidden"
          >
            <ol className="mt-1.5 ml-[3px] space-y-1.5 border-l border-line py-0.5 pl-3.5">
              {steps.map((step, index) => (
                <motion.li
                  key={step.id}
                  initial={{ opacity: 0, x: -4 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.2, delay: 0.03 * index, ease: EASE }}
                  className="flex items-center gap-2 text-[13px] text-secondary"
                >
                  <span className="grid h-4 w-4 flex-none place-items-center">{STEP_ICON[step.status]}</span>
                  {step.label}
                </motion.li>
              ))}
            </ol>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
