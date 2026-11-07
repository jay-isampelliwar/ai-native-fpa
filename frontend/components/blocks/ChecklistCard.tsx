'use client';

import { Circle, CircleCheck, CircleMinus, ListChecks } from 'lucide-react';

import type { ChecklistBlock } from '@/lib/types';
import { TileHead } from '@/components/blocks/Tile';

const STATUS = {
  done: { icon: CircleCheck, word: 'done', className: 'text-positive' },
  missing: { icon: Circle, word: 'missing', className: 'text-[var(--warning)]' },
  declined: { icon: CircleMinus, word: 'declined', className: 'text-muted' },
} as const;

/** A `checklist` block: which sections the planner knows about, and which are still missing or declined. */
export default function ChecklistCard({ block }: { block: ChecklistBlock }) {
  const done = block.items.filter((item) => item.status === 'done').length;

  return (
    <div className="tone-accent">
      <TileHead title={block.title} subtitle={block.subtitle ?? `${done} of ${block.items.length} done`} icon={ListChecks} />

      <ul className="mt-2">
        {block.items.map((item) => {
          const status = STATUS[item.status];
          const Icon = status.icon;

          return (
            <li key={item.label} className="flex items-center gap-2.5 border-t border-line py-2 text-[13.5px] first:border-t-0">
              <Icon aria-hidden className={`h-4 w-4 flex-none ${status.className}`} strokeWidth={2} />
              <span className="min-w-0 truncate text-primary">{item.label}</span>
              <span className={`ml-auto text-[11.5px] font-semibold uppercase tracking-[0.04em] ${status.className}`}>{status.word}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
