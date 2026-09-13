'use client';

import { ArrowUpRight, TriangleAlert } from 'lucide-react';

import type { PeriodView } from '@/lib/mock/derive';
import type { MonthOption } from '@/components/ui/MonthSelect';
import AnimatedRupees from '@/components/ui/AnimatedRupees';
import Card, { CardHeading } from '@/components/ui/Card';
import ChangeBadge from '@/components/ui/ChangeBadge';
import MonthSelect from '@/components/ui/MonthSelect';

/**
 * What went out this month.
 *
 * Deliberately the plainest card on the dashboard. The reference image shows
 * category bars beneath it and the doc excludes them in as many words — no
 * segmented bars, no progress bars, no legend. Spending breakdown is a screen of
 * its own, and putting a miniature of it here would compete with the cash-flow
 * card for the same glance.
 *
 * A rise is shown as a negative condition, which `Delta` already encodes: the
 * badge turns red while its arrow still points up. The warning line beneath
 * appears only when the rise outpaces income, because that is the case where the
 * number means something a reader should act on rather than merely note.
 */
export default function ExpenseSummaryCard({
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
  const outpacingIncome =
    period.expense.delta.trend === 'up' &&
    period.expense.delta.percent > period.income.delta.percent;

  return (
    <Card index={index} label="Expense summary" className="flex flex-col p-5">
      <CardHeading
        icon={<ArrowUpRight size={16} strokeWidth={2.5} />}
        title="Expense"
        tint="var(--negative)"
        soft="var(--negative-soft)"
      >
        <MonthSelect options={periods} value={period.id} onChange={onPeriodChange} compact />
      </CardHeading>

      <p className="mt-4 text-[28px] leading-none font-bold tracking-[-0.02em] text-primary sm:text-[32px]">
        <AnimatedRupees value={period.expense.total} />
      </p>

      <div className="mt-3">
        <ChangeBadge delta={period.expense.delta} />
      </div>

      <div className="mt-auto pt-5">
        {outpacingIncome ? (
          <p
            className="flex items-start gap-2 rounded-xl px-3 py-2.5 text-[12px] leading-[1.45]"
            style={{ background: 'var(--warning-soft)', color: 'var(--warning)' }}
          >
            <TriangleAlert size={14} className="mt-px flex-none" aria-hidden="true" />
            <span>Spending is rising faster than income this month.</span>
          </p>
        ) : (
          <p className="text-[12px] leading-[1.45] text-secondary">
            Spending is growing more slowly than income.
          </p>
        )}
      </div>
    </Card>
  );
}
