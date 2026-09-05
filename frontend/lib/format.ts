/**
 * Rupee formatting for the few places the client has a number rather than a string.
 *
 * Almost everything the backend sends is already formatted — a block's `display` field is the
 * backend's own rendering and is what should be shown, because formatting currency in two codebases
 * guarantees they eventually disagree and the one on screen will be the wrong one.
 *
 * These exist for the cases where the client genuinely holds a number: an axis tick it computed, a
 * total it summed across staged rows for a reconciliation screen. `rupees` matches what the backend
 * produces so a computed subtotal sits beside a returned figure without looking foreign.
 */

export const rupees = (value: number): string =>
  `INR ${Math.round(value).toLocaleString('en-IN')}`;

export const rupeesExact = (value: number): string =>
  `INR ${value.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

/** A compact axis tick: ₹1.2Cr, ₹45L, ₹8k. */
export const axisRupee = (value: number): string => {
  const abs = Math.abs(value);
  if (abs >= 1e7) return `₹${(value / 1e7).toFixed(abs >= 1e8 ? 0 : 1)}Cr`;
  if (abs >= 1e5) return `₹${(value / 1e5).toFixed(0)}L`;
  if (abs >= 1e3) return `₹${(value / 1e3).toFixed(0)}k`;
  return `₹${Math.round(value)}`;
};

/** Decimal strings arrive from the backend; parse only for geometry, never for display. */
export const toNumber = (value: string | null | undefined): number => {
  if (!value) return 0;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
};
