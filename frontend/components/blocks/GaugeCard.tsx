'use client';

import { HeartPulse } from 'lucide-react';

import type { GaugeBlock } from '@/lib/types';
import { TileHead } from '@/components/blocks/Tile';

const R = 54;
const HALF = Math.PI * R;

const TONE_VAR = { up: 'var(--positive)', down: 'var(--negative)', warn: 'var(--warning)' } as const;

/** The gauge colour: teal for a good score, amber for a fair one, rose for a poor one. */
function scoreTone(score: number): 'up' | 'warn' | 'down' {
  if (score >= 75) return 'up';
  if (score >= 50) return 'warn';
  return 'down';
}

/** A `gauge` block: a score out of 100 on a half ring, a verdict word, and the checks behind it. */
export default function GaugeCard({ block }: { block: GaugeBlock }) {
  const score = Math.max(0, Math.min(100, block.score));
  const tone = scoreTone(score);

  return (
    <div className={`tone-${tone}`}>
      <TileHead title={block.title} subtitle={block.as_of} icon={HeartPulse} />

      <div className="mt-1 flex flex-wrap items-center gap-4">
        <svg viewBox="0 0 140 84" className="w-[190px] flex-none" role="img" aria-label={`${block.title}: ${score} out of 100, ${block.verdict}`}>
          <path d="M16 76 A54 54 0 0 1 124 76" fill="none" stroke="var(--track)" strokeWidth={12} strokeLinecap="round" />
          <path
            d="M16 76 A54 54 0 0 1 124 76"
            fill="none"
            stroke={TONE_VAR[tone]}
            strokeWidth={12}
            strokeLinecap="round"
            strokeDasharray={`${(HALF * score) / 100} ${HALF}`}
            className="motion-safe:transition-[stroke-dasharray] motion-safe:duration-700"
          />
          <text x={70} y={62} textAnchor="middle" fontSize={26} fontWeight={650} fill="var(--text-primary)" style={{ letterSpacing: '-0.03em' }}>
            {score}
          </text>
          <text x={70} y={78} textAnchor="middle" fontSize={10.5} fill="var(--text-muted)">
            {block.verdict} · out of 100
          </text>
        </svg>

        <ul className="min-w-[160px] flex-1 space-y-2 text-[13px]">
          {block.checks.map((check) => (
            <li key={check.label} className="flex items-center gap-2">
              <span aria-hidden className="h-2.5 w-2.5 flex-none rounded-full" style={{ background: TONE_VAR[check.tone] }} />
              <span className="min-w-0 truncate text-primary">{check.label}</span>
              <span className="ml-auto font-semibold tabular-nums text-primary">{check.value}</span>
              <span className="sr-only">{check.tone === 'up' ? 'good' : check.tone === 'warn' ? 'needs attention' : 'poor'}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
