import type { AllocationAmount, Goal, Holding, PeriodRecord, RiskSnapshot } from '@/lib/mock/types';

/**
 * The mock ledger — eight months of invented but internally coherent records.
 *
 * This is the file that goes away when the backend grows record endpoints. It is
 * the only place in the app that states a number without deriving it, which is
 * what makes that swap a change to one module.
 *
 * Cash flow is absent on purpose. It is income minus expense, computed in
 * `derive.ts`, so it cannot drift from the two figures it is made of.
 *
 * The months rise gently and then dip in February, because a line that only ever
 * climbs tells a reader nothing about whether the shape means anything. January
 * 2026 is the default selection: it is the month both reference screens show.
 */

/** Holdings and risk barely move month to month, so they are written once. */
const HOLDINGS: Holding[] = [
  { ticker: 'AAPL', name: 'Apple Inc.', price: 16_520, weight: 24, profitLoss: 12.4, tint: '#1F2421' },
  { ticker: 'RELIANCE', name: 'Reliance Industries', price: 2_856, weight: 18, profitLoss: 4.8, tint: '#B4530A' },
  { ticker: 'HDFC', name: 'HDFC Bank', price: 1_642, weight: 15, profitLoss: 6.1, tint: '#1B4FA0' },
  { ticker: 'TCS', name: 'Tata Consultancy', price: 3_456, weight: 12, profitLoss: -2.3, tint: '#5B3FA8' },
  { ticker: 'INFY', name: 'Infosys', price: 1_498, weight: 8, profitLoss: 3.7, tint: '#0A7B6B' },
];

const RISK: RiskSnapshot = {
  score: 6.8,
  category: 'Moderate',
  metrics: [
    {
      label: 'Volatility (β)',
      value: '1.12',
      explanation: 'Your portfolio moves about 12% more than the market does.',
    },
    {
      label: 'Sharpe ratio',
      value: '1.84',
      explanation: 'Return earned for each unit of risk taken. Above 1 is considered good.',
    },
    {
      label: 'Max drawdown',
      value: '−8.2%',
      explanation: 'The deepest fall from a peak this portfolio has seen.',
    },
    {
      label: 'Diversification',
      value: 'Good',
      explanation: 'How well your money is spread across unrelated assets.',
    },
  ],
};

const GOALS: Goal[] = [
  {
    id: 'home',
    title: 'Buy a home',
    target: 1_00_00_000,
    saved: 42_00_000,
    targetYear: 2028,
    status: 'on-track',
    icon: 'home',
  },
  {
    id: 'education',
    title: "Child's education",
    target: 40_00_000,
    saved: 9_60_000,
    targetYear: 2032,
    status: 'at-risk',
    icon: 'graduation',
  },
];

function allocation(equity: number, debt: number, gold: number, mutualFunds: number): AllocationAmount[] {
  return [
    { key: 'equity', label: 'Equity', amount: equity },
    { key: 'debt', label: 'Debt', amount: debt },
    { key: 'gold', label: 'Gold', amount: gold },
    { key: 'mutualFunds', label: 'Mutual funds', amount: mutualFunds },
  ];
}

/**
 * One row per month, oldest first.
 *
 * The income and expense figures are chosen so that the derived cash flow reads
 * the way the reference screen does — January up 3.5% on December — while still
 * being a real subtraction. The reference's own badge percentages are not
 * reproduced exactly, because the numbers printed on it do not agree with each
 * other and the doc asks for totals that do.
 */
export const PERIODS: PeriodRecord[] = [
  {
    id: '2025-08',
    incomeSources: [
      { label: 'Salary', amount: 2_72_000, accent: 'accent' },
      { label: 'Freelance', amount: 1_40_000, accent: 'yellow' },
    ],
    expenseTotal: 3_57_000,
    investmentTotal: 41_20_000,
    allocation: allocation(24_72_000, 10_30_000, 4_12_000, 2_06_000),
    holdings: HOLDINGS,
    risk: RISK,
    goals: GOALS,
  },
  {
    id: '2025-09',
    incomeSources: [
      { label: 'Salary', amount: 2_78_000, accent: 'accent' },
      { label: 'Freelance', amount: 1_46_000, accent: 'yellow' },
    ],
    expenseTotal: 3_61_000,
    investmentTotal: 42_65_000,
    allocation: allocation(25_59_000, 10_66_000, 4_26_000, 2_14_000),
    holdings: HOLDINGS,
    risk: RISK,
    goals: GOALS,
  },
  {
    id: '2025-10',
    incomeSources: [
      { label: 'Salary', amount: 2_85_000, accent: 'accent' },
      { label: 'Freelance', amount: 1_54_000, accent: 'yellow' },
    ],
    expenseTotal: 3_68_000,
    investmentTotal: 44_10_000,
    allocation: allocation(26_46_000, 11_02_000, 4_41_000, 2_21_000),
    holdings: HOLDINGS,
    risk: RISK,
    goals: GOALS,
  },
  {
    id: '2025-11',
    incomeSources: [
      { label: 'Salary', amount: 2_90_000, accent: 'accent' },
      { label: 'Freelance', amount: 1_62_000, accent: 'yellow' },
    ],
    expenseTotal: 3_71_000,
    investmentTotal: 45_38_000,
    allocation: allocation(27_23_000, 11_34_000, 4_54_000, 2_27_000),
    holdings: HOLDINGS,
    risk: RISK,
    goals: GOALS,
  },
  {
    id: '2025-12',
    incomeSources: [
      { label: 'Salary', amount: 2_94_000, accent: 'accent' },
      { label: 'Freelance', amount: 1_84_000, accent: 'yellow' },
    ],
    expenseTotal: 3_81_400,
    investmentTotal: 47_03_000,
    allocation: allocation(28_22_000, 11_75_000, 4_70_000, 2_36_000),
    holdings: HOLDINGS,
    risk: RISK,
    goals: GOALS,
  },
  {
    // The month both reference screens show, and the default selection.
    id: '2026-01',
    incomeSources: [
      { label: 'Salary', amount: 3_00_000, accent: 'accent' },
      { label: 'Freelance', amount: 2_00_000, accent: 'yellow' },
    ],
    expenseTotal: 4_00_000,
    investmentTotal: 48_49_000,
    allocation: allocation(30_07_000, 11_15_000, 4_36_000, 2_91_000),
    holdings: HOLDINGS,
    risk: RISK,
    goals: GOALS,
  },
  {
    id: '2026-02',
    incomeSources: [
      { label: 'Salary', amount: 3_00_000, accent: 'accent' },
      { label: 'Freelance', amount: 1_94_000, accent: 'yellow' },
    ],
    expenseTotal: 4_02_000,
    investmentTotal: 47_92_000,
    allocation: allocation(29_71_000, 11_02_000, 4_31_000, 2_88_000),
    holdings: HOLDINGS,
    risk: RISK,
    goals: GOALS,
  },
  {
    id: '2026-03',
    incomeSources: [
      { label: 'Salary', amount: 3_08_000, accent: 'accent' },
      { label: 'Freelance', amount: 1_98_000, accent: 'yellow' },
    ],
    expenseTotal: 3_98_000,
    investmentTotal: 49_64_000,
    allocation: allocation(30_78_000, 11_41_000, 4_47_000, 2_98_000),
    holdings: HOLDINGS,
    risk: RISK,
    goals: GOALS,
  },
];

export const DEFAULT_PERIOD_ID = '2026-01';

/** The signed-in person, for the greeting and avatar. No backend has a profile yet. */
export const PROFILE = {
  name: 'Rohan Sharma',
  firstName: 'Rohan',
  initials: 'RS',
};
