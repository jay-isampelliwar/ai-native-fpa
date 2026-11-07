'use client';

import { motion } from 'framer-motion';
import type { ComponentType } from 'react';

import { Layers3 } from 'lucide-react';

import type { FactsBlock, StackBlock, UiBlock } from '@/lib/types';
import BarsCard from '@/components/blocks/BarsCard';
import BreakdownCard from '@/components/blocks/BreakdownCard';
import ChangesCard from '@/components/blocks/ChangesCard';
import ChecklistCard from '@/components/blocks/ChecklistCard';
import CompareCard from '@/components/blocks/CompareCard';
import EmptyCard from '@/components/blocks/EmptyCard';
import GaugeCard from '@/components/blocks/GaugeCard';
import GoalProgressCard from '@/components/blocks/GoalProgressCard';
import HeroCard from '@/components/blocks/HeroCard';
import HoldingsCard from '@/components/blocks/HoldingsCard';
import KpisCard from '@/components/blocks/KpisCard';
import QuoteCard from '@/components/blocks/QuoteCard';
import ReceiptCard from '@/components/blocks/ReceiptCard';
import RingCard from '@/components/blocks/RingCard';
import SourcesCard from '@/components/blocks/SourcesCard';
import TableCard from '@/components/blocks/TableCard';
import TimelineCard from '@/components/blocks/TimelineCard';
import { Badge, FactTiles, TileHead } from '@/components/blocks/Tile';

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
/** Blocks drawn straight into the reply with no card around them, such as the row of source tiles. */
const BARE = new Set<UiBlock['type']>(['sources']);

const PARTS: { [Type in Exclude<UiBlock['type'], 'form'>]: ComponentType<{ block: Extract<UiBlock, { type: Type }> }> } = {
  table: TableCard,
  breakdown: BreakdownCard,
  goal_progress: GoalProgressCard,
  facts: FactsCard,
  stack: StackCard,
  sources: SourcesCard,
  quote: QuoteCard,
  holdings: HoldingsCard,
  hero: HeroCard,
  kpis: KpisCard,
  bars: BarsCard,
  ring: RingCard,
  gauge: GaugeCard,
  receipt: ReceiptCard,
  changes: ChangesCard,
  checklist: ChecklistCard,
  compare: CompareCard,
  timeline: TimelineCard,
  empty: EmptyCard,
};

/** One block drawn bare, for use inside a card. */
function Part({ block }: { block: UiBlock }) {
  if (block.type === 'form') return null;

  const Component = PARTS[block.type] as ComponentType<{ block: UiBlock }> | undefined;

  return Component ? <Component block={block} /> : null;
}

/** The tone a card's glow and badge take, read from the block's own numbers; cards without a move stay accent. */
function toneOf(block: UiBlock): string {
  if (block.type === 'quote') {
    return block.items.every((item) => item.direction === 'down') ? 'tone-down' : 'tone-up';
  }

  if (block.type === 'holdings') {
    const overall = block.summary.find((stat) => stat.direction);

    return overall?.direction === 'down' ? 'tone-down' : overall ? 'tone-up' : 'tone-accent';
  }

  if (block.type === 'hero' || block.type === 'gauge') {
    const tone = block.type === 'hero' ? block.tone : block.score >= 70 ? 'up' : block.score >= 40 ? 'warn' : 'down';

    return `tone-${tone ?? 'accent'}`;
  }

  if (block.type === 'receipt') return block.action === 'removed' ? 'tone-down' : 'tone-up';

  if (block.type === 'empty') return 'tone-muted';

  return 'tone-accent';
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
      className={BARE.has(block.type) ? 'my-4' : `tile my-4 p-4 sm:p-5 ${toneOf(block)}`}
    >
      <Part block={block} />
    </motion.div>
  );
}

/** A `facts` block: a few labelled values as fact tiles, such as a fund's category and NAV. */
function FactsCard({ block }: { block: FactsBlock }) {
  return (
    <div>
      {block.title && <TileHead title={block.title} icon={Layers3} />}
      <FactTiles facts={block.facts} columns={block.facts.length <= 3 ? 3 : 4} />
    </div>
  );
}

/** A `stack` block: one titled card holding several parts, each a section split by a hairline. */
function StackCard({ block }: { block: StackBlock }) {
  return (
    <div>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h4 className="text-[15px] font-semibold tracking-[-0.01em] text-primary">{block.title}</h4>
          {block.chips && block.chips.length > 0 && (
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {block.chips.map((chip) => (
                <span key={chip} className="rounded-full border border-line px-2 py-px text-[11.5px] font-medium text-secondary">
                  {chip}
                </span>
              ))}
            </div>
          )}
        </div>
        <Badge icon={Layers3} />
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
