'use client';

import { ArrowDownLeft } from 'lucide-react';

import { rupees } from '@/lib/format';
import type { PeriodView } from '@/lib/mock/derive';
import type { MonthOption } from '@/components/ui/MonthSelect';
import AnimatedRupees from '@/components/ui/AnimatedRupees';
import Card, { CardHeading } from '@/components/ui/Card';
import ChangeBadge from '@/components/ui/ChangeBadge';
import MonthSelect from '@/components/ui/MonthSelect';

/**
 * What came in this month, and where from.
 *
 * The breakdown is typographic rather than charted, which the doc asks for
 * explicitly. Two or three sources do not need a pie; they need to be legible
 * side by side, each with a coloured rail that ties it to nothing else on the
 * screen — these are sources of income, not a category system shared with the
 * other cards.
 *
 * The period control here duplicates the dashboard header's on purpose: the
 * reference shows it, and a reader looking at one figure should be able to change
 * the month it describes without moving to the header.
 */
export default function IncomeSummaryCard({
  period,
  periods,
  onPeriodChange,
  index = 0,
}: {
  period: PeriodView;
  periods: MonthOption[];
  onPeriodChange: (id: string) => void;
  index?: number;
}) {
  return (
    <Card index={index} label="Income summary" className="flex flex-col p-5">
      <CardHeading
        icon={<ArrowDownLeft size={16} strokeWidth={2.5} />}
        title="Income"
        tint="var(--accent)"
        soft="var(--accent-soft)"
      >
        <MonthSelect options={periods} value={period.id} onChange={onPeriodChange} compact />
      </CardHeading>

      <p className="mt-4 text-[28px] leading-none font-bold tracking-[-0.02em] text-primary sm:text-[32px]">
        <AnimatedRupees value={period.income.total} />
      </p>

      <div className="mt-3">
        <ChangeBadge delta={period.income.delta} />
      </div>

      {/* The rail colour is decorative; the label carries the meaning. */}
      <dl className="mt-5 grid grid-cols-2 gap-x-3 border-t border-line pt-4">
        {period.income.sources.map((source) => (
          <div key={source.label} className="flex gap-2.5">
            <span
              aria-hidden="true"
              className="mt-0.5 w-[3px] flex-none rounded-full"
              style={{
                background: source.accent === 'yellow' ? 'var(--yellow)' : 'var(--accent)',
              }}
            />
            <div className="min-w-0">
              <dt className="truncate text-[12px] text-secondary">{source.label}</dt>
              <dd className="tabular mt-0.5 text-[15px] font-semibold text-primary">
                {rupees(source.amount)}
              </dd>
            </div>
          </div>
        ))}
      </dl>
    </Card>
  );
}
