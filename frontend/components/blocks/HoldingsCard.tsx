'use client';

import { ArrowDown, ArrowUp } from 'lucide-react';
import { useState } from 'react';

import type { HoldingsBlock, SummaryStat } from '@/lib/types';

/**
 * Colours for the four biggest holdings, in this fixed order. The order was checked for colour-blind
 * separation in light and dark; green and red stay free for gain and loss. The rest share one grey.
 */
const SLOTS = ['var(--chart-1)', 'var(--chart-4)', 'var(--chart-6)', 'var(--chart-5)'];
const OTHER = 'var(--border-strong)';

const colourAt = (index: number) => SLOTS[index] ?? OTHER;

/** One top-row number; a change is green or red with its note beside it. */
function Stat({ stat }: { stat: SummaryStat }) {
  const tone = stat.direction === 'up' ? 'text-positive' : stat.direction === 'down' ? 'text-negative' : 'text-primary';

  return (
    <div className="min-w-0 border-line pl-4 first:pl-0 [&:not(:first-child)]:border-l">
      <dt className="text-[11.5px] text-muted">{stat.label}</dt>
      <dd className={`mt-1 whitespace-nowrap text-[18px] font-semibold tracking-[-0.02em] tabular-nums ${tone}`}>
        {stat.value}
        {stat.note && <span className="ml-1 text-[12px] font-medium tracking-normal">{stat.note}</span>}
      </dd>
    </div>
  );
}

/** The one split bar: each of the four biggest holdings in its colour, the rest folded into one grey part. */
function SplitBar({ block }: { block: HoldingsBlock }) {
  const [hover, setHover] = useState<string | null>(null);

  const parts = block.items.slice(0, SLOTS.length).map((item, index) => ({
    key: item.name,
    label: `${item.name} · ${item.share.toFixed(2)}%`,
    share: item.share,
    colour: colourAt(index),
  }));

  const rest = block.items.slice(SLOTS.length).reduce((sum, item) => sum + item.share, 0);

  if (rest > 0) parts.push({ key: 'other', label: `Others · ${rest.toFixed(2)}%`, share: rest, colour: OTHER });

  return (
    <div className="mt-5">
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

/** A `holdings` block: total value and gain, one split bar, then each holding with its colour, share and value. */
export default function HoldingsCard({ block }: { block: HoldingsBlock }) {
  const hasToday = block.items.some((item) => item.today);

  return (
    <div>
      <div className="flex items-center justify-between gap-3">
        <span className="text-[12px] font-semibold uppercase tracking-[0.08em] text-muted">{block.title}</span>
        {block.as_of && (
          <span className="inline-flex items-center gap-1.5 text-[12px] text-muted">
            <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-current opacity-60" />
            {block.as_of}
          </span>
        )}
      </div>

      <dl className="mt-3.5 grid grid-cols-2 gap-y-3 sm:grid-cols-3">
        {block.summary.map((stat) => (
          <Stat key={stat.label} stat={stat} />
        ))}
      </dl>

      <SplitBar block={block} />

      <ul className="mt-1">
        {block.items.map((item, index) => {
          const Arrow = item.today?.direction === 'up' ? ArrowUp : ArrowDown;

          return (
            <li
              key={`${item.name}-${index}`}
              className={`grid items-center gap-4 border-t border-line py-2.5 ${
                hasToday ? 'grid-cols-[minmax(0,1fr)_auto_72px]' : 'grid-cols-[minmax(0,1fr)_auto]'
              }`}
            >
              <span className="flex min-w-0 items-center gap-2.5 text-[14px] font-medium text-primary">
                <span aria-hidden className="h-2 w-2 flex-none rounded-[2px]" style={{ background: colourAt(index) }} />
                <span className="truncate">{item.name}</span>
                <span className="flex-none text-[12px] font-normal text-muted tabular-nums">{item.share.toFixed(2)}%</span>
              </span>

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
