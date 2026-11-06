'use client';

import { ArrowDownLeft, ArrowUpRight, Bell, Mic, PiggyBank, Search, Wallet } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';

import { cashFlowSeries, PERIOD_IDS, periodView, selectablePeriods, trendUpTo } from '@/lib/mock/derive';
import { DEFAULT_PERIOD_ID, PROFILE } from '@/lib/mock/data';
import MonthSelect from '@/components/ui/MonthSelect';
import UserMenu from '@/components/ui/UserMenu';
import CashFlowTrendCard from '@/components/dashboard/CashFlowTrendCard';
import ExpenseSummaryCard from '@/components/dashboard/ExpenseSummaryCard';
import GoalsCard from '@/components/dashboard/GoalsCard';
import HoldingsCard from '@/components/dashboard/HoldingsCard';
import IncomeSummaryCard from '@/components/dashboard/IncomeSummaryCard';
import InvestmentDetailCard from '@/components/dashboard/InvestmentDetailCard';
import KpiSparkCard from '@/components/dashboard/KpiSparkCard';
import MonthPulseCard from '@/components/dashboard/MonthPulseCard';
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
 * The layout follows the reference: a row of four figure cards with sparklines, then
 * the big chart with three small month cards beside it, then the detail cards.
 *
 * `Updated just now` appears after a month switch and then stands down. It is in
 * an `aria-live` region so the change is announced rather than only seen — with a
 * month's worth of figures moving at once, a reader who cannot see them move needs
 * telling that they did.
 */
export default function FinancialDashboard() {
  const [selected, setSelected] = useState(DEFAULT_PERIOD_ID);
  const [justUpdated, setJustUpdated] = useState(false);

  const periods = useMemo(() => selectablePeriods(), []);
  const series = useMemo(() => cashFlowSeries(), []);
  const period = useMemo(() => periodView(selected), [selected]);

  // The selected month and the two before it, newest first, for the side cards.
  const recent = useMemo(() => {
    const at = PERIOD_IDS.indexOf(period.id);

    return PERIOD_IDS.slice(Math.max(0, at - 2), at + 1)
      .reverse()
      .map((id) => periodView(id));
  }, [period.id]);

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
      />

      <div className="space-y-3.5 px-4 pt-1 pb-6 sm:px-6">
        <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2 2xl:grid-cols-4">
          <KpiSparkCard
            icon={<ArrowDownLeft size={15} strokeWidth={2.4} />}
            title="Income"
            value={period.income.total}
            delta={period.income.delta}
            trend={trendUpTo(period.id, 'income')}
            color="var(--chart-1)"
            index={0}
          />
          <KpiSparkCard
            icon={<ArrowUpRight size={15} strokeWidth={2.4} />}
            title="Expense"
            value={period.expense.total}
            delta={period.expense.delta}
            trend={trendUpTo(period.id, 'expense')}
            color="var(--chart-2)"
            index={1}
          />
          <KpiSparkCard
            icon={<Wallet size={15} />}
            title="Cash flow"
            value={period.cashFlow.total}
            delta={period.cashFlow.delta}
            trend={trendUpTo(period.id, 'cashFlow')}
            color="var(--chart-3)"
            index={2}
          />
          <KpiSparkCard
            icon={<PiggyBank size={15} />}
            title="Investments"
            value={period.investment.total}
            delta={period.investment.delta}
            trend={trendUpTo(period.id, 'investment')}
            color="var(--chart-4)"
            index={3}
          />
        </div>

        <div className="grid grid-cols-1 gap-3.5 xl:grid-cols-[minmax(0,1fr)_250px]">
          <CashFlowTrendCard series={series} period={period} index={4} />

          <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-3 xl:grid-cols-1">
            {recent.map((month, at) => (
              <MonthPulseCard
                key={month.id}
                period={month}
                series={series}
                color={['var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)'][at]}
                index={5 + at}
              />
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 gap-3.5 xl:grid-cols-2">
          <IncomeSummaryCard
            period={period}
            periods={periods}
            onPeriodChange={setSelected}
            index={8}
          />

          <ExpenseSummaryCard
            period={period}
            periods={periods}
            onPeriodChange={setSelected}
            index={9}
          />

          <InvestmentDetailCard period={period} index={10} />

          <RiskScoreCard risk={period.risk} index={11} />

          <HoldingsCard holdings={period.holdings} index={12} />

          <GoalsCard goals={period.goals} index={13} />
        </div>
      </div>
    </div>
  );
}

function DashboardHeader({
  periods,
  selected,
  onSelect,
  justUpdated,
}: {
  periods: { id: string; label: string }[];
  selected: string;
  onSelect: (id: string) => void;
  justUpdated: boolean;
}) {
  return (
    <header className="sticky top-0 z-30 bg-[var(--pane)] px-4 pt-5 pb-4 backdrop-blur-xl sm:px-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-[24px] leading-tight font-bold tracking-[-0.02em] text-primary sm:text-[27px]">
            Welcome back, {PROFILE.firstName}!
          </h1>

          <p className="mt-1 flex flex-wrap items-center gap-2 text-[13px] text-secondary">
            Here&apos;s your financial picture for {periods.find((option) => option.id === selected)?.label}.
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
          {/* Search and voice are drawn only. There is no search route or speech-to-text yet. */}
          <label className="hidden h-9 items-center gap-2 rounded-full border border-[var(--pane-border)] bg-panel-subtle px-3 text-secondary lg:flex">
            <Search size={14} aria-hidden="true" />
            <span className="sr-only">Search</span>
            <input
              type="search"
              placeholder="Search"
              className="w-28 bg-transparent text-[12.5px] text-primary outline-none placeholder:text-muted xl:w-36"
            />
          </label>

          <button
            type="button"
            aria-label="Ask by voice"
            title="Ask by voice"
            className="send-gradient grid h-9 w-9 place-items-center rounded-full"
          >
            <Mic size={15} aria-hidden="true" />
          </button>

          <MonthSelect options={periods} value={selected} onChange={onSelect} />

          <IconButton label="Notifications" dot>
            <Bell size={16} />
          </IconButton>

          <UserMenu />
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
      className="icon-pill relative h-9 w-9"
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
