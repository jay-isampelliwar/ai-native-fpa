import type { GoalProgressBlock } from '@/lib/types';
import { BlockTitle } from '@/components/blocks/TableCard';
import { StatusAlert, StatusOk } from '@/components/icons/FinIcons';

/**
 * A `goal_progress` block: the free money each month, then one row per goal saying in words whether
 * it is on track, with a bar for how much of its monthly need is covered.
 *
 * One card, split by hairlines. The summary figures sit on the card itself, not in tiles, and each
 * goal is a row, not a box, so nothing is more than one box deep. The bar is neutral: it measures
 * coverage. Whether that is good or bad is said once, by the status label beside the name.
 */
export default function GoalProgressCard({ block }: { block: GoalProgressBlock }) {
  const onTrack = block.goals.filter((goal) => goal.on_track).length;

  return (
    <div className="min-w-0">
      <BlockTitle
        title={block.title}
        subtitle={`${onTrack} of ${block.goals.length} on track`}
      />

      <dl className="mt-3 flex flex-wrap gap-x-8 gap-y-3">
        {block.summary.map((item) => (
          <div key={item.label} className="min-w-0">
            <dt className="card-label">{item.label}</dt>
            <dd className="card-value mt-1 text-[22px] leading-none">{item.value}</dd>
          </div>
        ))}
      </dl>

      <ul className="mt-4">
        {block.goals.map((goal) => {
          const covered = Math.max(0, Math.min(100, goal.covered_pct));
          const tone = goal.on_track
            ? { color: 'var(--positive)', label: 'On track', Icon: StatusOk }
            : { color: 'var(--negative)', label: 'Not on track', Icon: StatusAlert };

          return (
            <li key={goal.name} className="border-t border-line py-4 last:pb-0">
              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                <span className="text-[15px] font-semibold tracking-[-0.01em] text-primary">{goal.name}</span>
                <span className="text-[13px] text-muted">by Dec {goal.target_year}</span>

                <span className="fi-host status-tag ml-auto" style={{ color: tone.color }}>
                  <tone.Icon size={15} />
                  {tone.label}
                </span>
              </div>

              <div className="mt-3 flex items-center gap-3">
                <div
                  className="meter flex-1"
                  role="meter"
                  aria-label={`${goal.name}: monthly need covered`}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={Math.round(covered)}
                >
                  <span style={{ width: `${covered}%` }} />
                </div>
                <span className="w-11 flex-none text-right text-[12.5px] tabular-nums text-secondary">
                  {Math.round(covered)}%
                </span>
              </div>

              <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2.5 sm:grid-cols-4">
                <Fact label="Target today" value={goal.target_today} />
                <Fact label="Needs a month" value={goal.monthly_need} />
                <Fact label="Free for it" value={goal.monthly_assigned} />
                <Fact label="Short by" value={goal.shortfall} warn={!goal.on_track} />
              </dl>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function Fact({ label, value, warn = false }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="card-label">{label}</dt>
      <dd
        className="card-value mt-0.5 truncate text-[14.5px] font-medium"
        style={warn ? { color: 'var(--negative)' } : undefined}
      >
        {value}
      </dd>
    </div>
  );
}
