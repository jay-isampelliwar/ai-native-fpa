'use client';

import { motion } from 'framer-motion';
import type { ComponentType } from 'react';

import type { FactsBlock, StackBlock, UiBlock } from '@/lib/types';
import BreakdownCard from '@/components/blocks/BreakdownCard';
import GoalProgressCard from '@/components/blocks/GoalProgressCard';
import TableCard, { BlockTitle } from '@/components/blocks/TableCard';

/**
 * The one place a block's `type` key is mapped to the component that draws it.
 *
 * A new card is a new entry here and a new builder in the backend's `app/agent/blocks.py`. A type
 * this map does not know draws nothing, so an older frontend never breaks on a newer backend.
 * `form` is not here: a form opens beside the chat, and its reply gets an "Open form" button.
 *
 * Every card follows one rule: the card is the only box. Parts inside it are split by hairlines and
 * space, so a card never holds a box that holds another box.
 */
const PARTS: { [Type in Exclude<UiBlock['type'], 'form'>]: ComponentType<{ block: Extract<UiBlock, { type: Type }> }> } = {
  table: TableCard,
  breakdown: BreakdownCard,
  goal_progress: GoalProgressCard,
  facts: FactsCard,
  stack: StackCard,
};

/** One block drawn bare, for use inside a card. */
function Part({ block }: { block: UiBlock }) {
  if (block.type === 'form') return null;

  const Component = PARTS[block.type] as ComponentType<{ block: UiBlock }> | undefined;

  return Component ? <Component block={block} /> : null;
}

/** One card in a reply, drawn where the text placed it. */
export default function BlockView({ block }: { block: UiBlock }) {
  // Reduced motion is handled by the chat's MotionConfig, which keeps the fade and drops the travel.
  if (block.type === 'form' || !(block.type in PARTS)) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
      className="card my-4 p-4 sm:p-5"
    >
      <Part block={block} />
    </motion.div>
  );
}

/** A `facts` block: a few labelled values in a grid, such as a fund's category and NAV. */
function FactsCard({ block }: { block: FactsBlock }) {
  return (
    <div>
      {block.title && <BlockTitle title={block.title} />}

      <dl className={`grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4 ${block.title ? 'mt-3' : ''}`}>
        {block.facts.map((fact) => (
          <div key={fact.label} className="min-w-0">
            <dt className="card-label">{fact.label}</dt>
            <dd className="card-value mt-1 truncate text-[15.5px]">{fact.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

/** A `stack` block: one titled card holding several parts, such as a fund's facts, holdings and sectors. */
function StackCard({ block }: { block: StackBlock }) {
  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        <h4 className="text-[15px] font-semibold tracking-[-0.01em] text-primary">{block.title}</h4>
        {block.chips?.map((chip) => (
          <span
            key={chip}
            className="rounded-md border border-line px-1.5 py-px text-[12px] font-medium text-secondary"
          >
            {chip}
          </span>
        ))}
      </div>

      {/* Each part is a section of the one card, split by a hairline rather than a box of its own. */}
      <div className="mt-4 divide-y divide-[var(--border)]">
        {block.blocks.map((part, index) => (
          <div key={index} className="py-4 first:pt-0 last:pb-0">
            <Part block={part} />
          </div>
        ))}
      </div>
    </div>
  );
}
