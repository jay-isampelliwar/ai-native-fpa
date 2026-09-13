'use client';

import { motion, useReducedMotion } from 'framer-motion';
import { ChartPie } from 'lucide-react';

import { percent, rupees } from '@/lib/format';
import type { AllocationSlice, PeriodView } from '@/lib/mock/derive';
import type { AllocationKey } from '@/lib/mock/types';
import AnimatedRupees from '@/components/ui/AnimatedRupees';
import Card, { CardHeading } from '@/components/ui/Card';
import ChangeBadge from '@/components/ui/ChangeBadge';

/**
 * The portfolio total, and how it is split.
 *
 * The shares come from `sharesOf`, which distributes rounding by largest
 * remainder, so the four percentages add to exactly 100 rather than to 99 or 101.
 * The doc requires that, and on a card where the legend sits directly under the
 * bar a reader can and will add them up.
 *
 * The bar animates as one sequence rather than four. Each segment given its own
 * spring arrives at a different moment and the boundaries visibly jostle; a single
 * shared transition means the whole bar resolves at once, which is what the doc
 * describes and what actually looks like an allocation rather than a race.
 *
 * Colour is assigned by category, not by position, so equity stays green when the
 * order changes. Every segment is also named in its legend row, so the mapping
 * never depends on telling the four hues apart.
 */

const TINTS: Record<AllocationKey, string> = {
  equity: 'var(--accent)',
  debt: 'var(--blue)',
  gold: 'var(--orange)',
  mutualFunds: 'var(--yellow)',
};

export default function InvestmentDetailCard({
  period,
  index = 0,
}: {
  period: PeriodView;
  index?: number;
}) {
  const reduced = useReducedMotion();
  const { allocation } = period.investment;

  return (
    <Card index={index} label="Investment detail" className="flex flex-col p-5">
      <CardHeading
        icon={<ChartPie size={16} strokeWidth={2.5} />}
        title="Investment detail"
        tint="var(--accent)"
        soft="var(--accent-soft)"
      />

      <div className="mt-4 flex flex-wrap items-end gap-x-3 gap-y-2">
        <p className="text-[28px] leading-none font-bold tracking-[-0.02em] text-primary sm:text-[32px]">
          <AnimatedRupees value={period.investment.total} short />
        </p>
        <div className="pb-0.5">
          <ChangeBadge delta={period.investment.delta} size="sm" />
          <span className="ml-1.5 text-[12px] text-secondary">vs previous month</span>
        </div>
      </div>

      <p className="mt-5 text-[12px] font-medium text-secondary">Distribution</p>

      {/* One track, four segments, one transition across all of them. */}
      <div
        className="mt-2 flex h-2.5 w-full gap-1 overflow-hidden rounded-full"
        role="img"
        aria-label={`Allocation: ${allocation
          .map((slice) => `${slice.label} ${slice.share} percent`)
          .join(', ')}`}
      >
        {allocation.map((slice) => (
          <motion.span
            key={slice.key}
            initial={reduced ? false : { flexGrow: 0 }}
            animate={{ flexGrow: slice.share }}
            transition={{ duration: 0.65, ease: [0.22, 1, 0.36, 1] }}
            style={{ background: TINTS[slice.key], flexBasis: 0 }}
            className="h-full rounded-full"
          />
        ))}
      </div>

      <dl className="mt-4 space-y-2.5">
        {allocation.map((slice) => (
          <LegendRow key={slice.key} slice={slice} />
        ))}
      </dl>
    </Card>
  );
}

/** One category: dot, name, rupee value and share — the bar restated as text. */
function LegendRow({ slice }: { slice: AllocationSlice }) {
  return (
    <div className="flex items-center gap-2.5">
      <span
        aria-hidden="true"
        className="h-2 w-2 flex-none rounded-full"
        style={{ background: TINTS[slice.key] }}
      />

      <dt className="min-w-0 flex-1 truncate text-[13px] text-secondary">{slice.label}</dt>

      <dd className="tabular flex items-center gap-3 text-[13px]">
        <span className="font-medium text-primary">{rupees(slice.amount)}</span>
        <span className="w-9 text-right text-secondary">{percent(slice.share)}</span>
      </dd>
    </div>
  );
}
