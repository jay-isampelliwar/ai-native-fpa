'use client';

import { CalendarDays } from 'lucide-react';

import { rupeesShort, signedPercent } from '@/lib/format';
import type { CashFlowPoint, PeriodView } from '@/lib/mock/derive';
import Card from '@/components/ui/Card';
import Sparkline from '@/components/ui/Sparkline';

/**
 * One month's cash flow as a small side card: the month, the figure, its change,
 * and a short wave with that month marked on it.
 *
 * The reference stacks three of these beside its big chart, one per recent day. Here
 * they are the selected month and the two before it, so the stack reads top to bottom
 * as "now, last month, the month before".
 */
export default function MonthPulseCard({
  period,
  series,
  color,
  index = 0,
}: {
  period: PeriodView;
  series: CashFlowPoint[];
  color: string;
  index?: number;
}) {
  // A five-month window around this month, so the mark sits inside the wave.
  const at = Math.max(0, series.findIndex((point) => point.periodId === period.id));
  const start = Math.max(0, Math.min(at - 2, series.length - 5));
  const window = series.slice(start, start + 5);

  const { percent, sentiment } = period.cashFlow.delta;
  const tone =
    sentiment === 'positive' ? 'var(--positive)' : sentiment === 'negative' ? 'var(--negative)' : 'var(--text-secondary)';

  return (
    <Card index={index} label={`Cash flow ${period.label}`} className="flex flex-col px-4 pt-3.5 pb-2">
      <div className="flex items-center gap-2">
        <span
          aria-hidden="true"
          className="grid h-7 w-7 flex-none place-items-center rounded-full border border-[var(--pane-border)] bg-panel-subtle text-secondary"
        >
          <CalendarDays size={13} />
        </span>
        <span className="text-[12.5px] font-medium text-primary">{period.label}</span>

        <span
          className="tabular ml-auto rounded-full border border-[var(--pane-border)] px-2 py-0.5 text-[11px] font-semibold"
          style={{ color: tone }}
        >
          {signedPercent(percent)}
        </span>
      </div>

      <div className="mt-2.5 flex items-center gap-2">
        <div className="min-w-0">
          <p className="tabular text-[19px] leading-none font-bold text-primary">
            {rupeesShort(period.cashFlow.total)}
          </p>
          <p className="mt-1 text-[11.5px] text-secondary">Cash flow</p>
        </div>

        <div className="min-w-0 flex-1">
          <Sparkline
            values={window.map((point) => point.value)}
            color={color}
            height={52}
            bars={false}
            mark={at - start}
          />
        </div>
      </div>
    </Card>
  );
}
