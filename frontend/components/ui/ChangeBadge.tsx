import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react';

import { signedPercent } from '@/lib/format';
import type { Delta } from '@/lib/mock/derive';

/**
 * A month-over-month change, said three ways at once.
 *
 * The doc forbids communicating meaning through colour alone, so every badge
 * carries an arrow for direction and a sign in the text as well as the tint. A
 * reader who cannot separate the red from the green still sees `↓` and `−4.9%`.
 *
 * Direction and sentiment are deliberately different inputs. An expense rising is
 * an up arrow and a red badge; income rising is an up arrow and a green one. One
 * variable could not express that, which is why `Delta` carries both.
 *
 * The label is part of the badge rather than text beside it, because `+4.6%` with
 * no referent is not a fact. `vs previous month` is what makes it one.
 */
export default function ChangeBadge({
  delta,
  label = 'vs previous month',
  size = 'md',
}: {
  delta: Delta;
  label?: string;
  size?: 'sm' | 'md';
}) {
  const { percent, trend, sentiment } = delta;

  const tone =
    sentiment === 'positive'
      ? { fg: 'var(--positive)', bg: 'var(--positive-soft)' }
      : sentiment === 'negative'
        ? { fg: 'var(--negative)', bg: 'var(--negative-soft)' }
        : { fg: 'var(--text-secondary)', bg: 'var(--panel-subtle)' };

  const Arrow = trend === 'up' ? ArrowUpRight : trend === 'down' ? ArrowDownRight : Minus;

  const compact = size === 'sm';

  // Spoken as one phrase, so a screen reader does not read an arrow and a number
  // as two unrelated facts.
  const spoken = `${trend === 'up' ? 'Up' : trend === 'down' ? 'Down' : 'Unchanged'} ${Math.abs(
    percent,
  ).toFixed(1)} percent ${label}`;

  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className={`inline-flex items-center gap-0.5 rounded-full font-semibold tabular ${
          compact ? 'px-1.5 py-0.5 text-[11px]' : 'px-2 py-1 text-[12px]'
        }`}
        style={{ color: tone.fg, background: tone.bg }}
      >
        <Arrow size={compact ? 11 : 13} strokeWidth={2.5} aria-hidden="true" />
        <span aria-hidden="true">{signedPercent(percent)}</span>
        <span className="sr-only">{spoken}</span>
      </span>

      {label && !compact && <span className="text-[12px] text-secondary">{label}</span>}
    </span>
  );
}
