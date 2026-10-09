'use client';

import { ArrowUpRight } from 'lucide-react';
import { useEffect, useId, useMemo, useRef } from 'react';
import { useReducedMotion } from 'framer-motion';
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { monthLabel, rupeesAxis, rupeesShort, signedPercent } from '@/lib/format';
import type { CashFlowPoint, PeriodView } from '@/lib/mock/derive';
import Card from '@/components/ui/Card';

/**
 * The dashboard's lead card: cash flow over time, with the selected month marked.
 *
 * Cash flow is income minus expense, computed upstream, which is why this card
 * takes a series rather than reading anything itself. It cannot disagree with the
 * income and expense cards beside it because it is not told anything they are not.
 *
 * The path draws itself left to right on entry. Recharts can animate an area, but
 * it does so by growing the shape from the baseline, which reads as the values
 * rising rather than as the line being traced. The dash-offset trick below is the
 * one that matches the doc: measure the rendered path, set a dash as long as the
 * path, and walk the offset to zero. The fill fades in slightly behind it.
 *
 * The heading is a sentence, not a label. `Your cash flow is stronger this month —
 * up by 3.5%` states the finding; a reader who takes nothing else from the card
 * has still been told the thing it was drawn to say. The wording and the figure
 * both follow the data, so a month where cash flow fell says so.
 */

interface Props {
  series: CashFlowPoint[];
  period: PeriodView;
  index?: number;
}

export default function CashFlowTrendCard({ series, period, index = 0 }: Props) {
  const reduced = useReducedMotion();
  const gradientId = useId().replace(/:/g, '');

  const stronger = period.cashFlow.delta.trend !== 'down';

  // The reference draws a five-month window rather than every month held. A
  // window keeps the shape readable as the ledger grows.
  const windowed = useMemo(() => {
    const at = series.findIndex((point) => point.periodId === period.id);
    const end = Math.min(series.length, Math.max(5, at + 3));

    return series.slice(Math.max(0, end - 6), end);
  }, [series, period.id]);

  /**
   * The vertical scale, padded around the data rather than anchored to zero.
   *
   * Recharts defaults an area chart's axis to start at zero, which for figures that
   * sit between ₹55,000 and ₹1.1L pushes the whole curve into the top third and
   * flattens the only thing the chart exists to show — the shape of the movement.
   * Padding below and above instead spends the height on the range that is actually
   * occupied. The fill still reads as an area because the baseline is the floor of
   * the axis, not the number zero.
   */
  const [floor, ceiling] = useMemo(() => {
    const values = windowed.map((point) => point.value);
    const low = Math.min(...values);
    const high = Math.max(...values);
    const spread = high - low || Math.max(1, high * 0.1);

    return [Math.max(0, low - spread * 0.75), high + spread * 0.3];
  }, [windowed]);

  return (
    <Card index={index} label="Cash flow trend" className="overflow-hidden p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <h2 className="max-w-[26ch] text-[21px] leading-[1.28] font-bold tracking-[-0.01em] text-primary sm:text-[25px]">
          Your cash flow is {stronger ? 'stronger' : 'softer'} this month —{' '}
          <span
            className="tabular"
            style={{ color: stronger ? 'var(--accent)' : 'var(--negative)' }}
          >
            {stronger ? 'up' : 'down'} by {signedPercent(Math.abs(period.cashFlow.delta.percent))
              .replace('+', '')
              .replace('−', '')}
            .
          </span>
        </h2>

        <button
          type="button"
          className="inline-flex flex-none items-center gap-1.5 rounded-full border border-line bg-panel-subtle px-3.5 py-2 text-[13px] font-medium text-primary transition hover:border-line-strong"
        >
          View details
          <ArrowUpRight size={15} aria-hidden="true" />
        </button>
      </div>

      {/* The chart is decoration to a screen reader; this is the actual content. */}
      <p className="sr-only">
        Cash flow by month.{' '}
        {windowed
          .map((point) => `${monthLabel(point.periodId)}: ${rupeesShort(point.value)}`)
          .join('. ')}
        . Selected month {period.label}, {rupeesShort(period.cashFlow.total)},{' '}
        {signedPercent(period.cashFlow.delta.percent)} against the month before.
      </p>

      <div className="chart-surface mt-5 h-[210px] w-full sm:h-[236px]" aria-hidden="true">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={windowed} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
            <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.28} />
                <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
              </linearGradient>
            </defs>

            <CartesianGrid vertical={false} />

            <XAxis
              dataKey="label"
              axisLine={false}
              tickLine={false}
              tickMargin={12}
              minTickGap={4}
            />

            <YAxis
              orientation="right"
              domain={[floor, ceiling]}
              axisLine={false}
              tickLine={false}
              width={56}
              tickCount={4}
              tickMargin={6}
              tickFormatter={(value: number) => rupeesAxis(value, ceiling)}
            />

            <Tooltip
              cursor={{ strokeDasharray: '3 4' }}
              content={<CashFlowTooltip series={windowed} />}
            />

            <Area
              type="monotone"
              baseValue={floor}
              dataKey="value"
              stroke="var(--accent)"
              strokeWidth={2.5}
              fill={`url(#${gradientId})`}
              isAnimationActive={false}
              activeDot={{
                r: 5,
                fill: 'var(--accent)',
                stroke: 'var(--panel)',
                strokeWidth: 3,
              }}
              dot={false}
            />
          </AreaChart>
        </ResponsiveContainer>

        {!reduced && <PathReveal deps={[windowed, period.id]} />}
      </div>

      <dl className="mt-4 grid grid-cols-3 divide-x divide-[var(--pane-border)] border-t border-[var(--pane-border)] pt-3.5">
        <Stat label="High" value={Math.max(...windowed.map((point) => point.value))} />
        <Stat label="Avg" value={windowed.reduce((total, point) => total + point.value, 0) / windowed.length} />
        <Stat label="Low" value={Math.min(...windowed.map((point) => point.value))} />
      </dl>
    </Card>
  );
}

/** One cell of the footer strip under the chart: the range the window covers. */
function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="px-3 first:pl-0">
      <dt className="text-[12px] text-secondary">{label}:</dt>
      <dd className="tabular mt-1 text-[15px] font-semibold text-primary">{rupeesShort(value)}</dd>
    </div>
  );
}

/**
 * Trace the rendered line, once, after Recharts has laid it out.
 *
 * There is no way to ask Recharts for the path it is about to draw, so this waits
 * a frame, finds the curve it produced, measures it, and animates a dash offset
 * across it. Re-running when the data changes is what makes a month switch redraw
 * rather than sit still.
 *
 * It renders nothing. Living as a component rather than an effect in the parent
 * keeps the DOM poking in one place, and lets the whole behaviour be dropped for
 * reduced motion by not mounting it at all.
 */
function PathReveal({ deps }: { deps: unknown[] }) {
  const anchor = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const surface = anchor.current?.parentElement;
    if (!surface) return;

    let frame = requestAnimationFrame(() => {
      const curve = surface.querySelector<SVGPathElement>('.recharts-area-curve');
      const area = surface.querySelector<SVGPathElement>('.recharts-area-area');

      if (!curve) return;

      const length = curve.getTotalLength();

      curve.style.transition = 'none';
      curve.style.strokeDasharray = `${length}`;
      curve.style.strokeDashoffset = `${length}`;

      if (area) {
        area.style.transition = 'none';
        area.style.opacity = '0';
      }

      // A second frame, so the starting state is painted before the transition
      // to the end state begins. Setting both in one frame animates nothing.
      frame = requestAnimationFrame(() => {
        curve.style.transition = 'stroke-dashoffset 820ms cubic-bezier(0.22, 1, 0.36, 1)';
        curve.style.strokeDashoffset = '0';

        if (area) {
          // Behind the line, per the doc: the fill arrives once the path is under way.
          area.style.transition = 'opacity 620ms ease-out 180ms';
          area.style.opacity = '1';
        }
      });
    });

    return () => cancelAnimationFrame(frame);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return <span ref={anchor} className="hidden" />;
}

/**
 * The floating readout: month, value, and the change that got it there.
 *
 * Rendered straight from the payload Recharts hands over. An earlier version held
 * the last point in state so the box could survive a frame with no payload, which
 * bought nothing — Recharts unmounts this component between points anyway — and
 * cost a render cascade on every pointer move across the chart.
 */
function CashFlowTooltip({
  active,
  payload,
  series,
}: {
  active?: boolean;
  payload?: { payload: CashFlowPoint }[];
  series: CashFlowPoint[];
}) {
  const point = payload?.[0]?.payload;

  if (!active || !point) return null;

  const at = series.findIndex((entry) => entry.periodId === point.periodId);
  const before = at > 0 ? series[at - 1].value : undefined;
  const change = before ? ((point.value - before) / before) * 100 : 0;

  return (
    <div className="rounded-xl border border-line bg-panel-elevated px-3 py-2.5 shadow-[var(--shadow-card)]">
      <p className="text-[12px] font-semibold text-primary">{monthLabel(point.periodId)}</p>

      <p className="mt-1.5 flex items-center gap-1.5 text-[12px] text-secondary">
        <span
          className="h-2 w-2 flex-none rounded-full"
          style={{ background: 'var(--accent)' }}
          aria-hidden="true"
        />
        Cash flow
        <span className="tabular font-semibold text-primary">{rupeesShort(point.value)}</span>
        {before !== undefined && (
          <span
            className="tabular font-semibold"
            style={{ color: change >= 0 ? 'var(--positive)' : 'var(--negative)' }}
          >
            {signedPercent(change)}
          </span>
        )}
      </p>
    </div>
  );
}
