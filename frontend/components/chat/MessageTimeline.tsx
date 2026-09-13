'use client';

import { motion } from 'framer-motion';

import { clockTime } from '@/lib/format';
import { PROFILE } from '@/lib/mock/data';
import Reply from '@/components/chat/Reply';

/**
 * The conversation so far.
 *
 * The two roles get genuinely different surfaces rather than the same bubble in two
 * colours: the reader's own words sit in a tinted card on the right, the planner's
 * answer in a panel on the left with its mark beside it. At this pane's width that
 * difference is what lets someone find their own question again while scrolling.
 *
 * The planner's bubble is wide — 92% rather than the usual two-thirds — because its
 * answers are financial explanations with lists in them, and a narrow column turns
 * a four-item list into twelve lines.
 *
 * Timestamps are muted and small. They are needed to place a turn in a session and
 * never needed at a glance, so they sit under the message rather than in it.
 */

export interface Turn {
  id: string;
  role: 'user' | 'planner';
  text: string;
  at: Date;
  /** Set when the turn failed, so it can be styled as a problem rather than an answer. */
  failed?: boolean;
}

export default function MessageTimeline({
  turns,
  streamingId,
}: {
  turns: Turn[];
  streamingId?: string;
}) {
  return (
    <div className="space-y-4 px-4 sm:px-5">
      {turns.map((turn) =>
        turn.role === 'user' ? (
          <UserTurn key={turn.id} turn={turn} />
        ) : (
          turn.text && (
            <PlannerTurn key={turn.id} turn={turn} streaming={turn.id === streamingId} />
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
      className="flex justify-end gap-2.5"
    >
      <div className="flex max-w-[88%] flex-col items-end">
        <p className="rounded-2xl rounded-br-md border border-line bg-panel-subtle px-3.5 py-2.5 text-[13.5px] leading-[1.55] whitespace-pre-wrap text-primary">
          {turn.text}
        </p>
        <time className="mt-1 pr-1 text-[10.5px] text-muted">{clockTime(turn.at)}</time>
      </div>

      <span
        aria-hidden="true"
        className="mt-0.5 grid h-7 w-7 flex-none place-items-center rounded-full text-[10px] font-bold"
        style={{ background: 'var(--accent-soft)', color: 'var(--accent)' }}
      >
        {PROFILE.initials}
      </span>
    </motion.div>
  );
}

function PlannerTurn({ turn, streaming }: { turn: Turn; streaming: boolean }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
      className="flex gap-2.5"
    >
      <span
        aria-hidden="true"
        className="mt-0.5 grid h-7 w-7 flex-none place-items-center rounded-full"
        style={{ background: 'var(--accent-soft)' }}
      >
        <svg viewBox="0 0 20 20" className="h-3.5 w-3.5" fill="none">
          <rect x="2" y="11" width="6" height="7" rx="2" fill="var(--accent)" opacity="0.55" />
          <rect x="2" y="2" width="6" height="7" rx="2" fill="var(--accent)" opacity="0.3" />
          <rect x="12" y="11" width="6" height="7" rx="2" fill="var(--accent)" opacity="0.3" />
          <rect x="12" y="2" width="6" height="7" rx="2" fill="var(--accent)" />
        </svg>
      </span>

      <div className="min-w-0 max-w-[92%]">
        <div
          className="rounded-2xl rounded-tl-md border px-3.5 py-3"
          style={
            turn.failed
              ? { borderColor: 'var(--negative)', background: 'var(--negative-soft)' }
              : { borderColor: 'var(--border)', background: 'var(--panel)' }
          }
        >
          <Reply text={turn.text} streaming={streaming} />
        </div>

        <time className="mt-1 pl-1 block text-[10.5px] text-muted">{clockTime(turn.at)}</time>
      </div>
    </motion.div>
  );
}
