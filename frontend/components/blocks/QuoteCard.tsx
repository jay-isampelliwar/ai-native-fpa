'use client';

import { animate, useReducedMotion } from 'framer-motion';
import { ChartNoAxesCombined } from 'lucide-react';
import { useEffect, useState } from 'react';

import type { QuoteBlock } from '@/lib/types';
import { BigNumber, Delta, FactTiles, TileHead } from '@/components/blocks/Tile';

type QuoteItem = QuoteBlock['items'][number];

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

  return <span className={`${className} font-semibold tabular-nums whitespace-nowrap text-primary`}>{reduce ? item.value : text}</span>;
}

/** The time of the quote, with "Closed" beside it when the market is shut. */
function asOf(block: QuoteBlock): string {
  return block.closed ? `${block.as_of} · Closed` : block.as_of;
}

/** A `quote` block: one index with its four stats, or several indices as tiles with only level and change. */
export default function QuoteCard({ block }: { block: QuoteBlock }) {
  const single = block.items.length === 1;

  if (single) {
    const item = block.items[0];

    return (
      <div>
        <TileHead title={item.name} subtitle={asOf(block)} icon={ChartNoAxesCombined} />
        <BigNumber>
          <Level item={item} className="" />
        </BigNumber>
        <Delta change={{ text: `${item.change} (${item.change_pct})`, direction: item.direction }} note="today" />
        {item.stats && <FactTiles facts={item.stats} columns={4} />}
      </div>
    );
  }

  return (
    <div>
      <TileHead title="Indices" subtitle={asOf(block)} icon={ChartNoAxesCombined} />

      <dl className="mt-3.5 grid grid-cols-1 gap-2.5 sm:grid-cols-3">
        {block.items.map((item) => (
          <div key={item.name} className="fact-tile">
            <dt className="text-[11.5px] text-muted">{item.name}</dt>
            <dd className="mt-0.5">
              <Level item={item} className="block text-[20px] leading-tight tracking-[-0.02em]" />
              <Delta change={{ text: `${item.change} (${item.change_pct})`, direction: item.direction }} small />
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
