'use client';

import { motion, useReducedMotion } from 'framer-motion';
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
  const reduced = useReducedMotion();

  if (block.type === 'form' || !(block.type in PARTS)) return null;

  return (
    <motion.div
      initial={reduced ? false : { opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
      className="card my-3 p-4"
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

      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {block.facts.map((fact) => (
          <div key={fact.label} className="min-w-0 rounded-xl bg-panel-subtle px-3 py-2">
            <dt className="text-[12.5px] text-muted">{fact.label}</dt>
            <dd className="truncate text-[15px] font-semibold tabular-nums text-primary">{fact.value}</dd>
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
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h4 className="text-[14px] font-semibold text-primary">{block.title}</h4>
        {block.chips?.map((chip) => (
          <span key={chip} className="rounded-full bg-panel-subtle px-2 py-0.5 text-[12.5px] text-secondary">
            {chip}
          </span>
        ))}
      </div>

      <div className="space-y-4">
        {block.blocks.map((part, index) => (
          <Part key={index} block={part} />
        ))}
      </div>
    </div>
  );
}
