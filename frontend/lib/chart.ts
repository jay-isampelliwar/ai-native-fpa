/**
 * Chart tokens.
 *
 * The two categorical hues are validated, not chosen by eye: run through the
 * palette checks against this surface they pass the lightness band, chroma floor,
 * CVD separation (worst adjacent pair ΔE 11.1 protan), the normal-vision floor
 * (ΔE 21.0) and 3:1 contrast. The brand's own deep teal #183f3a fails two of
 * those as a fill — too dark, and near-gray in chroma — so it stays what it is in
 * the UI chrome and is not used to carry data.
 */
export const SURFACE = '#f7f4ec';

export const SERIES = {
  /** Money already committed — what the client is doing today. */
  existing: '#00947a',
  /** The shortfall the plan asks them to add. */
  additional: '#c07018',
} as const;

/** Reserved for state, never for "series 3". Each ships with a label, never
 *  colour alone. Validated against a white card surface: all three pass the
 *  lightness band, chroma floor, CVD separation (worst ΔE 10.5 protan),
 *  normal-vision floor (ΔE 16.4) and 3:1 contrast. */
export const STATUS = {
  good: '#00947a',
  warning: '#bf8410',
  critical: '#b83f28',
} as const;

export type StatusKey = keyof typeof STATUS;

/** The workbook writes Red / Yellow / Green, plus prose verdicts on Debt_Ratios. */
export const statusOf = (raw: string | null | undefined): StatusKey => {
  const text = (raw ?? '').toLowerCase();
  if (/green|healthy|good|strong|comfortable/.test(text)) return 'good';
  if (/red|critical|poor|reduce|stretch|weak/.test(text)) return 'critical';
  return 'warning';
};

export const INK = {
  primary: '#18312f',
  secondary: '#4d6560',
  muted: '#8ba09c',
  grid: 'rgba(24, 49, 47, 0.10)',
} as const;

/** A compact axis tick: ₹1.2Cr, ₹45L, ₹8k. */
export const axisRupee = (value: number) => {
  const abs = Math.abs(value);
  if (abs >= 1e7) return `₹${(value / 1e7).toFixed(abs >= 1e8 ? 0 : 1)}Cr`;
  if (abs >= 1e5) return `₹${(value / 1e5).toFixed(0)}L`;
  if (abs >= 1e3) return `₹${(value / 1e3).toFixed(0)}k`;
  return `₹${Math.round(value)}`;
};

/**
 * A "nice" axis maximum at 1/2/5 × 10ⁿ, so ticks land on round numbers.
 * Without it an axis reads 0 / 3,847,221 / 7,694,442 and nobody can use it.
 */
export const niceCeil = (value: number) => {
  if (value <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const step = [1, 2, 2.5, 5, 10].find((s) => value <= s * magnitude) ?? 10;
  return step * magnitude;
};
