import { Rows3 } from 'lucide-react';

import type { TableBlock } from '@/lib/types';
import { Badge, TileHead, TileRow } from '@/components/blocks/Tile';

/**
 * A `table` block drawn as list rows, so a generic table from the backend still looks like the
 * other cards. The first column is the row's name, the other left-aligned columns join into the
 * grey sub-line, the last right-aligned column is the value and the one before it the small line
 * under the value.
 */
export default function TableCard({ block }: { block: TableBlock }) {
  const [first, ...others] = block.columns;
  const rights = others.filter((column) => column.align === 'right');
  const lefts = others.filter((column) => column.align !== 'right');
  const value = rights.at(-1);
  const valueSub = rights.length > 1 ? rights.at(-2) : undefined;
  const extraRights = rights.slice(0, Math.max(0, rights.length - 2));
  const subColumns = [...lefts, ...extraRights];

  const cell = (row: Record<string, string>, key?: string) => (key ? row[key] ?? '—' : undefined);

  return (
    <div className="min-w-0">
      {(block.title || block.subtitle) && <TileHead title={block.title ?? ''} subtitle={block.subtitle} icon={Rows3} />}

      <div className={block.title || block.subtitle ? 'mt-2' : ''}>
        {block.rows.map((row, index) => {
          const sub = subColumns
            .map((column) => {
              const text = row[column.key];

              return text ? (column.align === 'right' ? `${column.label} ${text}` : text) : null;
            })
            .filter(Boolean)
            .join(' · ');

          return (
            <TileRow
              key={index}
              lead={<Badge icon={Rows3} small tone="muted" />}
              name={first ? cell(row, first.key) : '—'}
              sub={sub || undefined}
              value={cell(row, value?.key)}
              valueSub={valueSub ? `${valueSub.label} ${cell(row, valueSub.key)}` : undefined}
            />
          );
        })}
      </div>
    </div>
  );
}

/** The title and muted line at the top of a card or a part of one. */
export function BlockTitle({ title, subtitle }: { title?: string | null; subtitle?: string | null }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
      {title && <h4 className="text-[14.5px] font-semibold tracking-[-0.01em] text-primary">{title}</h4>}
      {subtitle && <p className="text-[12.5px] text-muted">{subtitle}</p>}
    </div>
  );
}
