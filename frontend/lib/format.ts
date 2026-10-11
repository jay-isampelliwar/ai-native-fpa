/**
 * Money, percentages and dates, formatted the way an Indian reader expects them.
 *
 * Every figure on screen goes through this file. A dashboard that formats a rupee
 * amount in two places will eventually format it two ways, and on a financial
 * screen that reads as two different numbers rather than one number typeset badly.
 *
 * The grouping is the lakh/crore system, not thousands: `₹5,00,000`, not
 * `₹500,000`. `Intl` does this correctly under the `en-IN` locale, so the digits
 * are never grouped by hand.
 *
 * Large totals are abbreviated because a card headline has room for `₹48.5L` and
 * not for `₹48,49,000`. The full figure is still available through `rupees` and is
 * what the legend rows and tables use, so the precise number is always one line
 * away from the abbreviated one.
 */

const INR = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 0,
});

const PLAIN = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 });

/** `₹5,00,000` — the exact amount, grouped in the Indian system. */
export function rupees(amount: number): string {
  return INR.format(Math.round(amount));
}

/** `5,00,000` — the same grouping without the symbol, for count-up animation. */
export function groupedDigits(amount: number): string {
  return PLAIN.format(Math.round(amount));
}

/**
 * `₹48.5L`, `₹1.42Cr` — shortened for headline positions.
 *
 * The threshold is a lakh rather than a thousand: Indian financial writing leaves
 * five- and six-digit figures in full and only abbreviates from a lakh upward.
 */
export function rupeesShort(amount: number): string {
  const absolute = Math.abs(amount);

  if (absolute >= 10_000_000) return `₹${trim(amount / 10_000_000)}Cr`;
  if (absolute >= 100_000) return `₹${trim(amount / 100_000)}L`;

  return rupees(amount);
}

/** One decimal, but only when it says something: `48.5`, and `20` rather than `20.0`. */
function trim(value: number): string {
  return value.toFixed(1).replace(/\.0$/, '');
}

/**
 * Axis ticks, all in the same unit.
 *
 * A scale that abbreviates only the values above a lakh prints `₹60,000` beside
 * `₹1L`, and the reader has to convert one of them to compare the two. The unit is
 * therefore chosen once from the largest value on the axis and applied to every
 * tick, so the column reads as one scale.
 */
export function rupeesAxis(value: number, largest: number): string {
  if (largest >= 10_000_000) return `₹${(value / 10_000_000).toFixed(1)}Cr`;
  if (largest >= 100_000) return `₹${(value / 100_000).toFixed(1)}L`;

  return `₹${PLAIN.format(Math.round(value))}`;
}

/** `+4.6%` / `−4.6%`, with a true minus sign rather than a hyphen. */
export function signedPercent(value: number, digits = 1): string {
  const sign = value > 0 ? '+' : value < 0 ? '−' : '';

  return `${sign}${Math.abs(value).toFixed(digits)}%`;
}

/** `12%` — a share of a whole, which is never signed. */
export function percent(value: number, digits = 0): string {
  return `${value.toFixed(digits)}%`;
}

/** The month-over-month change between two totals, as a percentage. */
export function changeBetween(current: number, previous: number): number {
  if (!previous) return 0;

  return ((current - previous) / previous) * 100;
}

/**
 * Split a whole into percentages that add up to exactly 100.
 *
 * Rounding each share on its own gives 99 or 101 often enough to matter, and the
 * doc is explicit that the distribution must total 100. The largest-remainder
 * method hands the leftover points to the slices that lost the most to rounding,
 * so the figures stay honest and the row order never changes.
 */
export function sharesOf(amounts: number[]): number[] {
  const total = amounts.reduce((sum, amount) => sum + amount, 0);

  if (!total) return amounts.map(() => 0);

  const exact = amounts.map((amount) => (amount / total) * 100);
  const floored = exact.map(Math.floor);

  let remaining = 100 - floored.reduce((sum, share) => sum + share, 0);

  const byRemainder = exact
    .map((value, index) => ({ index, remainder: value - Math.floor(value) }))
    .sort((a, b) => b.remainder - a.remainder);

  const shares = [...floored];

  for (const { index } of byRemainder) {
    if (remaining <= 0) break;
    shares[index] += 1;
    remaining -= 1;
  }

  return shares;
}

/** `January 2026` from `2026-01`. */
export function monthLabel(periodId: string): string {
  const [year, month] = periodId.split('-').map(Number);

  return new Date(year, month - 1, 1).toLocaleDateString('en-IN', {
    month: 'long',
    year: 'numeric',
  });
}

/** `Jan 2026` — the axis and selector form. */
export function monthLabelShort(periodId: string): string {
  const [year, month] = periodId.split('-').map(Number);

  return new Date(year, month - 1, 1).toLocaleDateString('en-IN', {
    month: 'short',
    year: 'numeric',
  });
}

/** `10:24 AM` — chat timestamps. */
export function clockTime(at: Date): string {
  // `en-IN` renders the meridiem lowercase; the reference and the rest of the app
  // set it in caps, and a locale is not the place to argue about that.
  return at
    .toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit', hour12: true })
    .toUpperCase();
}

/** `RS` for "Rohan Sharma" — the first letters of the first and last names, for an avatar. */
export function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);

  if (parts.length === 0) return '?';

  const first = parts[0][0];
  const last = parts.length > 1 ? parts[parts.length - 1][0] : '';

  return (first + last).toUpperCase();
}

/** `Rohan` for "Rohan Sharma" — what a greeting calls the person. */
export function firstNameOf(name: string): string {
  return name.trim().split(/\s+/)[0] ?? '';
}
