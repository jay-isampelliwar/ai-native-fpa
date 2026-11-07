'use client';

import { CalendarClock } from 'lucide-react';

import type { TimelineBlock } from '@/lib/types';
import { TileHead } from '@/components/blocks/Tile';

const DOT = {
  past: 'bg-positive',
  soon: 'bg-accent',
  far: 'bg-line-strong',
} as const;

/** A `timeline` block: dated money events on one vertical line, soonest first. */
export default function TimelineCard({ block }: { block: TimelineBlock }) {
  return (
    <div className="tone-accent">
      <TileHead title={block.title} icon={CalendarClock} />

      <ol className="relative mt-3 pl-[22px] before:absolute before:bottom-1.5 before:left-[7px] before:top-1.5 before:w-0.5 before:bg-line">
        {block.items.map((item, index) => (
          <li key={`${item.when}-${item.label}-${index}`} className="relative pb-3 pt-1.5 last:pb-0">
            <span
              aria-hidden
              className={`absolute -left-[19px] top-[11px] h-2.5 w-2.5 rounded-full border-2 border-panel shadow-[0_0_0_1px_var(--border)] ${DOT[item.state]}`}
            />
            <div className="text-[11.5px] text-muted">{item.when}</div>
            <div className="flex justify-between gap-3 text-[13.5px] font-medium">
              <span className="min-w-0 truncate text-primary">{item.label}</span>
              {item.value && <span className="flex-none tabular-nums text-secondary">{item.value}</span>}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
