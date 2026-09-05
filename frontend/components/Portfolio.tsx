'use client';

import { useEffect, useState } from 'react';

import { Card, Kpi } from '@/components/blocks';
import { useUser } from '@/components/Shell';
import { assets, goals as goalsApi } from '@/lib/api';
import { rupees, toNumber } from '@/lib/format';
import type { GoalRead, HoldingsSummary } from '@/lib/types';

/**
 * What you own and what you are saving towards, side by side.
 *
 * The valuation date is shown next to the figure, not tucked into a footnote. These numbers are what a
 * statement said on the day it was exported and nothing refreshes them, so a portfolio dated in July
 * shown in September is stale by two months — and an interface that hides that is making a claim the
 * backend never made.
 *
 * Identification strength is surfaced too. Two of the three statement formats carry no ISIN, so some
 * positions are matched on a scheme name and folio instead; saying how many are ISIN-backed is the
 * honest way to describe how solid the portfolio view is.
 *
 * Goals show what is funding them rather than a stored balance, because a goal never holds money — it
 * links to assets, and the figure is computed when it is read.
 */
export default function Portfolio() {
  const userId = useUser();

  const [holdings, setHoldings] = useState<HoldingsSummary | null>(null);
  const [goals, setGoals] = useState<GoalRead[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    Promise.all([assets.holdings(userId), goalsApi.list(userId)])
      .then(([summary, goalList]) => {
        if (cancelled) return;
        setHoldings(summary);
        setGoals(goalList);
      })
      .catch(() => {
        if (!cancelled) setError('Your portfolio could not be loaded.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [userId]);

  if (loading) {
    return <Centered>Loading your portfolio…</Centered>;
  }

  if (error) {
    return <Centered>{error}</Centered>;
  }

  const empty = (holdings?.count ?? 0) === 0 && goals.length === 0;

  if (empty) {
    return (
      <Centered>
        Nothing here yet. Import a holdings statement, or add a goal, and this fills in.
      </Centered>
    );
  }

  const invested = toNumber(holdings?.invested_value);
  const current = toNumber(holdings?.current_value);
  const unrealised = toNumber(holdings?.unrealised);
  const returnPct = invested > 0 ? (unrealised / invested) * 100 : 0;

  return (
    <div className="no-scrollbar min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-[1000px] space-y-6 px-5 py-7">
        <header>
          <h1 className="font-serif text-[28px] leading-[1.15] tracking-[-0.015em] text-[#18312f]">
            Portfolio
          </h1>

          {holdings?.valued_at && (
            <p className="mt-1.5 text-[13px] leading-5 text-[#4d6560]">
              Valued as your statements stated on {holdings.valued_at}. Nothing here is a live price.
            </p>
          )}
        </header>

        {holdings && holdings.count > 0 && (
          <>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Kpi
                block={{
                  type: 'kpi',
                  label: 'Current value',
                  display: rupees(current),
                  value: null,
                  caption: `${holdings.count} positions`,
                  tone: 'neutral',
                  evidence_ids: [],
                }}
              />
              <Kpi
                block={{
                  type: 'kpi',
                  label: 'Invested',
                  display: rupees(invested),
                  value: null,
                  caption: null,
                  tone: 'neutral',
                  evidence_ids: [],
                }}
              />
              <Kpi
                block={{
                  type: 'kpi',
                  label: 'Unrealised',
                  display: rupees(unrealised),
                  value: null,
                  caption: `${returnPct >= 0 ? '+' : ''}${returnPct.toFixed(2)}%`,
                  tone: unrealised >= 0 ? 'positive' : 'negative',
                  evidence_ids: [],
                }}
              />
              <Kpi
                block={{
                  type: 'kpi',
                  label: 'Identified by ISIN',
                  display: `${holdings.identified_by_isin} of ${holdings.count}`,
                  value: null,
                  caption: 'the rest match on scheme and folio',
                  tone: 'neutral',
                  evidence_ids: [],
                }}
              />
            </div>

            <Card
              title="By asset type"
              note="Grouped from what each statement called the position, not from anything inferred."
            >
              <ul className="space-y-2">
                {Object.entries(holdings.by_asset_type).map(([kind, value]) => {
                  const amount = toNumber(value);
                  const share = current > 0 ? (amount / current) * 100 : 0;

                  return (
                    <li key={kind}>
                      <div className="flex items-baseline justify-between gap-3">
                        <span className="text-[12.5px] capitalize text-[#18312f]">
                          {kind.replace(/_/g, ' ')}
                        </span>
                        <span className="shrink-0 text-[12.5px] font-medium tabular-nums text-[#4d6560]">
                          {rupees(amount)} · {share.toFixed(1)}%
                        </span>
                      </div>

                      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-[#18312f]/7">
                        <div
                          className="h-full rounded-full bg-[#00947a]"
                          style={{ width: `${share}%` }}
                        />
                      </div>
                    </li>
                  );
                })}
              </ul>
            </Card>

            <Card title="Positions" subtitle={`Largest first, ${holdings.count} in total`}>
              <div className="no-scrollbar -mx-5 overflow-x-auto px-5">
                <table className="w-full min-w-[36rem] border-collapse">
                  <thead>
                    <tr className="border-b border-[#18312f]/9">
                      {['Instrument', 'Units', 'Avg cost', 'Invested', 'Value'].map((heading, index) => (
                        <th
                          key={heading}
                          scope="col"
                          className={`pb-2 text-[10.5px] uppercase leading-4 tracking-[0.07em] text-[#8ba09c] ${
                            index === 0 ? 'text-left' : 'text-right'
                          }`}
                        >
                          {heading}
                        </th>
                      ))}
                    </tr>
                  </thead>

                  <tbody>
                    {holdings.holdings.map((holding) => (
                      <tr key={holding.id} className="border-b border-[#18312f]/6 last:border-0">
                        <td className="max-w-[18rem] py-2 text-left text-[12.5px] text-[#18312f]">
                          <span className="block truncate">{holding.instrument_name}</span>
                          <span className="block truncate font-mono text-[10.5px] text-[#a8b8b4]">
                            {holding.isin ?? holding.folio_id ?? holding.identifier_type}
                          </span>
                        </td>
                        <td className="py-2 text-right text-[12.5px] tabular-nums text-[#4d6560]">
                          {holding.units}
                        </td>
                        <td className="py-2 text-right text-[12.5px] tabular-nums text-[#4d6560]">
                          {holding.average_cost}
                        </td>
                        <td className="py-2 text-right text-[12.5px] tabular-nums text-[#4d6560]">
                          {holding.invested_value ?? '—'}
                        </td>
                        <td className="py-2 text-right text-[12.5px] font-medium tabular-nums text-[#18312f]">
                          {holding.current_value ?? '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </>
        )}

        {goals.length > 0 && (
          <Card
            title="Goals"
            note="A goal links to the assets funding it and never stores a balance, so these figures are computed as you read them."
          >
            <ul className="space-y-3">
              {goals.map((goal) => {
                const target = toNumber(goal.target_amount);
                const funded = toNumber(goal.funded_corpus);
                const share = target > 0 ? Math.min((funded / target) * 100, 100) : 0;

                return (
                  <li key={goal.id}>
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="truncate text-[13px] font-medium text-[#18312f]">
                        {goal.label}
                      </span>
                      <span className="shrink-0 text-[12.5px] tabular-nums text-[#4d6560]">
                        {rupees(funded)} of {rupees(target)}
                      </span>
                    </div>

                    <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-[#18312f]/7">
                      <div className="h-full rounded-full bg-[#e7a14d]" style={{ width: `${share}%` }} />
                    </div>

                    <p className="mt-1 text-[11.5px] text-[#8ba09c]">
                      by {goal.target_date}
                      {toNumber(goal.monthly_contribution) > 0 && (
                        <> · {rupees(toNumber(goal.monthly_contribution))} a month going in</>
                      )}
                    </p>
                  </li>
                );
              })}
            </ul>
          </Card>
        )}
      </div>
    </div>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-1 items-center justify-center px-5 py-16">
      <p className="max-w-[42ch] text-center text-[13.5px] leading-6 text-[#5d7470]">{children}</p>
    </div>
  );
}
