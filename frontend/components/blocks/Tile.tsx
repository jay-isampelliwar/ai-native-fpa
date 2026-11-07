'use client';

import { ArrowDown, ArrowUp } from 'lucide-react';
import type { ComponentType, ReactNode } from 'react';

import type { Change, Direction } from '@/lib/types';

/**
 * The parts every chat card is built from, so all cards share one look: a tone that sets the
 * glow and badge colour, an icon badge, a head line, fact tiles and rows split by hairlines.
 *
 * A card picks its tone with the `tone-*` classes from globals.css (`tone-up`, `tone-down`,
 * `tone-warn`, `tone-accent`, `tone-muted`); every part below reads `--tone` from it.
 */

export type Tone = 'up' | 'down' | 'warn' | 'accent' | 'muted';

export type Icon = ComponentType<{ className?: string; strokeWidth?: number; 'aria-hidden'?: boolean }>;

export const toneClass = (tone: Tone | null | undefined) => `tone-${tone ?? 'accent'}`;

export const directionTone = (direction: Direction | null | undefined): Tone =>
  direction === 'up' ? 'up' : direction === 'down' ? 'down' : 'accent';

/** The icon chip in a card's corner or a row's left edge, tinted by the card's tone. */
export function Badge({ icon: IconPart, small, tone }: { icon: Icon; small?: boolean; tone?: Tone }) {
  return (
    <span className={`badge ${small ? 'badge-sm' : ''} ${tone ? toneClass(tone) : ''}`}>
      <IconPart aria-hidden className={small ? 'h-[13px] w-[13px]' : 'h-4 w-4'} strokeWidth={2} />
    </span>
  );
}

/** A card's first line: the title and a grey sub-line on the left, the badge on the right. */
export function TileHead({
  title,
  subtitle,
  icon,
  right,
}: {
  title: string;
  subtitle?: string | null;
  icon?: Icon;
  right?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0">
        <div className="text-[13px] font-semibold text-secondary">{title}</div>
        {subtitle && <div className="mt-0.5 text-[12px] text-muted">{subtitle}</div>}
      </div>
      {right ?? (icon && <Badge icon={icon} />)}
    </div>
  );
}

/** The big number a card leads with. */
export function BigNumber({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className={`mt-2.5 text-[32px] font-semibold leading-[1.05] tracking-[-0.035em] tabular-nums text-primary ${className}`}>
      {children}
    </div>
  );
}

/** A change line under a number, with an arrow, in profit or loss colour, and a grey note after it. */
export function Delta({ change, note, small }: { change: Change; note?: string | null; small?: boolean }) {
  const Arrow = change.direction === 'up' ? ArrowUp : ArrowDown;

  return (
    <span
      className={`inline-flex items-center gap-1 font-semibold tabular-nums ${small ? 'text-[12px]' : 'mt-2 text-[13px]'} ${
        change.direction === 'up' ? 'text-positive' : 'text-negative'
      }`}
    >
      <Arrow aria-hidden className={small ? 'h-3 w-3' : 'h-3.5 w-3.5'} strokeWidth={2.25} />
      {change.text}
      <span className="sr-only">{change.direction}</span>
      {note && <span className="font-medium text-muted">{note}</span>}
    </span>
  );
}

/** Small labelled values in a grid of tiles, two across on a phone and `columns` across from `sm` up. */
export function FactTiles({
  facts,
  columns = 4,
}: {
  facts: { label: string; value: ReactNode }[];
  columns?: 2 | 3 | 4;
}) {
  const across = { 2: 'sm:grid-cols-2', 3: 'sm:grid-cols-3', 4: 'sm:grid-cols-4' }[columns];

  return (
    <dl className={`mt-3.5 grid grid-cols-2 gap-2.5 ${across}`}>
      {facts.map((fact) => (
        <div key={fact.label} className="fact-tile">
          <dt className="text-[11.5px] text-muted">{fact.label}</dt>
          <dd className="mt-0.5 truncate text-[15px] font-semibold tabular-nums text-primary">{fact.value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** One row in a card: something on the left, a name with a grey sub-line, and a value on the right. */
export function TileRow({
  lead,
  name,
  sub,
  value,
  valueSub,
  below,
}: {
  lead?: ReactNode;
  name: ReactNode;
  sub?: ReactNode;
  value?: ReactNode;
  valueSub?: ReactNode;
  below?: ReactNode;
}) {
  return (
    <div className={`grid items-center gap-3 border-t border-line py-2.5 first:border-t-0 ${lead ? 'grid-cols-[auto_minmax(0,1fr)_auto]' : 'grid-cols-[minmax(0,1fr)_auto]'}`}>
      {lead}
      <div className="min-w-0">
        <div className="truncate text-[14px] font-medium text-primary">{name}</div>
        {sub && <div className="mt-px truncate text-[12px] text-muted">{sub}</div>}
        {below}
      </div>
      {(value || valueSub) && (
        <div className="text-right tabular-nums">
          {value && <div className="text-[14px] font-semibold text-primary">{value}</div>}
          {valueSub && <div className="text-[11.5px] text-muted">{valueSub}</div>}
        </div>
      )}
    </div>
  );
}

/** A thin bar showing a share, 0 to 100, in the given colour. */
export function ShareBar({ pct, colour }: { pct: number; colour: string }) {
  return (
    <div className="mt-1.5 h-[5px] overflow-hidden rounded-full bg-track">
      <span className="block h-full rounded-full" style={{ width: `${Math.max(0, Math.min(100, pct))}%`, background: colour }} />
    </div>
  );
}

/** A square colour dot for legends and rows. */
export function Dot({ colour }: { colour: string }) {
  return <span aria-hidden className="inline-block h-2.5 w-2.5 flex-none rounded-[3px]" style={{ background: colour }} />;
}

/** The chart colours in their fixed order; a series keeps its slot. Extras share the grey. */
export const SERIES = ['var(--chart-1)', 'var(--chart-4)', 'var(--chart-6)', 'var(--chart-5)', 'var(--chart-3)'];

export const colourAt = (index: number) => SERIES[index] ?? 'var(--border-strong)';
