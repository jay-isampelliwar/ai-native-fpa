import { CircleCheck, TriangleAlert } from 'lucide-react';

import type { GoalProgressBlock } from '@/lib/types';
import { BlockTitle } from '@/components/blocks/TableCard';

/**
 * A `goal_progress` block: the free money each month, then one row per goal saying in words whether
 * it is on track, with a bar for how much of its monthly need is covered.
 */
export default function GoalProgressCard({ block }: { block: GoalProgressBlock }) {
  return (
    <div className="min-w-0">
      <BlockTitle title={block.title} />

      <dl className="mb-3 grid grid-cols-2 gap-2">
        {block.summary.map((item) => (
          <div key={item.label} className="rounded-xl bg-panel-subtle px-3 py-2">
            <dt className="text-[12.5px] text-muted">{item.label}</dt>
            <dd className="text-[15px] font-semibold tabular-nums text-primary">{item.value}</dd>
          </div>
        ))}
      </dl>

      <ul className="space-y-3">
        {block.goals.map((goal) => {
          const tone = goal.on_track
            ? { fg: 'var(--positive)', bg: 'var(--positive-soft)', label: 'On track', Icon: CircleCheck }
            : { fg: 'var(--negative)', bg: 'var(--negative-soft)', label: 'Not on track', Icon: TriangleAlert };

          return (
            <li key={goal.name} className="rounded-xl border border-[var(--pane-border)] px-3 py-2.5">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[15px] font-semibold text-primary">{goal.name}</span>
                <span className="text-[13px] text-muted">by Dec {goal.target_year}</span>
                <span
                  className="ml-auto inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[12.5px] font-medium"
                  style={{ color: tone.fg, background: tone.bg }}
                >
                  <tone.Icon size={12} aria-hidden="true" />
                  {tone.label}
                </span>
              </div>

              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-[var(--track)]">
                <div
                  className="h-full rounded-full"
                  style={{ width: `${Math.max(0, Math.min(100, goal.covered_pct))}%`, background: tone.fg }}
                />
              </div>

              <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-[13.5px] sm:grid-cols-4">
                <Fact label="Target today" value={goal.target_today} />
                <Fact label="Needs a month" value={goal.monthly_need} />
                <Fact label="Free for it" value={goal.monthly_assigned} />
                <Fact label="Short by" value={goal.shortfall} />
              </dl>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-muted">{label}</dt>
      <dd className="font-medium tabular-nums text-primary">{value}</dd>
    </div>
  );
}
