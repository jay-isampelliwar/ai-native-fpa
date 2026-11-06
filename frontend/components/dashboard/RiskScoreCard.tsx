'use client';

import { motion, useReducedMotion } from 'framer-motion';
import { Info, ShieldCheck } from 'lucide-react';
import { useId } from 'react';

import type { RiskSnapshot } from '@/lib/mock/types';
import Card, { CardHeading } from '@/components/ui/Card';

/**
 * The risk gauge: a semicircle from green through to red, with the score on it.
 *
 * Drawn by hand rather than with a chart library. A gauge is one arc, one sweep of
 * colour and one needle; expressing that as a radial bar chart means fighting a
 * component built for something else to get the cap shapes and the zone
 * boundaries right.
 *
 * The arc is a path with a dash applied, which is what makes the fill animate: the
 * dash array is the visible length, and moving it from zero sweeps the colour
 * round. The gradient underneath is static, so the colour at any point on the arc
 * is a property of the position rather than of how far the fill has travelled —
 * which is what makes the zones mean anything.
 *
 * Each metric carries a plain-language explanation. The doc requires every one of
 * them to be explicable without jargon, and `title` plus a screen-reader line
 * covers both pointer and assistive use without building a tooltip system.
 */

/** Half a circle, from the left end round to the right, in a 100x56 box. */
const ARC = 'M 12 52 A 40 40 0 0 1 92 52';
const ARC_LENGTH = Math.PI * 40;

export default function RiskScoreCard({
  risk,
  index = 0,
}: {
  risk: RiskSnapshot;
  index?: number;
}) {
  const reduced = useReducedMotion();
  const gradientId = useId().replace(/:/g, '');

  // The score runs 0-10 and the arc is half a turn.
  const fraction = Math.max(0, Math.min(1, risk.score / 10));

  return (
    <Card index={index} label="Risk score" className="flex flex-col p-5">
      <CardHeading
        icon={<ShieldCheck size={16} strokeWidth={2.5} />}
        title="Risk score"
        tint="var(--accent)"
        soft="var(--accent-soft)"
      />

      <div className="mt-4 flex flex-col items-center gap-4 sm:flex-row sm:items-center sm:gap-5">
        <div className="relative w-[168px] flex-none">
          <svg viewBox="0 0 104 60" className="w-full" role="img" aria-label={`Risk score ${risk.score} out of 10, ${risk.category}`}>
            <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="0">
                <stop offset="0%" stopColor="var(--positive)" />
                <stop offset="50%" stopColor="var(--warning)" />
                <stop offset="100%" stopColor="var(--negative)" />
              </linearGradient>
            </defs>

            {/* The unreached part of the scale. */}
            <path
              d={ARC}
              fill="none"
              stroke="var(--track)"
              strokeWidth={10}
              strokeLinecap="round"
            />

            <motion.path
              d={ARC}
              fill="none"
              stroke={`url(#${gradientId})`}
              strokeWidth={10}
              strokeLinecap="round"
              strokeDasharray={ARC_LENGTH}
              initial={reduced ? false : { strokeDashoffset: ARC_LENGTH }}
              animate={{ strokeDashoffset: ARC_LENGTH * (1 - fraction) }}
              transition={{ duration: 0.85, ease: [0.22, 1, 0.36, 1] }}
            />
          </svg>

          <div className="absolute inset-x-0 bottom-0 text-center">
            <p className="tabular text-[26px] leading-none font-bold text-primary">
              {risk.score.toFixed(1)}
            </p>
            <p className="mt-1 text-[12px] text-secondary">{risk.category}</p>
          </div>
        </div>

        <dl className="w-full space-y-2">
          {risk.metrics.map((metric) => (
            <div key={metric.label} className="flex items-center gap-2">
              <dt className="flex min-w-0 flex-1 items-center gap-1 text-[12.5px] text-secondary">
                <span className="truncate">{metric.label}</span>
                <span
                  tabIndex={0}
                  title={metric.explanation}
                  aria-label={`${metric.label}: ${metric.explanation}`}
                  className="flex-none text-muted transition hover:text-secondary"
                >
                  <Info size={12} aria-hidden="true" />
                </span>
              </dt>

              <dd className="tabular text-[12.5px] font-semibold text-primary">{metric.value}</dd>
            </div>
          ))}
        </dl>
      </div>
    </Card>
  );
}
