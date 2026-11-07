'use client';

import { useState } from 'react';

import type { RingBlock } from '@/lib/types';
import { Dot, colourAt } from '@/components/blocks/Tile';

const R = 46;
const C = 2 * Math.PI * R;

/** A `ring` block: how a total is split, as a ring with the total in the middle and a legend beside it. */
export default function RingCard({ block }: { block: RingBlock }) {
  const [hover, setHover] = useState<number | null>(null);

  const arcs = block.items.map((item, index) => {
    const before = block.items.slice(0, index).reduce((sum, earlier) => sum + earlier.pct, 0);

    return { ...item, index, length: Math.max(0, (item.pct / 100) * C - 2), offset: (before / 100) * C, colour: colourAt(index) };
  });

  const shown = hover === null ? null : block.items[hover];

  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-[13px] font-semibold text-secondary">{block.title}</span>
        {block.subtitle && <span className="text-[12px] text-muted">{block.subtitle}</span>}
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-5">
        <svg viewBox="0 0 120 120" className="h-[150px] w-[150px] flex-none" role="img" aria-label={`${block.title}: ${block.items.map((item) => `${item.label} ${item.pct}%`).join(', ')}`} onMouseLeave={() => setHover(null)}>
          {arcs.map((arc) => (
            <circle
              key={arc.label}
              r={R}
              cx={60}
              cy={60}
              fill="none"
              stroke={arc.colour}
              strokeWidth={hover === arc.index ? 16 : 14}
              strokeDasharray={`${arc.length} ${C - arc.length}`}
              strokeDashoffset={-arc.offset}
              transform="rotate(-90 60 60)"
              opacity={hover !== null && hover !== arc.index ? 0.45 : 1}
              className="transition-[opacity,stroke-width] duration-150"
              onMouseEnter={() => setHover(arc.index)}
            >
              <title>{`${arc.label} · ${arc.value} · ${arc.pct}%`}</title>
            </circle>
          ))}
          <text x={60} y={57} textAnchor="middle" fontSize={shown ? 12 : 15} fontWeight={650} fill="var(--text-primary)" style={{ letterSpacing: '-0.02em' }}>
            {shown ? shown.value : block.total}
          </text>
          <text x={60} y={72} textAnchor="middle" fontSize={10.5} fill="var(--text-muted)">
            {shown ? `${shown.pct}%` : 'Total'}
          </text>
        </svg>

        <ul className="min-w-[180px] flex-1 space-y-2 text-[13px]">
          {block.items.map((item, index) => (
            <li
              key={item.label}
              className={`flex items-center gap-2 transition-opacity ${hover !== null && hover !== index ? 'opacity-50' : ''}`}
              onMouseEnter={() => setHover(index)}
              onMouseLeave={() => setHover(null)}
            >
              <Dot colour={colourAt(index)} />
              <span className="min-w-0 truncate text-primary">{item.label}</span>
              <span className="ml-auto font-semibold tabular-nums text-primary">{item.value}</span>
              <span className="w-11 text-right tabular-nums text-muted">{item.pct}%</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
