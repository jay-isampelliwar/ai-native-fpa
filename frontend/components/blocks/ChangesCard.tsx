'use client';

import { ArrowRight, PencilLine } from 'lucide-react';

import type { ChangesBlock } from '@/lib/types';
import { TileHead } from '@/components/blocks/Tile';

/** A `changes` block: the fields an update changed, old struck through beside new in bold. */
export default function ChangesCard({ block }: { block: ChangesBlock }) {
  return (
    <div className="tone-accent">
      <TileHead title={block.title} subtitle={`${block.fields.length} ${block.fields.length === 1 ? 'field' : 'fields'} changed`} icon={PencilLine} />

      <dl className="mt-3 grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-x-3 gap-y-1 text-[13.5px]">
        {block.fields.map((field) => (
          <div key={field.label} className="contents">
            <dt className="col-span-3 mt-2 text-[11.5px] text-muted first:mt-0">{field.label}</dt>
            <dd className="min-w-0 truncate text-right tabular-nums text-muted line-through decoration-[1.5px]">{field.old}</dd>
            <dd className="text-muted">
              <ArrowRight aria-hidden className="h-3.5 w-3.5" strokeWidth={2} />
              <span className="sr-only">changed to</span>
            </dd>
            <dd className="min-w-0 truncate font-semibold tabular-nums text-primary">{field.new}</dd>
          </div>
        ))}
      </dl>

      {block.note && <p className="mt-3 text-[12.5px] text-muted">{block.note}</p>}
    </div>
  );
}
