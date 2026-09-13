'use client';

import { motion, useReducedMotion } from 'framer-motion';
import type { ReactNode } from 'react';

/**
 * The dashboard's one surface, and the one place its entrance is described.
 *
 * Cards enter staggered, so the index matters: it becomes the delay. The doc asks
 * for 35-50ms between cards, 8px of travel and the `[0.22, 1, 0.36, 1]` ease, and
 * putting that here rather than on each card is what stops the seventh card from
 * drifting out of step with the first.
 *
 * A reader who asked for reduced motion gets no travel and no stagger — the cards
 * are simply present, which is the doc's instruction for this case.
 */

export interface CardProps {
  children: ReactNode;
  /** Position in the grid; sets the entrance delay. */
  index?: number;
  className?: string;
  /** Whether the card lifts on hover. Off for cards that are purely informational. */
  interactive?: boolean;
  /** Rendered as a section with this accessible name, so the dashboard has landmarks. */
  label?: string;
}

export default function Card({
  children,
  index = 0,
  className = '',
  interactive = true,
  label,
}: CardProps) {
  const reduced = useReducedMotion();

  return (
    <motion.section
      aria-label={label}
      initial={reduced ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: 0.24,
        delay: reduced ? 0 : index * 0.042,
        ease: [0.22, 1, 0.36, 1],
      }}
      className={`card ${interactive ? 'card-interactive' : ''} ${className}`}
    >
      {children}
    </motion.section>
  );
}

/** A card's title row: an accent-tinted icon, the name, and whatever sits opposite. */
export function CardHeading({
  icon,
  title,
  tint = 'var(--accent)',
  soft = 'var(--accent-soft)',
  children,
}: {
  icon: ReactNode;
  title: string;
  tint?: string;
  soft?: string;
  children?: ReactNode;
}) {
  return (
    <div className="flex items-center gap-2.5">
      <span
        aria-hidden="true"
        className="grid h-8 w-8 flex-none place-items-center rounded-full"
        style={{ background: soft, color: tint }}
      >
        {icon}
      </span>

      <h3 className="text-[14px] font-semibold text-primary">{title}</h3>

      {children && <div className="ml-auto flex items-center gap-1.5">{children}</div>}
    </div>
  );
}
