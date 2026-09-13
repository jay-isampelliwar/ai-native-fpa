'use client';

import { Bell, EllipsisVertical, Search } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';

import { cashFlowSeries, periodView, selectablePeriods } from '@/lib/mock/derive';
import { DEFAULT_PERIOD_ID } from '@/lib/mock/data';
import MonthSelect from '@/components/ui/MonthSelect';
import UserMenu from '@/components/ui/UserMenu';
import CashFlowTrendCard from '@/components/dashboard/CashFlowTrendCard';
import ExpenseSummaryCard from '@/components/dashboard/ExpenseSummaryCard';
import GoalsCard from '@/components/dashboard/GoalsCard';
import HoldingsCard from '@/components/dashboard/HoldingsCard';
import IncomeSummaryCard from '@/components/dashboard/IncomeSummaryCard';
import InvestmentDetailCard from '@/components/dashboard/InvestmentDetailCard';
import RiskScoreCard from '@/components/dashboard/RiskScoreCard';

/**
 * The right-hand pane: every card, all reading one derived snapshot.
 *
 * The selected month is the only state here. Everything on screen is
 * `periodView(selected)`, so a change moves every card at once and no two of them
 * can be describing different months — which is the failure the doc's "do not
 * produce contradictory totals" is really about.
 *
 * The data is mock and this component does not know that. It calls the derive
 * layer, which today reads a local ledger and tomorrow reads an API, and nothing
 * in this file would change.
 *
 * `Updated just now` appears after a month switch and then stands down. It is in
 * an `aria-live` region so the change is announced rather than only seen — with a
 * month's worth of figures moving at once, a reader who cannot see them move needs
 * telling that they did.
 */
export default function FinancialDashboard({ userId }: { userId: number | null }) {
  const [selected, setSelected] = useState(DEFAULT_PERIOD_ID);
  const [justUpdated, setJustUpdated] = useState(false);

  const periods = useMemo(() => selectablePeriods(), []);
  const series = useMemo(() => cashFlowSeries(), []);
  const period = useMemo(() => periodView(selected), [selected]);

  const lastSeen = useRef(selected);

  // The status is a consequence of switching, not of mounting: saying "updated just
  // now" about the initial render would be false. This compares against the month
  // last seen rather than holding a `first run` flag, because React runs an effect
  // twice on mount in development and a flag reads as "not first" the second time.
  useEffect(() => {
    if (lastSeen.current === selected) return;

    lastSeen.current = selected;

    setJustUpdated(true);

    const timer = setTimeout(() => setJustUpdated(false), 4200);

    return () => clearTimeout(timer);
  }, [selected]);

  return (
    <div className="quiet-scroll flex h-full min-h-0 flex-col overflow-y-auto">
      <DashboardHeader
        periods={periods}
        selected={selected}
        onSelect={setSelected}
        justUpdated={justUpdated}
        userId={userId}
      />

      <div className="grid grid-cols-1 gap-3.5 px-4 pt-1 pb-6 sm:px-6 xl:grid-cols-2">
        {/* The lead card spans the pane at every width. */}
        <div className="xl:col-span-2">
          <CashFlowTrendCard series={series} period={period} index={0} />
        </div>

        <IncomeSummaryCard
          period={period}
          periods={periods}
          onPeriodChange={setSelected}
          index={1}
        />

        <ExpenseSummaryCard
          period={period}
          periods={periods}
          onPeriodChange={setSelected}
          index={2}
        />

        <InvestmentDetailCard period={period} index={3} />

        <RiskScoreCard risk={period.risk} index={4} />

        <HoldingsCard holdings={period.holdings} index={5} />

        <GoalsCard goals={period.goals} index={6} />
      </div>
    </div>
  );
}

function DashboardHeader({
  periods,
  selected,
  onSelect,
  justUpdated,
  userId,
}: {
  periods: { id: string; label: string }[];
  selected: string;
  onSelect: (id: string) => void;
  justUpdated: boolean;
  userId: number | null;
}) {
  return (
    <header className="sticky top-0 z-30 bg-background/95 px-4 pt-5 pb-3 backdrop-blur-xl sm:px-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-[24px] leading-tight font-bold tracking-[-0.02em] text-primary sm:text-[27px]">
            Financial overview
          </h1>

          <p className="mt-1 flex flex-wrap items-center gap-2 text-[13px] text-secondary">
            Your complete financial picture, powered by AI.
            {/* Polite, so it waits for a pause rather than interrupting. */}
            <span aria-live="polite" className="contents">
              {justUpdated && (
                <span
                  className="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11.5px] font-medium"
                  style={{ background: 'var(--accent-soft)', color: 'var(--accent)' }}
                >
                  <span
                    className="h-1.5 w-1.5 rounded-full"
                    style={{ background: 'var(--accent)' }}
                    aria-hidden="true"
                  />
                  Updated just now
                </span>
              )}
            </span>
          </p>
        </div>

        <div className="flex flex-none items-center gap-1.5">
          <MonthSelect options={periods} value={selected} onChange={onSelect} />

          <IconButton label="Search"><Search size={16} /></IconButton>

          <IconButton label="Notifications" dot>
            <Bell size={16} />
          </IconButton>

          <IconButton label="Dashboard preferences">
            <EllipsisVertical size={16} />
          </IconButton>

          <UserMenu userId={userId} />
        </div>
      </div>
    </header>
  );
}

function IconButton({
  label,
  children,
  dot = false,
}: {
  label: string;
  children: React.ReactNode;
  dot?: boolean;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className="relative grid h-8 w-8 place-items-center rounded-full border border-line bg-panel-subtle text-secondary transition hover:border-line-strong hover:text-primary"
    >
      {children}
      {dot && (
        <span
          aria-hidden="true"
          className="absolute top-1.5 right-1.5 h-1.5 w-1.5 rounded-full"
          style={{ background: 'var(--negative)' }}
        />
      )}
    </button>
  );
}
