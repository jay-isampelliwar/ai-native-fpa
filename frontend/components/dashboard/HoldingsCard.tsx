'use client';

import { motion, useReducedMotion } from 'framer-motion';
import { ArrowDownRight, ArrowUpRight, ChartNoAxesColumn } from 'lucide-react';

import { percent, rupees, signedPercent } from '@/lib/format';
import type { Holding } from '@/lib/mock/types';
import Card, { CardHeading } from '@/components/ui/Card';

/**
 * The positions, as a real table.
 *
 * A table rather than a grid of divs because that is what it is: four columns of
 * comparable values with a header each. A screen reader then announces "Weight,
 * 24 percent" instead of reading a loose number, and the doc asks for semantic
 * tables specifically.
 *
 * Rows animate their position rather than jumping when the order changes, which
 * is what `layout` on the row buys. The weight bars grow horizontally on entry,
 * sharing one duration so the column resolves together.
 *
 * Profit and loss is stated three ways — arrow, sign and colour — so none of them
 * has to carry it alone.
 */
export default function HoldingsCard({
  holdings,
  index = 0,
}: {
  holdings: Holding[];
  index?: number;
}) {
  const widest = Math.max(...holdings.map((holding) => holding.weight), 1);

  return (
    <Card index={index} label="Holdings" className="flex flex-col p-5">
      <CardHeading
        icon={<ChartNoAxesColumn size={16} strokeWidth={2.5} />}
        title="Holdings"
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

      <div className="mt-4 -mx-1 overflow-x-auto">
        <table className="w-full min-w-[368px] table-fixed border-collapse">
          {/* `table-fixed` plus explicit widths: without it the asset column takes
              whatever a long name needs, which squeezed the weight bar to a dot and
              pushed the P/L badge past the card's edge. The asset column now takes
              the remainder and its text truncates instead. */}
          <colgroup>
            <col />
            <col style={{ width: 74 }} />
            <col style={{ width: 100 }} />
            <col style={{ width: 76 }} />
          </colgroup>

          <thead>
            <tr className="text-left text-[11px] font-medium text-muted">
              <th scope="col" className="px-1 pb-2 font-medium">Asset</th>
              <th scope="col" className="px-1 pb-2 text-right font-medium">Price</th>
              <th scope="col" className="px-1 pb-2 font-medium">Weight</th>
              <th scope="col" className="px-1 pb-2 text-right font-medium">P/L</th>
            </tr>
          </thead>

          <tbody>
            {holdings.map((holding) => (
              <HoldingRow key={holding.ticker} holding={holding} widest={widest} />
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function HoldingRow({ holding, widest }: { holding: Holding; widest: number }) {
  const reduced = useReducedMotion();

  const up = holding.profitLoss >= 0;
  const Arrow = up ? ArrowUpRight : ArrowDownRight;

  return (
    <motion.tr
      layout={!reduced}
      transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}
      className="border-t border-line transition-colors hover:bg-panel-subtle"
    >
      <td className="px-1 py-2.5">
        <div className="flex items-center gap-2.5">
          <AssetAvatar holding={holding} />
          <div className="min-w-0">
            <p className="truncate text-[13px] font-semibold text-primary">{holding.ticker}</p>
            <p className="truncate text-[11.5px] text-muted">{holding.name}</p>
          </div>
        </div>
      </td>

      <td className="tabular px-1 py-2.5 text-right text-[13px] text-primary">
        {rupees(holding.price)}
      </td>

      <td className="px-1 py-2.5">
        <div className="flex items-center gap-2">
          <span className="tabular w-7 flex-none text-[12px] text-secondary">
            {percent(holding.weight)}
          </span>
          <span
            className="h-1.5 min-w-[52px] flex-1 overflow-hidden rounded-full bg-track"
            aria-hidden="true"
          >
            <motion.span
              className="block h-full rounded-full"
              style={{ background: 'var(--meter)' }}
              initial={reduced ? false : { width: 0 }}
              animate={{ width: `${(holding.weight / widest) * 100}%` }}
              transition={{ duration: 0.62, ease: [0.22, 1, 0.36, 1] }}
            />
          </span>
        </div>
      </td>

      <td className="px-1 py-2.5 text-right">
        <span
          className="tabular inline-flex items-center rounded-full px-1.5 py-1 text-[11.5px] font-semibold whitespace-nowrap"
          style={{
            color: up ? 'var(--positive)' : 'var(--negative)',
            background: up ? 'var(--positive-soft)' : 'var(--negative-soft)',
          }}
        >
          <Arrow size={11} strokeWidth={2.5} aria-hidden="true" />
          {signedPercent(holding.profitLoss)}
        </span>
      </td>
    </motion.tr>
  );
}

/**
 * The asset's mark: its first character on its own tint.
 *
 * The doc asks for a real logo where one is available and a lettered fallback
 * where it is not. Nothing here ships logos — they are third-party marks with
 * their own licences — so every asset takes the fallback, drawn well enough that
 * it does not read as a missing image.
 */
function AssetAvatar({ holding }: { holding: Holding }) {
  return (
    <span
      aria-hidden="true"
      className="grid h-7 w-7 flex-none place-items-center rounded-full text-[11px] font-bold text-white"
      style={{ background: holding.tint }}
    >
      {holding.ticker.charAt(0)}
    </span>
  );
}
