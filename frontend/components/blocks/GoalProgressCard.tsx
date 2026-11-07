import { Target } from 'lucide-react';

import type { GoalProgressBlock } from '@/lib/types';
import { FactTiles, TileHead } from '@/components/blocks/Tile';

/** A ring filled to `pct`, in the goal's tone, with the number inside. */
function Ring({ pct, colour }: { pct: number; colour: string }) {
  const filled = Math.max(0, Math.min(100, Math.round(pct)));

  return (
    <span
      role="meter"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={filled}
      className="grid h-14 w-14 flex-none place-items-center rounded-full"
      style={{ background: `conic-gradient(${colour} ${filled}%, var(--track) 0)` }}
    >
      <span className="grid h-[42px] w-[42px] place-items-center rounded-full bg-panel text-[12px] font-semibold tabular-nums text-primary">
        {filled}%
      </span>
    </span>
  );
}

/**
 * A `goal_progress` block: the free money each month, then one row per goal with a ring for how
 * much of its monthly need is covered, and whether it is on track in the goal's tone.
 */
export default function GoalProgressCard({ block }: { block: GoalProgressBlock }) {
  const onTrack = block.goals.filter((goal) => goal.on_track).length;

  return (
    <div className="min-w-0">
      <TileHead title={block.title} subtitle={`${onTrack} of ${block.goals.length} on track`} icon={Target} />

      {block.summary.length > 0 && <FactTiles facts={block.summary} columns={block.summary.length > 2 ? 3 : 2} />}

      <ul className="mt-2">
        {block.goals.map((goal) => {
          const colour = goal.on_track ? 'var(--positive)' : goal.covered_pct >= 50 ? 'var(--warning)' : 'var(--negative)';
          const status = goal.on_track ? 'On track' : `Short ${goal.shortfall}`;

          return (
            <li key={goal.name} className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 border-t border-line py-3 first:border-t-0">
              <Ring pct={goal.covered_pct} colour={colour} />

              <div className="min-w-0">
                <div className="truncate text-[14px] font-medium text-primary">{goal.name}</div>
                <div className="truncate text-[12px] text-muted">
                  {goal.target_year} · needs {goal.monthly_need}/mo · {goal.monthly_assigned} free for it
                </div>
              </div>

              <span className="text-right text-[12.5px] font-semibold" style={{ color: colour }}>
                {status}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
