'use client';

import { animate, useReducedMotion } from 'framer-motion';
import { ArrowDown, ArrowUp } from 'lucide-react';
import { useEffect, useState } from 'react';

import type { QuoteBlock } from '@/lib/types';

type QuoteItem = QuoteBlock['items'][number];

/** Left hairline and padding per stat: two per row on a phone, four in a row from `sm` up. */
const STAT_EDGES = [
  '',
  'border-l border-line pl-3.5',
  'sm:border-l sm:border-line sm:pl-3.5',
  'border-l border-line pl-3.5',
];

const LEVEL = new Intl.NumberFormat('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** The level, counting up from just below its value when the card first appears, or shown as is for reduced motion. */
function Level({ item, className }: { item: QuoteItem; className: string }) {
  const reduce = useReducedMotion();
  const [text, setText] = useState(item.value);

  useEffect(() => {
    if (reduce) return;

    const controls = animate(item.number * 0.985, item.number, {
      duration: 0.7,
      ease: [0.22, 1, 0.36, 1],
      onUpdate: (latest) => setText(LEVEL.format(latest)),
      onComplete: () => setText(item.value),
    });

    return () => controls.stop();
  }, [item.number, item.value, reduce]);

  return <div className={`${className} font-semibold tabular-nums whitespace-nowrap text-primary`}>{reduce ? item.value : text}</div>;
}

/** The change as a pill tinted green or red, with an arrow and a sign so it never relies on colour alone. */
function Change({ item, small }: { item: QuoteItem; small?: boolean }) {
  const up = item.direction === 'up';
  const Arrow = up ? ArrowUp : ArrowDown;

  return (
    <span
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full py-1 pl-1.5 pr-2.5 font-semibold tabular-nums ${
        up ? 'bg-positive-soft text-positive' : 'bg-negative-soft text-negative'
      } ${small ? 'mt-2 text-[12px]' : 'mt-2.5 text-[13px]'}`}
    >
      <Arrow aria-hidden className="h-3.5 w-3.5" strokeWidth={2.25} />
      {item.change} ({item.change_pct})
      <span className="sr-only">{up ? 'up' : 'down'}</span>
    </span>
  );
}

/** The time of the quote, with "Closed" beside it when the market is shut. */
function AsOf({ block }: { block: QuoteBlock }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[12px] text-muted">
      <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-current opacity-60" />
      {block.as_of}
      {block.closed && <span className="font-medium text-secondary">· Closed</span>}
    </span>
  );
}

/** A `quote` block: one index with its four stats, or several indices side by side with only level and change. */
export default function QuoteCard({ block }: { block: QuoteBlock }) {
  const single = block.items.length === 1;
  const down = single ? block.items[0].direction === 'down' : block.items.every((item) => item.direction === 'down');
  const glow = down ? 'var(--negative)' : 'var(--positive)';

  return (
    <div className="relative -m-4 overflow-hidden rounded-[var(--radius-card)] p-4 sm:-m-5 sm:p-5">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{ background: `radial-gradient(120% 90% at 100% 0%, color-mix(in srgb, ${glow} 13%, transparent) 0%, transparent 55%)` }}
      />

      <div className="relative">
        <div className="flex items-center justify-between gap-3">
          <span className="text-[12px] font-semibold uppercase tracking-[0.08em] text-muted">
            {single ? block.items[0].name : 'Indices'}
          </span>
          <AsOf block={block} />
        </div>

        {single ? (
          <SingleQuote item={block.items[0]} />
        ) : (
          <div className="mt-3.5 grid grid-cols-1 gap-5 sm:grid-cols-3">
            {block.items.map((item) => (
              <div key={item.name} className="min-w-0">
                <div className="text-[12px] font-semibold uppercase tracking-[0.08em] text-muted">{item.name}</div>
                <Level item={item} className="mt-2 text-[24px] leading-none tracking-[-0.03em]" />
                <Change item={item} small />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/** One index: big level, change pill, and open, high, low and previous close split by hairlines. */
function SingleQuote({ item }: { item: QuoteItem }) {
  return (
    <>
      <Level item={item} className="mt-2.5 text-[36px] leading-[1.05] tracking-[-0.035em]" />
      <Change item={item} />

      {item.stats && (
        <dl className="mt-5 grid grid-cols-2 gap-y-3.5 sm:grid-cols-4">
          {item.stats.map((stat, index) => (
            <div key={stat.label} className={`min-w-0 pr-3.5 ${STAT_EDGES[index] ?? ''}`}>
              <dt className="text-[11.5px] text-muted">{stat.label}</dt>
              <dd className="mt-1 text-[14px] font-medium tabular-nums text-primary">{stat.value}</dd>
            </div>
          ))}
        </dl>
      )}
    </>
  );
}
