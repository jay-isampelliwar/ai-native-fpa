'use client';

import { ArrowDown, ArrowUp, Wallet } from 'lucide-react';
import { useState } from 'react';

import type { HoldingsBlock } from '@/lib/types';
import { BigNumber, Delta, Dot, TileHead, colourAt } from '@/components/blocks/Tile';

/** The split bar: the four biggest holdings in their colours, the rest folded into one grey part. */
function SplitBar({ block }: { block: HoldingsBlock }) {
  const [hover, setHover] = useState<string | null>(null);
  const slots = 4;

  const parts = block.items.slice(0, slots).map((item, index) => ({
    key: item.name,
    label: `${item.name} · ${item.share.toFixed(2)}%`,
    share: item.share,
    colour: colourAt(index),
  }));

  const rest = block.items.slice(slots).reduce((sum, item) => sum + item.share, 0);

  if (rest > 0) parts.push({ key: 'other', label: `Others · ${rest.toFixed(2)}%`, share: rest, colour: colourAt(slots) });

  return (
    <div className="mt-4">
      <div className="flex h-2 gap-[2px]" role="img" aria-label={parts.map((part) => part.label).join(', ')}>
        {parts.map((part) => (
          <span
            key={part.key}
            onMouseEnter={() => setHover(part.label)}
            onMouseLeave={() => setHover(null)}
            className={`h-full min-w-1 transition-opacity first:rounded-l-full last:rounded-r-full ${
              hover && hover !== part.label ? 'opacity-40' : ''
            }`}
            style={{ flexGrow: part.share, background: part.colour }}
          />
        ))}
      </div>
      <p className={`mt-1.5 h-4 text-[12px] text-muted tabular-nums transition-opacity ${hover ? 'opacity-100' : 'opacity-0'}`}>
        {hover}
      </p>
    </div>
  );
}

/** A `holdings` block: total value and overall gain, one split bar, then each holding with its colour, share and value. */
export default function HoldingsCard({ block }: { block: HoldingsBlock }) {
  const value = block.summary.find((stat) => stat.label === 'Value');
  const overall = block.summary.find((stat) => stat.direction);
  const hasToday = block.items.some((item) => item.today);

  return (
    <div>
      <TileHead title={block.title} subtitle={block.as_of ? `Prices as of ${block.as_of}` : null} icon={Wallet} />

      {value && <BigNumber>{value.value}</BigNumber>}

      {overall && (
        <Delta
          change={{ text: overall.note ? `${overall.value} (${overall.note.replace(/^[+−-]/, '')})` : overall.value, direction: overall.direction ?? 'up' }}
          note={overall.label.toLowerCase()}
        />
      )}

      <SplitBar block={block} />

      <ul className="-mt-1">
        {block.items.map((item, index) => {
          const Arrow = item.today?.direction === 'up' ? ArrowUp : ArrowDown;

          return (
            <li
              key={`${item.name}-${index}`}
              className={`grid items-center gap-3 border-t border-line py-2.5 ${
                hasToday ? 'grid-cols-[auto_minmax(0,1fr)_auto_64px]' : 'grid-cols-[auto_minmax(0,1fr)_auto]'
              }`}
            >
              <Dot colour={colourAt(index)} />

              <div className="min-w-0">
                <div className="truncate text-[14px] font-medium text-primary">{item.name}</div>
                <div className="text-[12px] text-muted tabular-nums">{item.share.toFixed(2)}% of total</div>
              </div>

              <span className="text-[14px] font-semibold tabular-nums text-primary">{item.value}</span>

              {hasToday && (
                <span
                  className={`inline-flex items-center justify-end gap-0.5 text-[12.5px] font-semibold tabular-nums ${
                    item.today?.direction === 'up' ? 'text-positive' : 'text-negative'
                  }`}
                >
                  {item.today ? (
                    <>
                      <Arrow aria-hidden className="h-3.5 w-3.5" strokeWidth={2.25} />
                      {item.today.text}
                      <span className="sr-only">{item.today.direction}</span>
                    </>
                  ) : (
                    <span className="text-muted">—</span>
                  )}
                </span>
              )}
            </li>
          );
        })}
      </ul>

      {block.subtitle && <p className="mt-2 text-[12px] text-muted">{block.subtitle}</p>}
    </div>
  );
}
