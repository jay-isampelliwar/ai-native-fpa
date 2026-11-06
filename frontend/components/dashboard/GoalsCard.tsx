'use client';

import { motion, useReducedMotion } from 'framer-motion';
import { CircleCheck, GraduationCap, House, Palmtree, TriangleAlert } from 'lucide-react';

import { percent, rupees } from '@/lib/format';
import type { Goal, GoalStatus } from '@/lib/mock/types';
import Card, { CardHeading } from '@/components/ui/Card';

/**
 * The goals worth watching, with how far along each one is.
 *
 * Status is the point of this card, so it is said in words and marked with its own
 * icon rather than left to the colour of a bar. `At risk` and `On track` differ by
 * more than a hue for the same reason every other figure here does.
 *
 * The years remaining are counted from the real current year rather than stored,
 * so a card built in one year does not still claim three years left in the next.
 */

const ICONS = { home: House, graduation: GraduationCap, palm: Palmtree };

const STATUS: Record<GoalStatus, { label: string; fg: string; bg: string; icon: typeof CircleCheck }> = {
  'on-track': {
    label: 'On track',
    fg: 'var(--positive)',
    bg: 'var(--positive-soft)',
    icon: CircleCheck,
  },
  'at-risk': {
    label: 'At risk',
    fg: 'var(--warning)',
    bg: 'var(--warning-soft)',
    icon: TriangleAlert,
  },
  'off-track': {
    label: 'Off track',
    fg: 'var(--negative)',
    bg: 'var(--negative-soft)',
    icon: TriangleAlert,
  },
};

export default function GoalsCard({ goals, index = 0 }: { goals: Goal[]; index?: number }) {
  return (
    <Card index={index} label="Goals" className="flex flex-col p-5">
      <CardHeading
        icon={<CircleCheck size={16} strokeWidth={2.5} />}
        title="Goals"
        tint="var(--accent)"
        soft="var(--accent-soft)"
      >
        <button
          type="button"
          className="rounded-full px-2 py-1 text-[12px] font-medium text-secondary transition hover:text-primary"
        >
          View all
        </button>
      </CardHeading>

      <ul className="mt-4 space-y-4">
        {goals.slice(0, 2).map((goal) => (
          <GoalRow key={goal.id} goal={goal} />
        ))}
      </ul>
    </Card>
  );
}

function GoalRow({ goal }: { goal: Goal }) {
  const reduced = useReducedMotion();

  const Icon = ICONS[goal.icon];
  const status = STATUS[goal.status];
  const StatusIcon = status.icon;

  const progress = Math.min(100, (goal.saved / goal.target) * 100);
  const yearsLeft = Math.max(0, goal.targetYear - new Date().getFullYear());

  return (
    <li>
      <div className="flex items-start gap-2.5">
        <span
          aria-hidden="true"
          className="grid h-8 w-8 flex-none place-items-center rounded-full bg-panel-subtle text-secondary"
        >
          <Icon size={15} strokeWidth={2} />
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <p className="truncate text-[13.5px] font-semibold text-primary">{goal.title}</p>

            <span
              className="ml-auto inline-flex flex-none items-center gap-1 rounded-full px-1.5 py-0.5 text-[11px] font-semibold"
              style={{ color: status.fg, background: status.bg }}
            >
              <StatusIcon size={10} strokeWidth={2.5} aria-hidden="true" />
              {status.label}
            </span>
          </div>

          <p className="tabular mt-0.5 text-[12px] text-secondary">
            {rupees(goal.saved)} of {rupees(goal.target)}
          </p>

          <div className="mt-2 flex items-center gap-2.5">
            <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-track" aria-hidden="true">
              <motion.span
                className="block h-full rounded-full"
                style={{ background: 'var(--meter)' }}
                initial={reduced ? false : { width: 0 }}
                animate={{ width: `${progress}%` }}
                transition={{ duration: 0.68, ease: [0.22, 1, 0.36, 1] }}
              />
            </span>

            <span className="tabular w-9 flex-none text-right text-[12px] font-semibold text-primary">
              {percent(progress)}
            </span>
          </div>

          <p className="mt-1.5 text-[11.5px] text-muted">
            Target {goal.targetYear} · {yearsLeft} {yearsLeft === 1 ? 'year' : 'years'} left
          </p>
        </div>
      </div>
    </li>
  );
}
