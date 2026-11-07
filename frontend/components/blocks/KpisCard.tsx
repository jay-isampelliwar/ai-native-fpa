'use client';

import { useState } from 'react';

import type { KpisBlock } from '@/lib/types';
import { Delta, colourAt } from '@/components/blocks/Tile';

const W = 160;
const H = 34;

/** A small filled line of recent values, oldest first, in one series colour, with the last value shown on hover. */
function Sparkline({ values, colour }: { values: number[]; colour: string }) {
  const [hover, setHover] = useState<number | null>(null);

  if (values.length < 2) return null;

  const min = Math.min(...values);
  const max = Math.max(...values);
  const points = values.map((value, index) => [
    (index / (values.length - 1)) * W,
    H - 3 - ((value - min) / (max - min || 1)) * (H - 6),
  ]);
  const line = points.map(([x, y], index) => `${index ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`).join(' ');
  const last = points[points.length - 1];
  const shown = hover ?? values.length - 1;
  const [hx, hy] = points[shown];

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      className="mt-2 h-[34px] w-full"
      role="img"
      aria-label={`Trend over ${values.length} months`}
      onMouseLeave={() => setHover(null)}
      onMouseMove={(event) => {
        const box = event.currentTarget.getBoundingClientRect();
        const index = Math.round(((event.clientX - box.left) / box.width) * (values.length - 1));
        setHover(Math.max(0, Math.min(values.length - 1, index)));
      }}
    >
      <title>{values[shown].toLocaleString('en-IN')}</title>
      <path d={`${line} L${W} ${H} L0 ${H} Z`} fill={colour} opacity={0.12} />
      <path d={line} fill="none" stroke={colour} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
      <circle cx={last[0]} cy={last[1]} r={3} fill={colour} />
      {hover !== null && <circle cx={hx} cy={hy} r={4} fill="var(--panel)" stroke={colour} strokeWidth={2} vectorEffect="non-scaling-stroke" />}
    </svg>
  );
}

/** A `kpis` block: two to four small tiles, each a number with its change and a trend line. */
export default function KpisCard({ block }: { block: KpisBlock }) {
  const across = block.items.length >= 4 ? 'sm:grid-cols-4' : block.items.length === 3 ? 'sm:grid-cols-3' : 'sm:grid-cols-2';

  return (
    <div>
      {(block.title || block.as_of) && (
        <div className="mb-3 flex items-baseline justify-between gap-3">
          {block.title && <span className="text-[13px] font-semibold text-secondary">{block.title}</span>}
          {block.as_of && <span className="text-[12px] text-muted">{block.as_of}</span>}
        </div>
      )}

      <div className={`grid grid-cols-1 gap-2.5 ${across}`}>
        {block.items.map((item, index) => (
          <div key={item.label} className="fact-tile">
            <div className="text-[12px] text-muted">{item.label}</div>
            <div className="mt-1 truncate text-[20px] font-semibold tracking-[-0.02em] tabular-nums text-primary">{item.value}</div>
            {item.change ? (
              <div className="mt-0.5">
                <Delta change={item.change} small />
              </div>
            ) : (
              <div className="mt-0.5 text-[12px] text-muted">no change</div>
            )}
            {item.trend && item.trend.length > 1 && <Sparkline values={item.trend} colour={colourAt(index)} />}
          </div>
        ))}
      </div>
    </div>
  );
}
