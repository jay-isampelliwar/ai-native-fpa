'use client';

import { useState } from 'react';

import { INK, SERIES, STATUS } from '@/lib/chart';
import { toNumber } from '@/lib/format';
import type {
  ApprovalCardBlock,
  Block,
  CalloutBlock,
  ChartBlock,
  ChartPoint,
  KpiBlock,
  TableBlock,
  TextBlock,
} from '@/lib/types';

/**
 * The small set of marks an answer is built from.
 *
 * Deliberately few, and closed. The backend describes what should be shown as typed blocks and this
 * file is the whole vocabulary that can render them — a model never emits markup, so nothing appears
 * on screen that a skill did not construct from computed figures.
 *
 * Every block carries the record ids behind it and every one of them offers to show them. That is the
 * point of the backend's provenance design: a reader who disputes a number can see the exact rows it
 * came from, not a prettier restatement of them.
 *
 * Nothing here formats currency. The backend's `display` string is what is shown, because formatting
 * rupees in two codebases guarantees they eventually disagree and the one on screen will be wrong.
 * Raw `value` is parsed only for geometry — a bar width, an arc length — where a float is harmless.
 */

// ---------------------------------------------------------------- provenance
function Evidence({ ids }: { ids: string[] }) {
  const [open, setOpen] = useState(false);

  if (ids.length === 0) return null;

  return (
    <div className="mt-3">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="text-[11.5px] text-[#8ba09c] transition hover:text-[#18312f]"
      >
        {open ? 'Hide' : 'Show'} the {ids.length} record{ids.length === 1 ? '' : 's'} behind this
      </button>

      {open && (
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {ids.map((id) => (
            <li
              key={id}
              className="rounded-md border border-[#18312f]/10 bg-[#f5f2e8]/70 px-1.5 py-0.5 font-mono text-[10.5px] text-[#5d7470]"
            >
              {id}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- containers
export function Card({
  title,
  subtitle,
  note,
  right,
  children,
}: {
  title?: string;
  subtitle?: string;
  note?: string;
  right?: React.ReactNode;
  children?: React.ReactNode;
}) {
  return (
    <section className="overflow-hidden rounded-2xl border border-[#18312f]/9 bg-white/80 shadow-[0_1px_3px_rgba(16,59,54,0.04)] backdrop-blur">
      {(title || right) && (
        <header className="flex items-start justify-between gap-4 px-5 pt-4">
          <div className="min-w-0">
            {title && (
              <h3 className="text-[15px] font-semibold tracking-[-0.01em] text-[#18312f]">{title}</h3>
            )}
            {subtitle && <p className="mt-1 text-[13px] leading-5 text-[#4d6560]">{subtitle}</p>}
          </div>
          {right}
        </header>
      )}

      {children && <div className={`px-5 pb-4 ${title || right ? 'pt-4' : 'pt-4'}`}>{children}</div>}

      {note && (
        <p className="border-t border-[#18312f]/7 bg-[#f5f2e8]/60 px-5 py-2.5 text-[12px] leading-[1.55] text-[#5d7470]">
          {note}
        </p>
      )}
    </section>
  );
}

const TONE_INK: Record<KpiBlock['tone'], string> = {
  neutral: INK.primary,
  positive: STATUS.good,
  negative: STATUS.critical,
};

// ---------------------------------------------------------------- marks
export function Kpi({ block }: { block: KpiBlock }) {
  return (
    <div className="rounded-2xl border border-[#18312f]/9 bg-white/80 px-4 py-3.5">
      <div className="text-[10.5px] uppercase leading-4 tracking-[0.07em] text-[#8ba09c]">
        {block.label}
      </div>

      <div
        className="mt-1 text-[19px] font-semibold tabular-nums tracking-[-0.02em]"
        style={{ color: TONE_INK[block.tone] }}
      >
        {block.display}
      </div>

      {block.caption && <div className="mt-0.5 text-[11px] leading-4 text-[#8ba09c]">{block.caption}</div>}

      <Evidence ids={block.evidence_ids} />
    </div>
  );
}

export function Table({ block }: { block: TableBlock }) {
  return (
    <Card title={block.title ?? undefined}>
      {/* The pane scrolls, not the page: a holdings table can be eleven columns, and a document that
          shifts sideways as a whole is one where the reader loses which row they were on. */}
      <div className="no-scrollbar -mx-5 overflow-x-auto px-5">
        <table className="w-full min-w-[22rem] border-collapse">
          <thead>
            <tr className="border-b border-[#18312f]/9">
              {block.columns.map((column) => (
                <th
                  key={column.key}
                  scope="col"
                  className={`pb-2 text-[10.5px] uppercase leading-4 tracking-[0.07em] text-[#8ba09c] ${
                    column.align === 'right' ? 'text-right' : 'text-left'
                  }`}
                >
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>

          <tbody>
            {block.rows.map((row, index) => (
              <tr key={index} className="border-b border-[#18312f]/6 last:border-0">
                {block.columns.map((column) => (
                  <td
                    key={column.key}
                    className={`py-2 text-[12.5px] ${
                      column.align === 'right'
                        ? 'tabular-nums text-right font-medium text-[#4d6560]'
                        : 'text-left text-[#18312f]'
                    }`}
                  >
                    {row[column.key] ?? ''}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Evidence ids={block.evidence_ids} />
    </Card>
  );
}

const ARC_COLORS = [SERIES.existing, SERIES.additional, '#4f8f79', '#bf8410', '#8ba09c'];

const magnitude = (point: ChartPoint) => Math.max(toNumber(point.value), 0);

function Bars({ points }: { points: ChartPoint[] }) {
  const ceiling = Math.max(...points.map(magnitude), 1);

  return (
    <ul className="space-y-2.5">
      {points.map((point, index) => (
        <li key={`${point.label}-${index}`}>
          <div className="flex items-baseline justify-between gap-3">
            <span className="truncate text-[12.5px] text-[#18312f]">{point.label}</span>
            <span className="shrink-0 text-[12.5px] font-medium tabular-nums text-[#4d6560]">
              {point.display ?? point.value}
            </span>
          </div>

          <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-[#18312f]/7">
            <div
              className="h-full rounded-full"
              style={{
                width: `${(magnitude(point) / ceiling) * 100}%`,
                background: ARC_COLORS[index % ARC_COLORS.length],
              }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}

/**
 * A ring, always followed by its values as text.
 *
 * An arc on its own cannot be read precisely, cannot be read at all by a screen reader, and a
 * financial figure available only as an angle is not really available. Negative values draw at zero
 * length rather than as reversed geometry — a deficit would otherwise run the wrong way round the
 * ring — and the sign travels in the label, which is where a reader looks for it anyway.
 */
function Donut({ points }: { points: ChartPoint[] }) {
  const total = points.reduce((sum, point) => sum + magnitude(point), 0);
  const radius = 52;
  const circumference = 2 * Math.PI * radius;

  let consumed = 0;

  return (
    <div className="flex flex-wrap items-center gap-6">
      <svg viewBox="0 0 140 140" className="h-[124px] w-[124px] shrink-0" aria-hidden="true">
        <circle cx="70" cy="70" r={radius} fill="none" stroke="rgba(24,49,47,0.07)" strokeWidth="15" />

        {total > 0 &&
          points.map((point, index) => {
            const share = magnitude(point) / total;
            const dash = share * circumference;
            const offset = consumed * circumference;

            consumed += share;

            return (
              <circle
                key={`${point.label}-${index}`}
                cx="70"
                cy="70"
                r={radius}
                fill="none"
                stroke={ARC_COLORS[index % ARC_COLORS.length]}
                strokeWidth="15"
                strokeDasharray={`${dash} ${circumference - dash}`}
                strokeDashoffset={-offset}
                transform="rotate(-90 70 70)"
              />
            );
          })}
      </svg>

      <ul className="min-w-[11rem] flex-1 space-y-1.5">
        {points.map((point, index) => (
          <li key={`${point.label}-${index}`} className="flex items-baseline justify-between gap-3">
            <span className="flex items-center gap-2 truncate text-[12.5px] text-[#18312f]">
              <span
                aria-hidden="true"
                className="h-2 w-2 shrink-0 rounded-full"
                style={{ background: ARC_COLORS[index % ARC_COLORS.length] }}
              />
              {point.label}
            </span>

            <span className="shrink-0 text-[12.5px] font-medium tabular-nums text-[#4d6560]">
              {point.display ?? point.value}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Chart({ block }: { block: ChartBlock }) {
  return (
    <Card title={block.title ?? undefined}>
      {block.chart === 'donut' ? <Donut points={block.points} /> : <Bars points={block.points} />}
      <Evidence ids={block.evidence_ids} />
    </Card>
  );
}

/**
 * A caveat shown beside the figure it qualifies rather than buried in a field nobody opens.
 *
 * The calculators attach these deliberately — a deficit, holdings valued at cost, returns that do not
 * beat inflation — and each changes how the number above it should be read. A warning is distinct but
 * not alarming: these appear routinely on healthy portfolios, and an interface that shouts every time
 * makes a reader stop looking.
 */
export function Callout({ block }: { block: CalloutBlock }) {
  const warning = block.level === 'warning';

  return (
    <div
      className={`rounded-xl border px-3.5 py-2.5 ${
        warning
          ? 'border-[#bf8410]/28 bg-[#bf8410]/8 text-[#8a5a12]'
          : 'border-[#18312f]/10 bg-[#f5f2e8]/70 text-[#5d7470]'
      }`}
    >
      <p className="text-[12.5px] leading-5">{block.text}</p>
      <Evidence ids={block.evidence_ids} />
    </div>
  );
}

/**
 * The card a person approves, showing exactly what changes before anything does.
 *
 * The only block that acts. Before and after are rendered as literal values side by side rather than
 * summarised in a sentence, because someone approving a change to their own money should see the two
 * numbers rather than a description of them.
 *
 * Rejecting carries equal weight. The safe answer to a change you do not understand is no, and an
 * interface where yes is the only obvious action is nudging.
 */
export function ApprovalCard({
  block,
  onDecide,
}: {
  block: ApprovalCardBlock;
  onDecide?: (decision: 'approve' | 'reject') => Promise<void>;
}) {
  const [pending, setPending] = useState<'approve' | 'reject' | null>(null);
  const [settled, setSettled] = useState(false);

  async function decide(decision: 'approve' | 'reject') {
    if (!onDecide || pending || settled) return;

    setPending(decision);

    try {
      await onDecide(decision);
      setSettled(true);
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="rounded-2xl border border-[#e7a14d]/40 bg-[#e7a14d]/8 px-5 py-4">
      <p className="text-[13.5px] font-semibold leading-5 text-[#18312f]">{block.title}</p>

      <dl className="mt-3 space-y-2">
        {block.changes.map((change) => (
          <div
            key={change.label}
            className="flex flex-wrap items-baseline justify-between gap-2 border-b border-[#18312f]/8 pb-2 last:border-0 last:pb-0"
          >
            <dt className="text-[12.5px] text-[#4d6560]">{change.label}</dt>

            <dd className="flex items-center gap-2 text-[13px] tabular-nums">
              {change.before && (
                <>
                  <span className="text-[#8ba09c] line-through">{change.before}</span>
                  <span aria-hidden="true" className="text-[#8ba09c]">
                    →
                  </span>
                </>
              )}
              <span className="font-semibold text-[#18312f]">{change.after}</span>
            </dd>
          </div>
        ))}
      </dl>

      {onDecide && !settled && (
        <div className="mt-4 flex gap-2">
          <button
            type="button"
            onClick={() => decide('approve')}
            disabled={pending !== null}
            className="rounded-full bg-[#183f3a] px-4 py-2 text-[12.5px] font-semibold text-white transition hover:bg-[#0d322e] disabled:opacity-50"
          >
            {pending === 'approve' ? 'Applying…' : 'Approve'}
          </button>

          <button
            type="button"
            onClick={() => decide('reject')}
            disabled={pending !== null}
            className="rounded-full border border-[#18312f]/15 bg-white px-4 py-2 text-[12.5px] font-medium text-[#4d6560] transition hover:bg-white/70 disabled:opacity-50"
          >
            {pending === 'reject' ? 'Rejecting…' : 'Reject'}
          </button>
        </div>
      )}

      {settled && <p className="mt-3 text-[12.5px] text-[#5d7470]">Your decision has been recorded.</p>}

      <Evidence ids={block.evidence_ids} />
    </div>
  );
}

function Text({ block }: { block: TextBlock }) {
  return (
    <div>
      <p className="whitespace-pre-wrap text-[14px] leading-[1.65] text-[#22423e]">{block.text}</p>
      <Evidence ids={block.evidence_ids} />
    </div>
  );
}

// ---------------------------------------------------------------- registry
/**
 * The switch is exhaustive on purpose: the `never` in the default branch turns adding a block type to
 * the backend without adding it here into a TypeScript error, rather than a silently missing element
 * on someone's screen.
 *
 * Order is the backend's decision, because the skill that produced the blocks knows which figure
 * leads. Re-sorting here would put the headline somewhere its author did not intend.
 */
export function BlockRenderer({
  blocks,
  onDecide,
}: {
  blocks: Block[];
  onDecide?: (decision: 'approve' | 'reject') => Promise<void>;
}) {
  if (blocks.length === 0) return null;

  return (
    <div className="space-y-3">
      {blocks.map((block, index) => (
        <div key={`${block.type}-${index}`}>{render(block, onDecide)}</div>
      ))}
    </div>
  );
}

function render(block: Block, onDecide?: (decision: 'approve' | 'reject') => Promise<void>) {
  switch (block.type) {
    case 'text':
      return <Text block={block} />;
    case 'kpi':
      return <Kpi block={block} />;
    case 'table':
      return <Table block={block} />;
    case 'chart':
      return <Chart block={block} />;
    case 'callout':
      return <Callout block={block} />;
    case 'approval_card':
      return <ApprovalCard block={block} onDecide={onDecide} />;
    default: {
      const unhandled: never = block;
      return unhandled;
    }
  }
}
