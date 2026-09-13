/**
 * The shape of the financial state every dashboard card reads from.
 *
 * One model, derived once per selected month, rather than a set of figures per
 * card. The doc is explicit that adding an expense must reduce cash flow, and the
 * only way to guarantee that is to make cash flow something computed rather than
 * something stored next to income and expense and hoped to agree with them.
 *
 * So the stored record is deliberately small — income sources, an expense total,
 * holdings, allocation amounts — and everything a card actually displays
 * (cash flow, every percentage, every month-over-month delta) is derived in
 * `derive.ts`. A contradictory total is then not something to catch in review; it
 * is something that cannot be written down.
 *
 * These types describe mock data today and an API response tomorrow. Nothing here
 * mentions where the numbers came from, which is what lets `mock/data.ts` be
 * swapped for a fetch without a card noticing.
 */

/** `2026-01`. Sorts correctly as a string, which is why it is not a Date. */
export type PeriodId = string;

export type Trend = 'up' | 'down' | 'flat';

/** Whether a movement is good news, which is not the same as which way it points. */
export type Sentiment = 'positive' | 'negative' | 'neutral';

export type AllocationKey = 'equity' | 'debt' | 'gold' | 'mutualFunds';

export type GoalStatus = 'on-track' | 'at-risk' | 'off-track';

export interface IncomeSource {
  label: string;
  amount: number;
  /** Which accent marks this source in the breakdown rail. */
  accent: 'accent' | 'yellow' | 'blue';
}

export interface AllocationAmount {
  key: AllocationKey;
  label: string;
  amount: number;
}

export interface Holding {
  ticker: string;
  name: string;
  /** Current price per unit, in rupees. */
  price: number;
  /** Share of the portfolio, 0-100. Holdings need not sum to 100; `View all` implies more. */
  weight: number;
  /** Profit or loss as a percentage of cost. */
  profitLoss: number;
  /** Brand tint for the fallback avatar when no logo is available. */
  tint: string;
}

export interface RiskMetric {
  label: string;
  value: string;
  /** Plain-language meaning, surfaced as a tooltip and to screen readers. */
  explanation: string;
}

export interface RiskSnapshot {
  /** 0-10. The gauge maps this onto a semicircle. */
  score: number;
  category: string;
  metrics: RiskMetric[];
}

export interface Goal {
  id: string;
  title: string;
  /** What the goal costs. */
  target: number;
  /** What has been put aside so far. */
  saved: number;
  targetYear: number;
  status: GoalStatus;
  icon: 'home' | 'graduation' | 'palm';
}

/** Everything recorded for one month. Nothing here is a percentage or a delta. */
export interface PeriodRecord {
  id: PeriodId;
  incomeSources: IncomeSource[];
  expenseTotal: number;
  investmentTotal: number;
  allocation: AllocationAmount[];
  holdings: Holding[];
  risk: RiskSnapshot;
  goals: Goal[];
}
