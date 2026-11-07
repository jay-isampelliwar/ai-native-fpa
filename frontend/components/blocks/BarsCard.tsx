'use client';

import { useState } from 'react';

import type { BarsBlock } from '@/lib/types';
import { Dot, colourAt } from '@/components/blocks/Tile';

const W = 460;
const H = 160;
const LEFT = 40;
const RIGHT = 8;
const TOP = 10;
const BOTTOM = 22;

/** Rupees in short form for an axis: 8k, 1.2L, 1.5Cr. */
function short(value: number): string {
  if (value >= 1e7) return `${(value / 1e7).toFixed(value % 1e7 ? 1 : 0)}Cr`;
  if (value >= 1e5) return `${(value / 1e5).toFixed(value % 1e5 ? 1 : 0)}L`;
  if (value >= 1e3) return `${Math.round(value / 1e3)}k`;
  return `${Math.round(value)}`;
}

const rupees = (value: number) => `₹${Math.round(value).toLocaleString('en-IN')}`;

/** The series colours: income-like first series in blue, spending-like second in yellow, then the rest in order. */
const seriesColour = (index: number) => (index === 0 ? colourAt(0) : index === 1 ? colourAt(1) : colourAt(index));

/** A `bars` block: grouped bars by label, one or two series, in rupees, with a legend and hover values. */
export default function BarsCard({ block }: { block: BarsBlock }) {
  const [hover, setHover] = useState<{ text: string; x: number; y: number } | null>(null);

  const max = Math.max(1, ...block.series.flatMap((series) => series.values));
  const inner = W - LEFT - RIGHT;
  const innerH = H - TOP - BOTTOM;
  const slot = inner / Math.max(1, block.labels.length);
  const count = Math.max(1, block.series.length);
  const gap = 2;
  const barW = Math.max(4, Math.min(14, (slot - 10 - gap * (count - 1)) / count));

  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-[13px] font-semibold text-secondary">{block.title}</span>
        {block.subtitle && <span className="text-[12px] text-muted">{block.subtitle}</span>}
      </div>

      <div className="relative mt-2">
        <svg viewBox={`0 0 ${W} ${H}`} className="block w-full" role="img" aria-label={block.title} onMouseLeave={() => setHover(null)}>
          {[0, 0.5, 1].map((tick) => {
            const y = TOP + innerH - innerH * tick;

            return (
              <g key={tick}>
                <line x1={LEFT} x2={W - RIGHT} y1={y} y2={y} stroke="var(--border)" strokeDasharray="2 3" />
                <text x={LEFT - 6} y={y + 4} textAnchor="end" fontSize={10.5} fill="var(--text-muted)">
                  {short(max * tick)}
                </text>
              </g>
            );
          })}

          {block.labels.map((label, index) => {
            const groupW = barW * count + gap * (count - 1);
            const x0 = LEFT + index * slot + (slot - groupW) / 2;

            return (
              <g key={label}>
                {block.series.map((series, k) => {
                  const value = series.values[index] ?? 0;
                  const height = (value / max) * innerH;
                  const x = x0 + k * (barW + gap);
                  const y = TOP + innerH - height;

                  return (
                    <rect
                      key={series.name}
                      x={x}
                      y={y}
                      width={barW}
                      height={Math.max(0, height)}
                      rx={3}
                      fill={seriesColour(k)}
                      onMouseEnter={() => setHover({ text: `${label} · ${series.name} · ${rupees(value)}`, x: x + barW / 2, y })}
                    >
                      <title>{`${label} · ${series.name} · ${rupees(value)}`}</title>
                    </rect>
                  );
                })}
                <text x={LEFT + index * slot + slot / 2} y={H - 6} textAnchor="middle" fontSize={10.5} fill="var(--text-muted)">
                  {label}
                </text>
              </g>
            );
          })}
        </svg>

        {hover && (
          <div
            className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full whitespace-nowrap rounded-md border border-line bg-panel-elevated px-2 py-1 text-[12px] tabular-nums text-primary shadow-[var(--shadow-card)]"
            style={{ left: `${(hover.x / W) * 100}%`, top: `${(hover.y / H) * 100}%`, marginTop: -6 }}
          >
            {hover.text}
          </div>
        )}
      </div>

      {block.series.length > 1 && (
        <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-[12.5px] text-secondary">
          {block.series.map((series, index) => (
            <span key={series.name} className="inline-flex items-center gap-1.5">
              <Dot colour={seriesColour(index)} />
              {series.name}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
