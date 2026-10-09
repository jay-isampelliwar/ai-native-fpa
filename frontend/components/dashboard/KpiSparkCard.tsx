'use client';

import type { ReactNode } from 'react';

import { rupeesShort } from '@/lib/format';
import type { Delta } from '@/lib/mock/derive';
import Card from '@/components/ui/Card';
import ChangeBadge from '@/components/ui/ChangeBadge';
import Sparkline from '@/components/ui/Sparkline';

/**
 * One figure for the selected month with its recent run drawn under it.
 *
 * The reference's top row: an icon in a round chip, the name, the value, its change,
 * and a sparkline. Each card has its own colour, so the four lines can be told apart
 * at a glance, but the colour only ties a card to its own line and means nothing else.
 */
export default function KpiSparkCard({
  icon,
  title,
  value,
  delta,
  trend,
  color,
  index = 0,
}: {
  icon: ReactNode;
  title: string;
  value: number;
  delta: Delta;
  trend: number[];
  color: string;
  index?: number;
}) {
  return (
    <Card index={index} label={title} className="flex flex-col overflow-hidden px-4 pt-4 pb-2">
      <div className="flex items-center gap-2.5">
        <span
          aria-hidden="true"
          className="grid h-8 w-8 flex-none place-items-center rounded-full border border-[var(--pane-border)] bg-panel-subtle"
          style={{ color }}
        >
          {icon}
        </span>
        <h3 className="truncate text-[13px] font-medium text-secondary">{title}</h3>
      </div>

      <div className="mt-3 flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <p className="tabular text-[22px] leading-none font-bold tracking-[-0.02em] text-primary">
          {rupeesShort(value)}
        </p>
        <ChangeBadge delta={delta} size="sm" label="" />
      </div>

      <div className="mt-2">
        <Sparkline values={trend} color={color} height={58} />
      </div>
    </Card>
  );
}
