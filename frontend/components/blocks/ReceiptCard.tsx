'use client';

import { CircleCheck, Trash2 } from 'lucide-react';

import type { ReceiptBlock } from '@/lib/types';
import { Badge } from '@/components/blocks/Tile';

/** A `receipt` block: what was just saved or removed, with its key facts. */
export default function ReceiptCard({ block }: { block: ReceiptBlock }) {
  const saved = block.action === 'saved';

  return (
    <div className={saved ? 'tone-up' : 'tone-muted'}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className={`inline-flex items-center gap-1.5 text-[12px] font-semibold uppercase tracking-[0.08em] ${saved ? 'text-positive' : 'text-muted'}`}>
            {saved ? 'Saved' : 'Removed'}
          </div>
          <div className="mt-0.5 text-[12px] text-muted">
            {block.kind}
            {block.record_id != null && ` · id ${block.record_id}`}
          </div>
        </div>
        <Badge icon={saved ? CircleCheck : Trash2} />
      </div>

      <p className={`mt-2 text-[15px] font-semibold ${saved ? 'text-primary' : 'text-secondary line-through decoration-[1.5px]'}`}>{block.name}</p>

      {block.facts.length > 0 && (
        <dl className="mt-2">
          {block.facts.map((fact) => (
            <div key={fact.label} className="flex justify-between gap-3 border-t border-line py-2 text-[13.5px] first:border-t-0">
              <dt className="text-muted">{fact.label}</dt>
              <dd className="min-w-0 truncate text-right font-medium tabular-nums text-primary">{fact.value}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}
