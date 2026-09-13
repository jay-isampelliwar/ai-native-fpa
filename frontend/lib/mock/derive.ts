import { changeBetween, monthLabel, monthLabelShort, sharesOf } from '@/lib/format';
import { DEFAULT_PERIOD_ID, PERIODS } from '@/lib/mock/data';
import type { AllocationKey, Goal, Holding, PeriodId, RiskSnapshot, Sentiment } from '@/lib/mock/types';

/**
 * Everything the cards display, computed from the ledger rather than stored beside it.
 *
 * The rule this file exists to enforce: a figure that can be calculated is never
 * written down. Cash flow is income minus expense. Every delta is this month
 * against last. Every allocation percentage comes from the amounts. So the doc's
 * requirement — that adding an expense must reduce cash flow, and that no two
 * cards may disagree — holds by construction instead of by discipline.
 *
 * Sentiment is kept apart from direction, because on a financial screen they are
 * not the same thing. Income rising is good and expense rising is not, yet both
 * are an upward arrow. Callers get both facts and colour the arrow by sentiment
 * while pointing it by trend.
 */

export interface Delta {
  /** Percentage change against the previous month. */
  percent: number;
  trend: 'up' | 'down' | 'flat';
  /** Whether this movement is good news, which direction alone cannot say. */
  sentiment: Sentiment;
}

export interface AllocationSlice {
  key: AllocationKey;
  label: string;
  amount: number;
  /** Whole percentages that are guaranteed to sum to exactly 100 across slices. */
  share: number;
}

export interface CashFlowPoint {
  periodId: PeriodId;
  /** `Jan 2026` — the axis label. */
  label: string;
  value: number;
}

export interface PeriodView {
  id: PeriodId;
  label: string;
  shortLabel: string;

  income: { total: number; delta: Delta; sources: { label: string; amount: number; accent: string }[] };
  expense: { total: number; delta: Delta };
  cashFlow: { total: number; delta: Delta };
  investment: { total: number; delta: Delta; allocation: AllocationSlice[] };

  holdings: Holding[];
  risk: RiskSnapshot;
  goals: Goal[];
}

const ORDER = PERIODS.map((period) => period.id);

export const PERIOD_IDS = ORDER;

function sum(values: number[]): number {
  return values.reduce((total, value) => total + value, 0);
}

function incomeOf(index: number): number {
  return sum(PERIODS[index].incomeSources.map((source) => source.amount));
}

/**
 * Build a delta, given which direction counts as good news.
 *
 * `risingIsGood` is false for expenses: the doc says a rising expense reads as a
 * negative condition, so the badge turns red while the arrow still points up.
 */
function delta(current: number, previous: number | undefined, risingIsGood: boolean): Delta {
  if (previous === undefined) return { percent: 0, trend: 'flat', sentiment: 'neutral' };

  const percent = changeBetween(current, previous);
  const trend = percent > 0.05 ? 'up' : percent < -0.05 ? 'down' : 'flat';

  if (trend === 'flat') return { percent, trend, sentiment: 'neutral' };

  const good = trend === 'up' ? risingIsGood : !risingIsGood;

  return { percent, trend, sentiment: good ? 'positive' : 'negative' };
}

function indexOf(periodId: PeriodId): number {
  const index = ORDER.indexOf(periodId);

  return index === -1 ? ORDER.indexOf(DEFAULT_PERIOD_ID) : index;
}

/** Cash flow for one month: what came in, less what went out. */
export function cashFlowAt(index: number): number {
  return incomeOf(index) - PERIODS[index].expenseTotal;
}

/** The whole cash-flow series, which is what the trend chart draws. */
export function cashFlowSeries(): CashFlowPoint[] {
  return PERIODS.map((period, index) => ({
    periodId: period.id,
    label: monthLabelShort(period.id),
    value: cashFlowAt(index),
  }));
}

/** Resolve one month into the figures every card on screen reads. */
export function periodView(periodId: PeriodId): PeriodView {
  const index = indexOf(periodId);
  const record = PERIODS[index];
  const before = index > 0 ? index - 1 : undefined;

  const income = incomeOf(index);
  const expense = record.expenseTotal;

  const shares = sharesOf(record.allocation.map((slice) => slice.amount));

  return {
    id: record.id,
    label: monthLabel(record.id),
    shortLabel: monthLabelShort(record.id),

    income: {
      total: income,
      delta: delta(income, before === undefined ? undefined : incomeOf(before), true),
      sources: record.incomeSources,
    },

    expense: {
      total: expense,
      delta: delta(expense, before === undefined ? undefined : PERIODS[before].expenseTotal, false),
    },

    cashFlow: {
      total: income - expense,
      delta: delta(income - expense, before === undefined ? undefined : cashFlowAt(before), true),
    },

    investment: {
      total: record.investmentTotal,
      delta: delta(
        record.investmentTotal,
        before === undefined ? undefined : PERIODS[before].investmentTotal,
        true,
      ),
      allocation: record.allocation.map((slice, at) => ({ ...slice, share: shares[at] })),
    },

    holdings: record.holdings,
    risk: record.risk,
    goals: record.goals,
  };
}

/** The months the period selector offers, newest first. */
export function selectablePeriods(): { id: PeriodId; label: string }[] {
  return [...PERIODS]
    .reverse()
    .map((period) => ({ id: period.id, label: monthLabel(period.id) }));
}
